#!/usr/bin/env python3
"""Trusted SamScript frontend, resolver, Wasm assembly, WASI runtime, and CLI."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import tempfile

TOKEN = re.compile(r'\s*(?:(//[^\n]*)|([A-Za-z_]\w*)|(\d+)|(==|!=|<=|>=|\+=|-=|\*=|&&|\|\||[{}(),;=+*%<>!-]))')


def lex(source):
    result, pos = [], 0
    while pos < len(source):
        match = TOKEN.match(source, pos)
        if not match:
            if not source[pos:].strip():
                break
            raise SyntaxError(f"unexpected input near {source[pos:pos + 12]!r}")
        pos = match.end()
        if match.group(1):
            continue
        text = next(group for group in match.groups()[1:] if group is not None)
        result.append(("id" if match.group(2) else "num" if match.group(3) else "op", text))
    return result + [("eof", "eof")]


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
        functions = []
        while not self.at("eof"):
            self.take("fn"); name = self.take()[1]; self.take("("); params = []
            while not self.at(")"):
                params.append(self.take()[1])
                if not self.at(","):
                    break
                self.take(",")
            self.take(")")
            functions.append((name, params, self.block()))
        return functions

    def block(self):
        self.take("{"); body = []
        while not self.at("}"):
            body.append(self.statement())
        self.take("}")
        return body

    def statement(self):
        if self.at("let"):
            self.take(); name = self.take()[1]; self.take("="); value = self.expr(); self.take(";")
            return ("let", name, value)
        if self.at("if"):
            self.take(); condition = self.expr(); yes = self.block(); no = []
            if self.at("else"):
                self.take(); no = self.block()
            return ("if", condition, yes, no)
        if self.at("loop"):
            self.take(); return ("loop", self.block())
        if self.at("return"):
            self.take(); value = self.expr(); self.take(";"); return ("return", value)
        if self.at("break") or self.at("continue"):
            kind = self.take()[1]; self.take(";"); return (kind,)
        if self.tokens[self.pos][0] == "id" and self.tokens[self.pos + 1][1] in ("=", "+=", "-=", "*="):
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
        elif token[1] in ("true", "false"):
            left = ("literal", int(token[1] == "true"))
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
        precedence = {"||": 1, "&&": 2, "==": 3, "!=": 3, "<": 4, "<=": 4, ">": 4, ">=": 4,
                      "+": 5, "-": 5, "*": 6, "%": 6}
        while self.tokens[self.pos][1] in precedence and precedence[self.tokens[self.pos][1]] >= minimum:
            op = self.take()[1]; priority = precedence[op]
            left = ("binary", op, left, self.expr(priority + 1))
        return left


@dataclass
class Function:
    name: str
    params: list[str]
    locals: list[str]
    body: list[tuple]


class Resolver:
    def __init__(self, signatures):
        self.signatures = signatures
        self.serial = 0

    def function(self, raw):
        name, raw_params, body = raw
        self.scopes, self.locals = [{}], []
        params = [self.declare(item, parameter=True) for item in raw_params]
        resolved = self.block(body, scoped=False)
        return Function(name, params, self.locals, resolved)

    def declare(self, name, parameter=False):
        if name in self.scopes[-1]:
            raise SyntaxError(f"duplicate binding {name}")
        unique = f"v{self.serial}"; self.serial += 1
        self.scopes[-1][name] = unique
        if not parameter:
            self.locals.append(unique)
        return unique

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise SyntaxError(f"undefined binding {name}")

    def expression(self, expr):
        if expr[0] == "name":
            return ("name", self.lookup(expr[1]))
        if expr[0] in ("literal",):
            return expr
        if expr[0] == "call":
            if expr[1] not in self.signatures or len(expr[2]) != self.signatures[expr[1]]:
                raise SyntaxError(f"invalid call to {expr[1]}")
            return ("call", expr[1], [self.expression(item) for item in expr[2]])
        if expr[0] == "unary":
            return ("unary", expr[1], self.expression(expr[2]))
        return ("binary", expr[1], self.expression(expr[2]), self.expression(expr[3]))

    def block(self, statements, scoped=True):
        if scoped:
            self.scopes.append({})
        result = []
        for stmt in statements:
            kind = stmt[0]
            if kind == "let":
                value = self.expression(stmt[2]); result.append((kind, self.declare(stmt[1]), value))
            elif kind == "assign":
                result.append((kind, self.lookup(stmt[1]), stmt[2], self.expression(stmt[3])))
            elif kind == "if":
                result.append((kind, self.expression(stmt[1]), self.block(stmt[2]), self.block(stmt[3])))
            elif kind == "loop":
                result.append((kind, self.block(stmt[1])))
            elif kind in ("return", "expr"):
                result.append((kind, self.expression(stmt[1])))
            else:
                result.append(stmt)
        if scoped:
            self.scopes.pop()
        return result


class Emitter:
    def __init__(self):
        self.lines, self.depth = [], 2

    def emit(self, line):
        self.lines.append("  " * self.depth + line)

    def open(self, line):
        self.emit(line); self.depth += 1

    def close(self, line="end"):
        self.depth -= 1; self.emit(line)


RUNTIME = r'''(module
  (import "wasi_snapshot_preview1" "fd_write" (func $fd_write (param i32 i32 i32 i32) (result i32)))
  (memory (export "memory") 1)
  (func $print_i32 (param $n i32) (local $p i32) (local $neg i32)
    i32.const 44
    local.set $p
    local.get $p
    i32.const 10
    i32.store8
    local.get $n
    i32.const 0
    i32.lt_s
    local.set $neg
    local.get $neg
    if
      i32.const 0
      local.get $n
      i32.sub
      local.set $n
    end
    block $digits_done
      loop $digits
        local.get $p
        i32.const 1
        i32.sub
        local.tee $p
        local.get $n
        i32.const 10
        i32.rem_u
        i32.const 48
        i32.add
        i32.store8
        local.get $n
        i32.const 10
        i32.div_u
        local.tee $n
        br_if $digits
      end
    end
    local.get $neg
    if
      local.get $p
      i32.const 1
      i32.sub
      local.tee $p
      i32.const 45
      i32.store8
    end
    i32.const 0
    local.get $p
    i32.store
    i32.const 4
    i32.const 45
    local.get $p
    i32.sub
    i32.store
    i32.const 1
    i32.const 0
    i32.const 1
    i32.const 8
    call $fd_write
    drop)
'''


def compile_source(source):
    raw = Parser(source).program()
    signatures = {name: len(params) for name, params, _ in raw}
    if "main" not in signatures or signatures["main"] != 0:
        raise SyntaxError("main must exist and take no arguments")
    resolver = Resolver(signatures)
    functions = [resolver.function(item) for item in raw]
    from lowering import Lowerer
    chunks = [RUNTIME]
    for function in functions:
        emitter = Emitter()
        params = "".join(f" (param ${item} i32)" for item in function.params)
        emitter.lines.append(f"  (func ${function.name}{params} (result i32)")
        emitter.lines.extend(f"    (local ${item} i32)" for item in function.locals)
        Lowerer(emitter).lower_function(function)
        emitter.lines.append("  )")
        chunks.append("\n".join(emitter.lines) + "\n")
    chunks.append('  (func (export "_start")\n    call $main\n    call $print_i32)\n)\n')
    return "".join(chunks)


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("input")
    compile_parser.add_argument("-o", "--output", required=True)
    compile_parser.add_argument("--target", choices=["wasm32-wasi"], required=True)
    args = parser.parse_args(argv)
    wat = compile_source(Path(args.input).read_text(encoding="utf-8"))
    with tempfile.NamedTemporaryFile("w", suffix=".wat", encoding="utf-8") as source:
        source.write(wat); source.flush()
        subprocess.run(["wat2wasm", source.name, "-o", args.output], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
