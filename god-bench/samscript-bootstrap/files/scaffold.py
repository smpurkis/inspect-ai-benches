"""Trusted SamScript lexer, parser, evaluator, imports, and CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import re


class RuntimeFault(Exception):
    pass


@dataclass(frozen=True)
class Return(Exception):
    value: object


class Break(Exception):
    pass


class Continue(Exception):
    pass


TOKEN = re.compile(r'\s*(?:(//[^\n]*)|([A-Za-z_]\w*)|(\d+)|("(?:\\.|[^"\\])*")|(==|!=|<=|>=|\+=|-=|\*=|/=|&&|\|\||[{}(),;=+*/%<>!-]))')


def lex(source):
    tokens, pos = [], 0
    while pos < len(source):
        match = TOKEN.match(source, pos)
        if not match:
            if source[pos:].strip() == "":
                break
            raise SyntaxError(f"unexpected input near {source[pos:pos + 12]!r}")
        pos = match.end()
        if match.group(1):
            continue
        kind = "id" if match.group(2) else "num" if match.group(3) else "str" if match.group(4) else match.group(5)
        text = next(group for group in match.groups()[1:] if group is not None)
        tokens.append((kind, text))
    tokens.append(("eof", "eof"))
    return tokens


class Parser:
    def __init__(self, source):
        self.tokens, self.pos = lex(source), 0

    def at(self, text):
        return self.tokens[self.pos][1] == text

    def take(self, text=None):
        token = self.tokens[self.pos]
        if text is not None and token[1] != text:
            raise SyntaxError(f"expected {text!r}, got {token[1]!r}")
        self.pos += 1
        return token

    def program(self):
        functions = {}
        while not self.at("eof"):
            self.take("fn")
            name = self.take()[1]
            self.take("(")
            params = []
            while not self.at(")"):
                params.append(self.take()[1])
                if not self.at(","):
                    break
                self.take(",")
            self.take(")")
            functions[name] = (params, self.block())
        return functions

    def block(self):
        self.take("{")
        body = []
        while not self.at("}"):
            body.append(self.statement())
        self.take("}")
        return body

    def statement(self):
        if self.at("let"):
            self.take(); name = self.take()[1]; self.take("="); value = self.expr(); self.take(";")
            return ("let", name, value)
        if self.at("if"):
            self.take(); condition = self.expr(); yes = self.block()
            no = []
            if self.at("else"):
                self.take(); no = self.block()
            return ("if", condition, yes, no)
        if self.at("loop"):
            self.take(); return ("loop", self.block())
        if self.at("return"):
            self.take(); value = None if self.at(";") else self.expr(); self.take(";"); return ("return", value)
        if self.at("break") or self.at("continue"):
            kind = self.take()[1]; self.take(";"); return (kind,)
        if self.tokens[self.pos][0] == "id" and self.tokens[self.pos + 1][1] in ("=", "+=", "-=", "*=", "/="):
            name = self.take()[1]; op = self.take()[1]; value = self.expr(); self.take(";")
            return ("assign", name, op, value)
        value = self.expr(); self.take(";"); return ("expr", value)

    def expr(self, minimum=0):
        token = self.take()
        if token[1] in ("!", "-"):
            left = ("unary", token[1], self.expr(8))
        elif token[1] == "(":
            left = self.expr(); self.take(")")
        elif token[0] == "num":
            left = ("literal", int(token[1]))
        elif token[0] == "str":
            left = ("literal", bytes(token[1][1:-1], "utf8").decode("unicode_escape"))
        elif token[1] in ("true", "false"):
            left = ("literal", token[1] == "true")
        else:
            left = ("name", token[1])
        if self.at("("):
            self.take(); args = []
            while not self.at(")"):
                args.append(self.expr())
                if not self.at(","):
                    break
                self.take(",")
            self.take(")"); left = ("call", left[1], args)
        precedence = {"||": 1, "&&": 2, "==": 3, "!=": 3, "<": 4, "<=": 4, ">": 4, ">=": 4, "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}
        while self.tokens[self.pos][1] in precedence and precedence[self.tokens[self.pos][1]] >= minimum:
            op = self.take()[1]; priority = precedence[op]
            left = ("binary", op, left, self.expr(priority + 1))
        return left


def evaluate(expr, runtime):
    kind = expr[0]
    if kind == "literal":
        return expr[1]
    if kind == "name":
        return runtime.lookup(expr[1])
    if kind == "call":
        args = [evaluate(item, runtime) for item in expr[2]]
        if expr[1] == "print":
            runtime.output.append(str(args[0]).lower() if isinstance(args[0], bool) else str(args[0]))
            return None
        return runtime.invoke(expr[1], args)
    if kind == "unary":
        value = evaluate(expr[2], runtime)
        return not value if expr[1] == "!" else -value
    op = expr[1]
    left = evaluate(expr[2], runtime)
    if op == "&&":
        return bool(left) and bool(evaluate(expr[3], runtime))
    if op == "||":
        return bool(left) or bool(evaluate(expr[3], runtime))
    right = evaluate(expr[3], runtime)
    operations = {"+": lambda: left + right, "-": lambda: left - right, "*": lambda: left * right,
                  "/": lambda: left // right, "%": lambda: left % right, "==": lambda: left == right,
                  "!=": lambda: left != right, "<": lambda: left < right, "<=": lambda: left <= right,
                  ">": lambda: left > right, ">=": lambda: left >= right}
    try:
        return operations[op]()
    except (KeyError, ZeroDivisionError) as exc:
        raise RuntimeFault(str(exc)) from exc


IMPORT = re.compile(r'^\s*from\s+"([^"]+)"\s+import\s+([A-Za-z_]\w*)\s*;\s*$', re.MULTILINE)


def load_program(path, seen=None):
    """Resolve explicit function imports before the candidate runtime sees the AST."""
    path = Path(path).resolve()
    seen = set() if seen is None else seen
    if path in seen:
        raise SyntaxError(f"cyclic import: {path}")
    seen.add(path)
    source = path.read_text(encoding="utf-8")
    imports = IMPORT.findall(source)
    functions = Parser(IMPORT.sub("", source)).program()
    for relative, name in imports:
        imported = load_program(path.parent / relative, seen)
        if name not in imported or name in functions:
            raise SyntaxError(f"invalid import: {name}")
        functions[name] = imported[name]
    seen.remove(path)
    return functions


def run_source(source):
    from runtime import Runtime
    output = []
    Runtime(Parser(source).program(), output).run()
    return "\n".join(output) + ("\n" if output else "")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("program")
    args = parser.parse_args(argv)
    functions = load_program(args.program)
    from runtime import Runtime
    output = []
    Runtime(functions, output).run()
    print("\n".join(output))


if __name__ == "__main__":
    main()
