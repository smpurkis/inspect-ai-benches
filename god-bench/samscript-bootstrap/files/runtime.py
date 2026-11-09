"""Candidate kernel: lexical environments and control-flow execution."""

from scaffold import Break, Continue, Return, RuntimeFault, evaluate


class Runtime:
    def __init__(self, functions, output):
        self.functions = functions
        self.output = output
        self.frames = []

    def declare(self, name, value):
        """Declare in the innermost lexical scope."""
        raise NotImplementedError("implement lexical declaration")

    def lookup(self, name):
        """Read the nearest visible binding."""
        raise NotImplementedError("implement lexical lookup")

    def assign(self, name, value):
        """Update the nearest visible binding."""
        raise NotImplementedError("implement lexical assignment")

    def execute_block(self, statements, *, scoped=True):
        """Execute statements, unwinding a block scope on every exit."""
        raise NotImplementedError("implement block execution")

    def execute_statement(self, statement):
        """Execute one parsed statement and preserve non-local signals."""
        raise NotImplementedError("implement statement execution")

    def invoke(self, name, arguments):
        """Call a function in an isolated frame and consume its return."""
        raise NotImplementedError("implement function invocation")

    def run(self):
        result = self.invoke("main", [])
        return result
