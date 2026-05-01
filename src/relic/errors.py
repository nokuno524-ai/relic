"""Error types for the Relic language."""


class RelicError(Exception):
    """Base error for all Relic errors."""


class LexError(RelicError):
    """Error during tokenization."""

    def __init__(self, message: str, line: int = 0, col: int = 0):
        self.line = line
        self.col = col
        super().__init__(f"Lex error at {line}:{col}: {message}")


class ParseError(RelicError):
    """Error during parsing."""

    def __init__(self, message: str, line: int = 0):
        self.line = line
        super().__init__(f"Parse error at line {line}: {message}")


class CyclicDependencyError(RelicError):
    """Cycle detected in constraint graph."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        super().__init__(f"Cyclic dependency: {' -> '.join(cycle)}")


class ResolveError(RelicError):
    """Error during constraint resolution."""

    def __init__(self, message: str):
        super().__init__(f"Resolve error: {message}")


class CodegenError(RelicError):
    """Error during code generation."""

    def __init__(self, message: str):
        super().__init__(f"Codegen error: {message}")
