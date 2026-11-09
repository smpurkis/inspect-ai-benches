"""Candidate kernel for structured SamScript-to-WAT lowering."""


class Lowerer:
    def __init__(self, emitter):
        self.out = emitter
        self.loops = []
        self.next_label = 0

    def lower_function(self, function):
        """Lower a resolved function body, leaving its result on the stack."""
        raise NotImplementedError("implement function lowering")

    def lower_block(self, statements):
        """Lower statements in source order."""
        raise NotImplementedError("implement block lowering")

    def lower_statement(self, statement):
        """Lower structured control flow and local mutations."""
        raise NotImplementedError("implement statement lowering")

    def lower_expr(self, expression):
        """Lower an i32 expression, preserving lazy boolean evaluation."""
        raise NotImplementedError("implement expression lowering")
