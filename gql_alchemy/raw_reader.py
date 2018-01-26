import typing as t


class Reader:
    text_input: str
    index: int
    lineno: int

    def __init__(self, text_input: str) -> None:
        self.text_input = text_input
        self.index = 0
        self.lineno = 1

    def str_read_ch(self) -> t.Optional[str]:
        if len(self.text_input) == self.index:
            return None

        ch = self.text_input[self.index]
        self.index += 1
        return ch

    def read_ch(self) -> t.Optional[str]:
        ch = self.lookup_ch()
        if ch is not None:
            self.index += 1
        return ch

    def lookup_ch(self) -> t.Optional[str]:
        while True:
            if len(self.text_input) == self.index:
                return None

            ch = self.text_input[self.index]

            if ch == "\n":
                self.lineno += 1
                self.index += 1
                continue

            if ch in " \r\t,":
                self.index += 1
                continue

            if ch == "#":
                index = self.text_input.find("\n", self.index)
                if index < 0:
                    self.index = len(self.text_input)
                else:
                    self.index = index
                continue

            return ch

    def match_re(self, regexp: t.Pattern[str]) -> t.Match[str]:
        return regexp.match(self.text_input, self.index)

    def read_re(self, regexp: t.Pattern[str]) -> t.Optional[str]:

        # eat ignoring characters
        self.lookup_ch()

        m = regexp.match(self.text_input, self.index)
        if m:
            self.index += len(m.group(0))
            return m.group(0)

        return None

    def line_pos(self) -> int:
        start = self.text_input.rfind("\n", 0, self.index)

        if start < 0:
            return self.index

        return self.index - start - 1

    def current_line(self) -> str:
        start = self.text_input.rfind("\n", 0, self.index)
        if start < 0:
            start = 0
        else:
            start += 1
        end = self.text_input.find("\n", self.index)
        if end < 0:
            end = len(self.text_input)
        return self.text_input[start:end]

    def prev_line(self) -> t.Optional[str]:
        prev_line_end = self.text_input.rfind("\n", 0, self.index)

        if prev_line_end < 0:
            return None

        if prev_line_end == 0:
            return ""

        prev_line_start = self.text_input.rfind("\n", 0, prev_line_end)

        if prev_line_start < 0:
            prev_line_start = 0
        else:
            prev_line_start += 1

        return self.text_input[prev_line_start:prev_line_end]

    def next_line(self) -> t.Optional[str]:
        next_line_start = self.text_input.find("\n", self.index)

        if next_line_start < 0:
            return None

        if next_line_start == len(self.text_input) - 1:
            return ""

        next_line_start += 1

        next_line_end = self.text_input.find("\n", next_line_start)

        if next_line_end < 0:
            next_line_end = len(self.text_input)

        return self.text_input[next_line_start:next_line_end]


def format_position(lineno: int, line_pos: int, lines: t.Sequence[t.Optional[str]]) -> t.Sequence[str]:
    result = []

    if lines[0] is not None:
        result.append("{:4d} | {}".format(lineno - 1, lines[0]))

    result.append("{:4d} | {}".format(lineno, lines[1]))
    result.append("       {}\u2303".format(" " * line_pos))

    if lines[2] is not None:
        result.append("{:4d} | {}".format(lineno + 1, lines[2]))

    return result


__all__ = ["Reader", "format_position"]
