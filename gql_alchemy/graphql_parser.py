import json
import logging
import re
from typing import List

from gql_alchemy.utils import add_if_not_none, add_if_not_empty

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
    def __init__(self):
        self.operations = []
        self.selections = []

    def consume(self, reader: Reader):
        pass

    def next(self, stack: List, reader: Reader):
        ch = reader.lookup_ch()

        if ch == "{":
            return SelectionsParser()

        if ch == "m":
            return Operation("mutation")

        if ch == "q":
            return Operation("query")

        if ch is None:
            return Success()

    def to_dict(self):
        d = {
            "type": "document"
        }
        add_if_not_empty(d, "operations", self.operations)
        add_if_not_empty(d, "selections", self.selections)
        return d


NAME_RE = re.compile(r'[_A-Za-z][_0-9A-Za-z]*')


class Operation:
    def __init__(self, type):
        self.type = type
        self.name = None
        self.variables = []
        self.directives = []
        self.selections = None

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
        if self.selections is not None:
            d = stack[-2]
            d.operations.append(self)
            del stack[-1]
            return
        ch = reader.lookup_ch()
        if ch == "(":
            reader.next_ch()
            return VariablesParser()
        if ch == "@":
            return DirectivesParser()
        if ch == "{":
            return SelectionsParser()
        raise ParsingError("Expected '{'", reader.position_str())

    def to_dict(self):
        return {
            "type": "mutation",
            "name": self.name,
            "variables": [v.to_dict() for v in self.variables],
            "directives": [d.to_dict() for d in self.directives],
            "selections": None if self.selections is None else [s.to_dict() for s in self.selections]
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
            raise RuntimeError("..., VariablesParser, Variable] expected")

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
            reader.next_ch()
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
        self.alias = None
        self.name = None
        self.arguments = []
        self.directives = []
        self.selections = []

    def consume(self, reader: Reader):
        name = reader.next_re(NAME_RE)
        if name is None:
            raise ParsingError("Name expected", reader.position_str())
        ch = reader.lookup_ch()
        if ch == ":":
            reader.next_ch()
            self.alias = name
            self.name = reader.next_re(NAME_RE)
            if self.name is None:
                raise ParsingError("Name expected", reader.position_str())
        else:
            self.name = name

    def next(self, stack: List, reader: Reader):
        ch = reader.lookup_ch()
        if ch == "(":
            return ArgumentsParser()
        elif ch == "@":
            return DirectivesParser()
        elif ch == "{":
            return SelectionsParser()
        else:
            sp = stack[-2]
            sp.selections.append(self)
            del stack[-1]

    def to_dict(self):
        d = {
            "type": "field",
            "name": self.name
        }
        add_if_not_none(d, "alias", self.alias)
        add_if_not_empty(d, "arguments", self.arguments)
        add_if_not_empty(d, "directives", self.directives)
        add_if_not_empty(d, "selections", self.selections)
        return d


class ArgumentsParser:
    def __init__(self):
        self.arguments = []

    def consume(self, reader: Reader):
        ch = reader.next_ch()
        if ch != "(":
            raise ParsingError("Expected '('", reader.position_str())

    def next(self, stack: List, reader: Reader):
        ch = reader.lookup_ch()
        if ch == ")":
            reader.next_ch()
            parent = stack[-2]
            parent.arguments = self.arguments
            del stack[-1]
        else:
            return Argument()

    def to_dict(self):
        return {
            "type": "argumentsParser",
            "arguments": [a.to_dict() for a in self.arguments]
        }


class Argument:
    def __init__(self):
        self.name = None
        self.value = None

    def consume(self, reader: Reader):
        self.name = reader.next_re(NAME_RE)
        if self.name is None:
            raise ParsingError("Name expected", reader.position_str())
        ch = reader.next_ch()
        if ch != ":":
            raise ParsingError("Expected ':'", reader.position_str())

    def next(self, stack, reader: Reader):
        return ValueParser()

    @staticmethod
    def value_to_dict(value):
        if isinstance(value, VariableValue) or isinstance(value, EnumValue) or isinstance(value, ObjectValue):
            return value.to_dict()
        if isinstance(value, list):
            return [Argument.value_to_dict(i) for i in value]

    def to_dict(self):
        return {
            "name": self.name,
            "value": self.value_to_dict(self.value)
        }


class ValueParser:
    def __init__(self, const=False):
        self.const = const

    def consume(self, reader: Reader):
        pass

    def next(self, stack: List, reader: Reader):
        ch = reader.lookup_ch()
        if ch == "$":
            if self.const:
                raise ParsingError("Unexpected '$'", reader.position_str())
            reader.next_ch()
            name = reader.next_re(NAME_RE)
            if name is None:
                raise ParsingError("Name expected", reader.position_str())
            self.reduce(stack, VariableValue(name))
        elif ch == '"':
            del stack[-1]
            return StringValueParser()
        elif ch == "[":
            del stack[-1]
            return ListValueParser(self.const)
        elif ch == "{":
            del stack[-1]
            return ObjectValueParser(self.const)
        else:
            v = reader.next_re(re.compile("true"))
            if v is not None:
                self.reduce(stack, True)
                return
            v = reader.next_re(re.compile("false"))
            if v is not None:
                self.reduce(stack, False)
                return
            v = reader.next_re(re.compile("null"))
            if v is not None:
                self.reduce(stack, None)
                return
            v = reader.next_re(NAME_RE)
            if v is not None:
                self.reduce(stack, EnumValue(v))
                return
            int_part = r'-?(?:[1-9][0-9]+|0)'
            fr_part = r'(?:\.[0-9]+)'
            exp_part = r'(?:[eE][+-]?[0-9]+)'
            v = reader.next_re(re.compile(int_part + r'(?:' + fr_part + exp_part + '?|' + exp_part + ')'))
            if v is not None:
                self.reduce(stack, float(v))
                return
            v = reader.next_re(re.compile(int_part))
            if v is not None:
                self.reduce(stack, int(v))
                return
            raise ParsingError("Value expected", reader.position_str())

    def reduce(self, stack: List, value):
        arg = stack[-2]
        arg.value = value
        args = stack[-3]
        args.arguments.append(arg)
        del stack[-1]
        del stack[-1]

    def to_dict(self):
        return {
            "type": "valueParser",
            "const": self.const
        }


class ListValueParser:
    def __init__(self, const):
        raise NotImplementedError()


class ObjectValueParser:
    def __init__(self, const):
        raise NotImplementedError()


class ObjectValue:
    def __init__(self, value):
        self.value = value

    def to_dict(self):
        return {
            "type": "objectValue",
            "value": self.value
        }


class StringValueParser:
    def __init__(self):
        raise NotImplementedError()


class VariableValue:
    def __init__(self, name):
        self.name = name

    def to_dict(self):
        return {
            "type": "variableValue",
            "name": self.name
        }


class EnumValue:
    def __init__(self, name):
        self.name = name

    def to_dict(self):
        return {
            "type": "enumValue",
            "name": self.name
        }


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

    def consume(self, reader):
        pass
