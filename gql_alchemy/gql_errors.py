import itertools

from .raw_reader import Reader, format_position


class GqlError(Exception):
    pass


class GqlParsingError(GqlError):
    """Errors during query parsing"""
    def __init__(self, msg: str, reader: Reader) -> None:
        self.msg = msg
        self.lineno = reader.lineno
        self.line_pos = reader.line_pos()
        self.lines = [reader.prev_line(), reader.current_line(), reader.next_line()]

    def __str__(self) -> str:
        return '\n'.join(itertools.chain([self.msg], format_position(self.lineno, self.line_pos, self.lines)))


class GqlSchemaError(GqlError):
    """Errors in schema definition"""
    pass


class GqlTypeServerError(GqlError):
    """Errors during execution: response do not match schema"""
    pass


class GqlTypeClientError(GqlError):
    """Errors during execution: query do not match schema"""
    pass


__all__ = ["GqlError", "GqlParsingError", "GqlSchemaError", "GqlTypeServerError", "GqlTypeClientError"]
