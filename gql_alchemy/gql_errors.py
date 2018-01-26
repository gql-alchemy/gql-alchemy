import itertools

from .raw_reader import Reader, format_position


class GqlParsingError(Exception):
    def __init__(self, msg: str, reader: Reader) -> None:
        self.msg = msg
        self.lineno = reader.lineno
        self.line_pos = reader.line_pos()
        self.lines = [reader.prev_line(), reader.current_line(), reader.next_line()]

    def __str__(self) -> str:
        return '\n'.join(itertools.chain([self.msg], format_position(self.lineno, self.line_pos, self.lines)))


__all__ = ["GqlParsingError"]
