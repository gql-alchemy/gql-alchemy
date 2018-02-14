import typing as t

from .raw_reader import Reader, format_position


class GqlError(Exception):
    pass


class GqlParsingError(GqlError):
    """Errors during query parsing"""

    def __init__(self, msg: str, reader: t.Optional[Reader] = None) -> None:
        self.msg = msg

        self.lineno: t.Optional[int] = None
        self.line_pos: t.Optional[int] = None
        self.lines: t.Optional[t.Sequence[t.Optional[str]]] = None

        if reader is not None:
            self.lineno = reader.lineno
            self.line_pos = reader.line_pos()
            self.lines = [reader.prev_line(), reader.current_line(), reader.next_line()]

    def __str__(self) -> str:
        lines = [self.msg]

        if self.lineno is not None and self.line_pos is not None and self.lines is not None:
            lines += format_position(self.lineno, self.line_pos, self.lines)

        return '\n'.join(lines)


class GqlValidationError(GqlError):
    pass


class GqlSchemaError(GqlError):
    """Errors in schema definition"""
    pass


class GqlExecutionError(GqlError):
    """Errors during execution: response do not match schema"""
    pass


__all__ = ["GqlError", "GqlParsingError", "GqlSchemaError", "GqlExecutionError",
           "GqlValidationError"]
