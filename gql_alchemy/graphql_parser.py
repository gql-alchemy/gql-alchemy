import json
import logging
import re
from typing import List

logger = logging.getLogger("parser")
logger.setLevel(logging.DEBUG)
sh = logging.StreamHandler()
sh.setLevel(logging.DEBUG)
logger.addHandler(sh)


class Reader:
    def __init__(self, input: str):
        self.input = input
        self.index = 0
        self.lineno = 1

    def push_back(self):
        self.index -= 1
        if self.input[self.index] == "\n":
            self.lineno -= 1

    def next_ch(self):
        while True:
            if len(self.input) == self.index:
                return None
            ch = self.input[self.index]
            if ch == "\n":
                self.lineno += 1
                self.index += 1
                continue
            if ch in " \r,":
                self.index += 1
                continue
            self.index += 1
            return ch

    def lookup_ch(self):
        while True:
            if len(self.input) == self.index:
                return None
            ch = self.input[self.index]
            if ch == "\n":
                self.lineno += 1
                self.index += 1
                continue
            if ch in " \r,":
                self.index += 1
                continue
            return ch

    def next_re(self, regexp):

        # eat ignoring characters
        self.lookup_ch()

        m = regexp.match(self.input, self.index)
        if m:
            self.index += len(m.group(0))
            return m.group(0)

    def position_str(self):
        start = self.input.rfind("\n", 0, self.index)
        if start < 0:
            start = 0
        else:
            start += 1
        end = self.input.find("\n", self.index)
        if end < 0:
            end = len(self.input)
        return "{}:  {}\u2304{}".format(self.lineno, self.input[start:self.index], self.input[self.index:end])


def log_stack(stack):
    logger.debug("Stack: %s", json.dumps([i.to_dict() for i in stack]))


def parse(input):
    stack = [Document()]
    reader = Reader(input)

    while True:
        logger.debug("BEGIN STEP")
        log_stack(stack)
        logger.debug("Position:\n%s", reader.position_str())
        last = stack[-1]
        if isinstance(last, Error):
            return
        if isinstance(last, Success):
            return stack[0]
        else:
            log_stack(stack)
            next = last.next(stack, reader)
            if next is not None:
                stack.append(next)
                logger.debug("Stack modified")
                log_stack(stack)
                next.consume(reader)
                logger.debug("Consumed:\n%s", reader.position_str())
        logger.debug("Finished:")
        log_stack(stack)


class ParsingError(RuntimeError):
    def __init__(self, msg, line):
        self.msg = msg
        self.line = line

    def __str__(self):
        return ''.join([self.msg, ":\n", self.line])


class ParseObject:
    def consume(self, reader: Reader):
        pass

    def next(self, stack: List, reader: Reader):
        pass

    def to_dict(self):
        return {}


class Document:
    def consume(self, reader: Reader):
        pass

    def next(self, stack: List, reader: Reader):
        ch = reader.lookup_ch()

        if ch == "m":
            return Operation("mutation")

        if ch == "q":
            return Operation("query")

    def to_dict(self):
        return {
            "type": "document"
        }


NAME_RE = re.compile(r'[_A-Za-z][_0-9A-Za-z]*')


class Operation:
    def __init__(self, type):
        self.type = type
        self.name = None
        self.variables = []
        self.directives = []
        self.selections = []

    def consume(self, reader: Reader):
        m = reader.next_re(re.compile(self.type))
        if m is None:
            raise ParsingError("Expected `{}` keyword".format(type), reader.position_str())

        ch = reader.lookup_ch()
        if ch not in "(@{":
            name = reader.next_re(NAME_RE)
            if name is None:
                raise ParsingError("Name expected", reader.position_str())
            self.name = name

    def next(self, stack: List, reader: Reader):
        ch = reader.lookup_ch()
        if ch == "(":
            reader.next_ch()
            return VariablesParser()
        if ch == "@":
            return DirectivesParser()
        if ch == "{":
            return SelectionsParser()

    def to_dict(self):
        return {
            "type": "mutation"
        }


class VariablesParser:
    def __init__(self):
        self.variables = []

    def consume(self, reader: Reader):
        pass

    def consume_default(self, reader):
        ch = reader.lookup_ch()
        if ch == "=":
            reader.next_ch()

    def next(self, stack: List, reader: Reader):
        ch = reader.next_ch()
        if ch == ")":
            o = stack[-2]
            if isinstance(o, Operation):
                o.variables = self.variables
            else:
                raise RuntimeError("..., Operation, VariablesParser] expected")
            del stack[-1]
        elif ch == "$":
            return Variable()
        else:
            raise RuntimeError("Expected ')' or '$'", reader.position_str())

    def to_dict(self):
        return {
            "type": "variablesParser",
            "variables": [v.to_dict() for v in self.variables]
        }


class Variable:
    def __init__(self):
        self.name = None
        self.type = None
        self.default = None

    def consume(self, reader):
        self.name = reader.next_re(NAME_RE)
        if self.name is None:
            raise ParsingError("Variable name expected", reader.position_str())
        self.type = self.consume_type(reader)

    def consume_type(self, reader):
        ch = reader.next_ch()
        if ch != ":":
            raise ParsingError("Expected ':'", reader.position_str())
        ch = reader.lookup_ch()
        if ch == "[":
            reader.next_ch()
            type = self.consume_type(reader)
            ch = reader.next_ch()
            if ch != "]":
                raise ParsingError("Expected ']'", reader.position_str())
            ch = reader.lookup_ch()
            if ch == "!":
                reader.next_ch()
                return ListType(type, True)
            return ListType(type)
        else:
            type = reader.next_re(NAME_RE)
            ch = reader.lookup_ch()
            if ch == "!":
                reader.next_ch()
                return NameType(type, True)
            return NameType(type)

    def next(self, stack: List, reader: Reader):
        ch = reader.lookup_ch()
        if ch == "=":
            reader.next_ch()
            return DefaultParser()

        vp = stack[-2]
        if isinstance(vp, VariablesParser):
            vp.variables.append(self)
            del stack[-1]
        else:
            raise RuntimeError("..., VariablesParser, VariableParser] expected")

    def to_dict(self):
        return {
            "type": "variable",
            "name": self.name,
            "var_type": self.type.to_dict() if self.type is not None else None,
            "default": self.default
        }


class DefaultParser:
    def __init__(self):
        raise NotImplementedError()


class Type:
    def __init__(self, non_null: bool):
        self.non_null = non_null

    def to_dict(self):
        raise NotImplementedError("Supposed to be overridden")


class ListType(Type):
    def __init__(self, type: Type, non_null=False):
        super().__init__(non_null)
        self.type = type

    def to_dict(self):
        return {
            "list": self.type.to_dict(),
            "nonNull": self.non_null
        }


class NameType(Type):
    def __init__(self, type: str, non_null=False):
        super().__init__(non_null)
        self.type = type

    def to_dict(self):
        return {
            "name": self.type,
            "nonNull": self.non_null
        }


class DirectivesParser:
    def __init__(self):
        self.directives = []

    def consume(self, reader: Reader):
        pass

    def next(self, stack: List, reader: Reader):
        pass

    def to_dict(self):
        return {}


class SelectionsParser:
    def __init__(self):
        self.selections = []

    def consume(self, reader: Reader):
        ch = reader.next_ch()
        if ch != "{":
            raise ParsingError("Expected '{'", reader.position_str())

    def next(self, stack: List, reader: Reader):
        ch = reader.lookup_ch()
        if ch == "}":
            parent = stack[-2]
            parent.selections = self.selections
            del stack[-1]
        elif ch == ".":
            return SpreadParser()
        else:
            return Field()

    def to_dict(self):
        return {
            "type": "selectionsParser"
        }


class Field:
    def __init__(self):
        raise NotImplementedError()


class SpreadParser:
    def __init__(self):
        raise NotImplementedError()


class Error:
    def to_dict(self):
        return {
            "type": "error"
        }


class Success:
    def to_dict(self):
        return {
            "type": "success"
        }
