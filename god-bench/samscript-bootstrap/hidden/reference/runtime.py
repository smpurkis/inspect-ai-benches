"""Reference kernel retained only in the verifier image."""

from scaffold import Break, Continue, Return, RuntimeFault, evaluate


class Runtime:
    def __init__(self, functions, output):
        self.functions, self.output, self.frames = functions, output, []

    def declare(self, name, value):
        scope = self.frames[-1][-1]
        if name in scope:
            raise RuntimeFault(f"duplicate binding: {name}")
        scope[name] = value

    def lookup(self, name):
        for scope in reversed(self.frames[-1]):
            if name in scope:
                return scope[name]
        raise RuntimeFault(f"undefined binding: {name}")

    def assign(self, name, value):
        for scope in reversed(self.frames[-1]):
            if name in scope:
                scope[name] = value
                return
        raise RuntimeFault(f"undefined binding: {name}")

    def execute_block(self, statements, *, scoped=True):
        if scoped:
            self.frames[-1].append({})
        try:
            for statement in statements:
                self.execute_statement(statement)
        finally:
            if scoped:
                self.frames[-1].pop()

    def execute_statement(self, statement):
        kind = statement[0]
        if kind == "let":
            self.declare(statement[1], evaluate(statement[2], self))
        elif kind == "assign":
            old, rhs = self.lookup(statement[1]), evaluate(statement[3], self)
            op = statement[2]
            value = {"=": lambda: rhs, "+=": lambda: old + rhs, "-=": lambda: old - rhs,
                     "*=": lambda: old * rhs, "/=": lambda: old // rhs}[op]()
            self.assign(statement[1], value)
        elif kind == "expr":
            evaluate(statement[1], self)
        elif kind == "if":
            branch = statement[2] if evaluate(statement[1], self) else statement[3]
            self.execute_block(branch)
        elif kind == "loop":
            while True:
                try:
                    self.execute_block(statement[1])
                except Continue:
                    continue
                except Break:
                    break
        elif kind == "break":
            raise Break()
        elif kind == "continue":
            raise Continue()
        elif kind == "return":
            raise Return(None if statement[1] is None else evaluate(statement[1], self))

    def invoke(self, name, arguments):
        if name not in self.functions:
            raise RuntimeFault(f"undefined function: {name}")
        params, body = self.functions[name]
        if len(params) != len(arguments):
            raise RuntimeFault(f"arity mismatch for {name}")
        self.frames.append([dict(zip(params, arguments))])
        try:
            try:
                self.execute_block(body, scoped=False)
            except Return as signal:
                return signal.value
            except (Break, Continue) as signal:
                raise RuntimeFault(f"{type(signal).__name__.lower()} outside loop") from signal
            return None
        finally:
            self.frames.pop()

    def run(self):
        return self.invoke("main", [])
