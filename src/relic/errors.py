"""Error types for the Relic language."""

import difflib


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

    def __init__(self, message: str, suggestions: list[str] | None = None):
        self.suggestions = suggestions or []
        msg = f"Resolve error: {message}"
        if self.suggestions:
            msg += f" Did you mean: {', '.join(repr(s) for s in self.suggestions)}?"
        super().__init__(msg)


def suggest_names(name: str, candidates: list[str], n: int = 3) -> list[str]:
    """Return close matches for a name from a list of candidates."""
    return difflib.get_close_matches(name, candidates, n=n, cutoff=0.5)


class CodegenError(RelicError):
    """Error during code generation."""

    def __init__(self, message: str):
        super().__init__(f"Codegen error: {message}")
