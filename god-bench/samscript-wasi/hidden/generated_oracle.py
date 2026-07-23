"""Deterministic SamScript AST generator and independent executable oracle."""

# Kept byte-for-byte equivalent to the bootstrap task's hidden oracle so the
# two backends are measured against one semantic model, not against each other.
from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any


@dataclass(frozen=True)
class Expr:
    kind: str
    value: Any = None
    args: tuple["Expr", ...] = ()


@dataclass(frozen=True)
class Stmt:
    kind: str
    value: Any = None
    args: tuple[Any, ...] = ()


@dataclass(frozen=True)
class Function:
    name: str
    params: tuple[str, ...]
    body: tuple[Stmt, ...]


@dataclass(frozen=True)
class Program:
    functions: tuple[Function, ...]


@dataclass(frozen=True)
class OracleResult:
    stdout: str
    status: int
    error_class: str | None = None


class ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


class BreakSignal(Exception):
    pass


class RuntimeFault(Exception):
    def __init__(self, error_class: str):
        self.error_class = error_class


def n(value: int | float) -> Expr:
    return Expr("literal", float(value))


def b(value: bool) -> Expr:
    return Expr("literal", value)


def v(name: str) -> Expr:
    return Expr("variable", name)


def call(name: str, *args: Expr) -> Expr:
    return Expr("call", name, tuple(args))


def binary(op: str, left: Expr, right: Expr) -> Expr:
    return Expr("binary", op, (left, right))


def interpolation(*parts: str | Expr) -> Expr:
    return Expr("interpolation", tuple(parts))


_PRECEDENCE = {"or": 1, "and": 2, "==": 3, "!=": 3, "<": 4, ">": 4,
               "<=": 4, ">=": 4, "+": 5, "-": 5, "..": 5, "*": 6,
               "/": 6, "%": 6, "**": 7}


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else repr(value)


def _quote(text: str) -> str:
    return (text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            .replace("\t", "\\t").replace("$", "\\$"))


def render_expr(expr: Expr, minimum_precedence: int = 0) -> str:
    if expr.kind == "literal":
        if isinstance(expr.value, bool):
            return "true" if expr.value else "false"
        return _format_number(expr.value)
    if expr.kind == "variable":
        return expr.value
    if expr.kind == "call":
        return f"{expr.value}({', '.join(render_expr(arg) for arg in expr.args)})"
    if expr.kind == "interpolation":
        body = "".join(_quote(part) if isinstance(part, str) else "${" + render_expr(part) + "}"
                       for part in expr.value)
        return f'"{body}"'
    if expr.kind == "binary":
        op, precedence = expr.value, _PRECEDENCE[expr.value]
        left_min = precedence + (1 if op == "**" else 0)
        right_min = precedence + (0 if op == "**" else 1)
        text = f"{render_expr(expr.args[0], left_min)} {op} {render_expr(expr.args[1], right_min)}"
        return f"({text})" if precedence < minimum_precedence else text
    raise AssertionError(f"unknown expression kind: {expr.kind}")


def _render_block(statements: tuple[Stmt, ...], depth: int) -> list[str]:
    lines: list[str] = []
    pad = "    " * depth
    for stmt in statements:
        if stmt.kind == "let":
            lines.append(f"{pad}let {stmt.value} = {render_expr(stmt.args[0])}")
        elif stmt.kind == "assign":
            lines.append(f"{pad}{stmt.value} {stmt.args[0]} {render_expr(stmt.args[1])}")
        elif stmt.kind == "print":
            lines.append(f"{pad}print({render_expr(stmt.args[0])})")
        elif stmt.kind == "expr":
            lines.append(f"{pad}{render_expr(stmt.args[0])}")
        elif stmt.kind == "return":
            lines.append(f"{pad}return {render_expr(stmt.args[0])}")
        elif stmt.kind == "break":
            lines.append(f"{pad}break")
        elif stmt.kind == "if":
            lines.append(f"{pad}if {render_expr(stmt.args[0])} {{")
            lines.extend(_render_block(stmt.args[1], depth + 1))
            lines.append(f"{pad}}}")
        elif stmt.kind == "loop":
            lines.append(f"{pad}loop {{")
            lines.extend(_render_block(stmt.args[0], depth + 1))
            lines.append(f"{pad}}}")
        else:
            raise AssertionError(f"unknown statement kind: {stmt.kind}")
    return lines


def render(program: Program) -> str:
    lines = ["// generated from a deterministic typed AST; values are not fixtures"]
    for function in program.functions:
        lines.append(f"fn {function.name}({', '.join(function.params)}) {{")
        lines.extend(_render_block(function.body, 1))
        lines.extend(("}", ""))
    return "\n".join(lines)


class Oracle:
    def __init__(self, program: Program):
        self.functions = {function.name: function for function in program.functions}
        self.scopes: list[dict[str, Any]] = []
        self.output: list[str] = []

    def lookup(self, name: str) -> Any:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise RuntimeFault("undeclared_binding")

    def assign(self, name: str, value: Any) -> None:
        for scope in reversed(self.scopes):
            if name in scope:
                scope[name] = value
                return
        raise RuntimeFault("undeclared_binding")

    def evaluate(self, expr: Expr) -> Any:
        if expr.kind == "literal":
            return expr.value
        if expr.kind == "variable":
            return self.lookup(expr.value)
        if expr.kind == "call":
            return self.invoke(expr.value, [self.evaluate(arg) for arg in expr.args])
        if expr.kind == "interpolation":
            return "".join(part if isinstance(part, str) else self.stringify(self.evaluate(part))
                           for part in expr.value)
        if expr.kind == "binary":
            op = expr.value
            left = self.evaluate(expr.args[0])
            if op == "and":
                return self.evaluate(expr.args[1]) if left else False
            if op == "or":
                return True if left else self.evaluate(expr.args[1])
            right = self.evaluate(expr.args[1])
            if op in ("/", "%") and right == 0.0:
                raise RuntimeFault("division_by_zero")
            operations = {"+": lambda: left + right, "-": lambda: left - right,
                          "*": lambda: left * right, "/": lambda: left / right,
                          "%": lambda: left % right, "**": lambda: left**right,
                          "==": lambda: left == right, "!=": lambda: left != right,
                          "<": lambda: left < right, ">": lambda: left > right,
                          "<=": lambda: left <= right, ">=": lambda: left >= right,
                          "..": lambda: self.stringify(left) + self.stringify(right)}
            return operations[op]()
        raise AssertionError(f"unknown expression kind: {expr.kind}")

    @staticmethod
    def stringify(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "none"
        if isinstance(value, float):
            return _format_number(value)
        return value

    def execute_block(self, statements: tuple[Stmt, ...], scoped: bool = True) -> None:
        if scoped:
            self.scopes.append({})
        try:
            for stmt in statements:
                if stmt.kind == "let":
                    self.scopes[-1][stmt.value] = self.evaluate(stmt.args[0])
                elif stmt.kind == "assign":
                    old, rhs, op = self.lookup(stmt.value), self.evaluate(stmt.args[1]), stmt.args[0]
                    value = rhs if op == "=" else self.evaluate(binary(op[0], Expr("literal", old), Expr("literal", rhs)))
                    self.assign(stmt.value, value)
                elif stmt.kind == "print":
                    self.output.append(self.stringify(self.evaluate(stmt.args[0])))
                elif stmt.kind == "expr":
                    self.evaluate(stmt.args[0])
                elif stmt.kind == "return":
                    raise ReturnSignal(self.evaluate(stmt.args[0]))
                elif stmt.kind == "break":
                    raise BreakSignal
                elif stmt.kind == "if" and self.evaluate(stmt.args[0]):
                    self.execute_block(stmt.args[1])
                elif stmt.kind == "loop":
                    while True:
                        try:
                            self.execute_block(stmt.args[0])
                        except BreakSignal:
                            break
        finally:
            if scoped:
                self.scopes.pop()

    def invoke(self, name: str, arguments: list[Any]) -> Any:
        function = self.functions[name]
        if len(arguments) != len(function.params):
            raise RuntimeFault("arity")
        saved_scopes, self.scopes = self.scopes, [dict(zip(function.params, arguments))]
        try:
            try:
                self.execute_block(function.body, scoped=False)
            except ReturnSignal as signal:
                return signal.value
            return None
        finally:
            self.scopes = saved_scopes

    def run(self) -> OracleResult:
        try:
            self.invoke("main", [])
        except RuntimeFault as fault:
            stdout = "\n".join(self.output) + ("\n" if self.output else "")
            return OracleResult(stdout, 1, fault.error_class)
        return OracleResult("\n".join(self.output) + ("\n" if self.output else ""), 0)


def build_program(seed: int, mutable_leaf: int) -> Program:
    rng = random.Random(seed)
    tag = "g" + "".join(rng.choice("abcdefghjkmnpqrstuvwxyz") for _ in range(9))
    left, middle, right = (rng.randint(2, 8) for _ in range(3))
    precedence = binary("+", n(left), binary("*", n(middle), n(right)))
    power = binary("**", n(2), binary("**", n(2), n(3)))
    fact = Function("fold_recur", ("n",), (
        Stmt("if", args=(binary("<=", v("n"), n(1)), (Stmt("return", args=(n(1),)),))),
        Stmt("return", args=(binary("*", v("n"), call("fold_recur", binary("-", v("n"), n(1)))),)),
    ))
    marker = Function("forbidden_side_effect", ("x",), (
        Stmt("print", args=(interpolation(tag, ":BAD:", v("x")),)),
        Stmt("return", args=(b(True),)),
    ))
    main = Function("main", (), (
        Stmt("let", "base", (n(mutable_leaf),)),
        Stmt("print", args=(interpolation(tag, ":precedence=", precedence, ":power=", power),)),
        Stmt("print", args=(interpolation(tag, ":recursion=", call("fold_recur", v("base"))),)),
        Stmt("if", args=(b(True), (
            Stmt("let", "base", (binary("+", v("base"), n(3)),)),
            Stmt("assign", "base", ("+=", n(2))),
            Stmt("print", args=(interpolation(tag, ":inner=", v("base")),)),
        ))),
        Stmt("print", args=(interpolation(tag, ":outer=", v("base")),)),
        Stmt("let", "i", (n(0),)), Stmt("let", "sum", (n(0),)),
        Stmt("loop", args=((
            Stmt("if", args=(binary(">=", v("i"), v("base")), (Stmt("break"),))),
            Stmt("assign", "sum", ("+=", v("i"))),
            Stmt("assign", "i", ("+=", n(1))),
        ),)),
        Stmt("print", args=(interpolation(tag, ":mutation=", v("sum")),)),
        Stmt("expr", args=(binary("and", b(False), call("forbidden_side_effect", v("base"))),)),
        Stmt("expr", args=(binary("or", b(True), call("forbidden_side_effect", binary("+", v("base"), n(1)))),)),
        Stmt("print", args=(interpolation(tag, ':escape:\nquote=";slash=\\;dollar=$;tab=\t;value=', v("base")),)),
    ))
    return Program((fact, marker, main))


def build_error_program(seed: int) -> Program:
    rng = random.Random(seed)
    numerator, leaf = rng.randint(11, 97), rng.randint(3, 12)
    return Program((Function("main", (), (
        Stmt("let", "leaf", (n(leaf),)),
        Stmt("let", "dynamic_zero", (binary("-", v("leaf"), v("leaf")),)),
        Stmt("print", args=(binary("/", n(numerator), v("dynamic_zero")),)),
    )),))


def execute(program: Program) -> OracleResult:
    return Oracle(program).run()
