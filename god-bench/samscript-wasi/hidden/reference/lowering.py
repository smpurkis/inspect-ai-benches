"""Reference structured lowering kernel retained only in the verifier image."""


class Lowerer:
    def __init__(self, emitter):
        self.out = emitter
        self.loops = []
        self.next_label = 0

    def lower_function(self, function):
        self.out.emit("i32.const 0")
        self.out.emit("local.set $result")
        # The resolver reserves no synthetic locals, so declare the result inline.
        self.out.lines.insert(1, "    (local $result i32)")
        self.out.open("block $return")
        self.lower_block(function.body)
        self.out.close()
        self.out.emit("local.get $result")

    def lower_block(self, statements):
        for statement in statements:
            self.lower_statement(statement)

    def lower_statement(self, statement):
        kind = statement[0]
        if kind == "let":
            self.lower_expr(statement[2])
            self.out.emit(f"local.set ${statement[1]}")
        elif kind == "assign":
            op = statement[2]
            if op != "=":
                self.out.emit(f"local.get ${statement[1]}")
            self.lower_expr(statement[3])
            if op != "=":
                self.out.emit({"+=": "i32.add", "-=": "i32.sub", "*=": "i32.mul"}[op])
            self.out.emit(f"local.set ${statement[1]}")
        elif kind == "expr":
            self.lower_expr(statement[1])
            self.out.emit("drop")
        elif kind == "if":
            self.lower_expr(statement[1])
            self.out.open("if")
            self.lower_block(statement[2])
            if statement[3]:
                self.out.depth -= 1
                self.out.emit("else")
                self.out.depth += 1
                self.lower_block(statement[3])
            self.out.close()
        elif kind == "loop":
            serial = self.next_label
            self.next_label += 1
            break_label, continue_label = f"break{serial}", f"loop{serial}"
            self.loops.append((break_label, continue_label))
            self.out.open(f"block ${break_label}")
            self.out.open(f"loop ${continue_label}")
            self.lower_block(statement[1])
            self.out.emit(f"br ${continue_label}")
            self.out.close()
            self.out.close()
            self.loops.pop()
        elif kind in ("break", "continue"):
            if not self.loops:
                raise SyntaxError(f"{kind} outside loop")
            target = self.loops[-1][0 if kind == "break" else 1]
            self.out.emit(f"br ${target}")
        elif kind == "return":
            self.lower_expr(statement[1])
            self.out.emit("local.set $result")
            self.out.emit("br $return")
        else:
            raise AssertionError(kind)

    def lower_expr(self, expression):
        kind = expression[0]
        if kind == "literal":
            self.out.emit(f"i32.const {expression[1]}")
        elif kind == "name":
            self.out.emit(f"local.get ${expression[1]}")
        elif kind == "call":
            for argument in expression[2]:
                self.lower_expr(argument)
            self.out.emit(f"call ${expression[1]}")
        elif kind == "unary":
            if expression[1] == "!":
                self.lower_expr(expression[2]); self.out.emit("i32.eqz")
            else:
                self.out.emit("i32.const 0"); self.lower_expr(expression[2]); self.out.emit("i32.sub")
        elif expression[1] in ("&&", "||"):
            self.lower_expr(expression[2])
            self.out.open("if (result i32)")
            if expression[1] == "&&":
                self.lower_expr(expression[3])
                self.out.depth -= 1; self.out.emit("else"); self.out.depth += 1
                self.out.emit("i32.const 0")
            else:
                self.out.emit("i32.const 1")
                self.out.depth -= 1; self.out.emit("else"); self.out.depth += 1
                self.lower_expr(expression[3])
            self.out.close()
        else:
            self.lower_expr(expression[2]); self.lower_expr(expression[3])
            opcode = {"+": "i32.add", "-": "i32.sub", "*": "i32.mul", "%": "i32.rem_s",
                      "==": "i32.eq", "!=": "i32.ne", "<": "i32.lt_s", "<=": "i32.le_s",
                      ">": "i32.gt_s", ">=": "i32.ge_s"}[expression[1]]
            self.out.emit(opcode)
