import json
import logging
import re
from typing import List

from .gql_model import *

logger = logging.getLogger("parser")
logger.setLevel(logging.DEBUG)
sh = logging.StreamHandler()
sh.setLevel(logging.DEBUG)
logger.addHandler(sh)


class Reader:
    text_input: str
    index: int
    lineno: int

    def __init__(self, text_input: str):
        self.text_input = text_input
        self.index = 0
        self.lineno = 1

    def push_back(self):
        self.index -= 1
        if self.text_input[self.index] == "\n":
            self.lineno -= 1

    def str_next_ch(self):
        if len(self.text_input) == self.index:
            return None

        ch = self.text_input[self.index]
        self.index += 1
        return ch

    def next_ch(self) -> Optional[str]:
        ch = self.lookup_ch()
        if ch is not None:
            self.index += 1
        return ch

    def lookup_ch(self) -> Optional[str]:
        while True:
            if len(self.text_input) == self.index:
                return None

            ch = self.text_input[self.index]

            if ch == "\n":
                self.lineno += 1
                self.index += 1
                continue

            if ch in " \r,":
                self.index += 1
                continue

            if ch == "#":
                index = self.text_input.find("\n")
                if index < 0:
                    self.index = len(self.text_input)
                else:
                    self.index = index
                continue

            return ch

    def match_re(self, regexp):
        return regexp.match(self.text_input, self.index)

    def next_re(self, regexp) -> Optional[str]:

        # eat ignoring characters
        self.lookup_ch()

        m = regexp.match(self.text_input, self.index)
        if m:
            self.index += len(m.group(0))
            return m.group(0)

    def position_str(self) -> str:
        start = self.text_input.rfind("\n", 0, self.index)
        if start < 0:
            start = 0
        else:
            start += 1
        end = self.text_input.find("\n", self.index)
        if end < 0:
            end = len(self.text_input)
        return "{}:  {}\u2304{}".format(self.lineno, self.text_input[start:self.index], self.text_input[self.index:end])


def log_stack(stack):
    logger.debug("Stack: %s", json.dumps([i.to_dbg_repr() for i in stack]))


def parse_document(text_input: str) -> Document:
    document = []

    def set_document(d):
        document.append(d)

    parser = DocumentParser(set_document)

    parse(text_input, parser)

    return document[0]


def parse(text_input: str, initial_parser: 'ElementParser'):
    stack: List[ElementParser] = [initial_parser]
    reader = Reader(text_input)

    logger.debug("=== START PARSING ===")
    log_stack(stack)

    while True:
        if len(stack) == 0:
            logger.debug("=== FINISH PARSING ===")
            log_stack(stack)

            if reader.lookup_ch() is not None:
                logger.debug("POS %s", reader.position_str())
                raise ParsingError("Not all input parsed", reader)

            logger.debug("POS EOI")
            return

        parser = stack[-1]

        index_before = reader.index
        to_add, remove_count = parser.next(reader)
        index_after = reader.index

        if to_add is None and remove_count == 0 and index_before == index_after:
            parser_name = type(parser).__name__
            logger.debug("Parser did nothing: %s", parser_name)
            raise RuntimeError("Parser did no change during a step, stop "
                               "parsing to prevent looping forever (parser: {})".format(parser_name))

        if index_after != index_before:
            logger.debug("READ DETECTED")
            logger.debug("POS %s", reader.position_str())
            log_stack(stack)

        if remove_count > 0:
            stack[-remove_count:] = []
            log_stack(stack)

        if to_add is not None:
            stack.append(to_add)

            log_stack(stack)

            index_before = reader.index
            to_add.consume(reader)
            index_after = reader.index

            if index_after != index_before:
                logger.debug("READ DETECTED")
                logger.debug("POS %s", reader.position_str())
                log_stack(stack)


class ParsingError(RuntimeError):
    def __init__(self, msg: str, reader: Reader):
        self.msg = msg
        self.line = reader.position_str()
        self.lineno = reader.lineno

    def __str__(self):
        return ''.join([self.msg, ":\n", self.line])


class LiteralExpected(ParsingError):
    def __init__(self, symbols: Sequence[str], reader: Reader):
        if len(symbols) == 1:
            msg = "Expected '{}'".format(symbols[0])
        else:
            msg = "One of {} and {} expected".format(', '.join(symbols[-1:]), symbols[-1])
        super().__init__(msg, reader)
        self.symbols = symbols


NAME_RE = re.compile(r'[_A-Za-z][_0-9A-Za-z]*')


class ElementParser:
    @staticmethod
    def assert_ch(reader: Reader, ch: str):
        next_ch = reader.next_ch()
        if next_ch != ch:
            raise LiteralExpected([ch], reader)

    @staticmethod
    def assert_literal(reader: Reader, literal: str):
        next_literal = reader.next_re(re.compile(r'(?:' + literal + r')[ \t]'))
        if next_literal is None:
            raise LiteralExpected([literal], reader)

    @staticmethod
    def try_literal(reader: Reader, literal: str):
        next_literal = reader.next_re(re.compile(r'(?:' + literal + r')[ \t]'))
        return next_literal is not None

    @staticmethod
    def read_if(reader: Reader, ch: str):
        next_ch = reader.lookup_ch()

        if next_ch == ch:
            reader.next_ch()
            return True

        return False

    @staticmethod
    def read_name(reader: Reader):
        name = reader.next_re(NAME_RE)

        if name is None:
            raise ParsingError("Name expected", reader)

        return name

    def consume(self, reader: Reader):
        raise NotImplementedError()

    def next(self, reader: Reader) -> (Optional['ElementParser'], int):
        raise NotImplementedError()

    def to_dbg_repr(self) -> PrimitiveType:
        return {
            "parser": type(self).__name__
        }


class DocumentParser(ElementParser):
    def __init__(self, set_document):
        self.set_document = set_document

        self.operations = []
        self.fragments = []
        self.selections = []

        self.selection_allowed = True
        self.query_allowed = True

    def consume(self, reader: Reader):
        pass

    def next(self, reader):
        ch = reader.lookup_ch()

        if self.selection_allowed and ch == "{":
            self.selection_allowed = False
            self.query_allowed = False
            return SelectionsParser(self.selections), 0

        if ch == "m":
            return OperationParser("mutation", self.operations), 0

        if self.query_allowed and ch == "q":
            self.selection_allowed = False
            return OperationParser("query", self.operations), 0

        if ch == "f":
            return FragmentParser(self.fragments), 0

        if ch is None:
            self.set_document(Document(self.selections, self.operations, self.fragments))
            return None, 1

        raise ParsingError("One of top-level declaration expected", reader)

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        add_if_not_empty(d, "ops", self.operations)
        add_if_not_empty(d, "frgs", self.fragments)
        add_if_not_empty(d, "sels", self.selections)
        return d


class OperationParser(ElementParser):
    variables: List[VariableDefinition]
    directives: List[Directive]
    selections: List[Selection]

    def __init__(self, operation_type, operations: List[Operation]):
        self.operation_type = operation_type
        self.operations = operations

        self.name = None
        self.variables = []
        self.directives = []
        self.selections = []

        self.expected = {
            '(': self.next_variables,
            '@': self.next_directives,
            '{': self.next_selections
        }

    def consume(self, reader: Reader):
        self.assert_literal(reader, self.operation_type)

        ch = reader.lookup_ch()

        if ch not in self.expected:
            name = reader.next_re(NAME_RE)
            if name is None:
                raise ParsingError("One of `name`, '(', '@' or '{' expected", reader)
            self.name = name

    def next(self, reader):

        if len(self.expected) == 0:
            if self.operation_type == "query":
                self.operations.append(Query(self.name, self.variables, self.directives, self.selections))
            else:
                self.operations.append(Mutation(self.name, self.variables, self.directives, self.selections))
            return None, 1

        ch = reader.lookup_ch()

        if ch not in self.expected:
            raise LiteralExpected(list(self.expected.keys()), reader)

        return self.expected[ch]()

    def next_variables(self):
        del self.expected['(']
        return VariablesParser(self.variables), 0

    def next_directives(self):
        del self.expected['(']
        del self.expected['@']
        DirectivesParser(self.directives), 0

    def next_selections(self):
        self.expected.clear()
        return SelectionsParser(self.selections), 0

    def to_dict(self):
        d = {
            "type": self.operation_type
        }
        add_if_not_none(d, "name", self.name)
        add_if_not_empty(d, "vars", self.variables)
        add_if_not_empty(d, "dirs", self.directives)
        add_if_not_empty(d, "sels", self.selections)
        return d


class VariablesParser(ElementParser):
    def __init__(self, variables: List[VariableDefinition]):
        self.variables = variables

    def consume(self, reader):
        self.assert_ch(reader, "(")

    def next(self, reader: Reader):
        ch = reader.lookup_ch()

        if ch == "$":
            return VariableDefinitionParser(self.variables), 0

        if ch == ")":
            if len(self.variables) == 0:
                raise ParsingError("Empty variable definition is not allowed", reader)
            reader.next_ch()
            return None, 1

        raise LiteralExpected(["$", ")"], reader)


class VariableDefinitionParser(ElementParser):
    type: Optional[Type]

    def __init__(self, variables: List[VariableDefinition]):
        self.variables = variables

        self.name = None
        self.type = None
        self.default = None

        self.default_checked = False

    def consume(self, reader: Reader):
        self.assert_ch(reader, "$")

        self.name = self.read_name(reader)

        self.assert_ch(reader, ":")

        self.type = self.parse_type(reader)

    def parse_type(self, reader: Reader):
        ch = reader.lookup_ch()

        if ch == "[":
            return self.parse_list_type(reader)

        type_name = self.read_name(reader)

        return NamedType(type_name, not self.read_if(reader, "!"))

    def parse_list_type(self, reader: Reader):
        self.assert_ch(reader, "[")

        el_type = self.parse_type(reader)

        self.assert_ch(reader, "]")

        return ListType(el_type, not self.read_if(reader, "!"))

    def next(self, reader: Reader):
        if not self.default_checked:
            self.default_checked = True

            if self.read_if(reader, "="):
                def set_default(v):
                    self.default = v

                return ValueParser(set_default, True), 0

        self.variables.append(VariableDefinition(self.name, self.type, self.default))

        return None, 1

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        add_if_not_none(d, "name", self.name)

        if self.type is not None:
            d["type"] = self.type.to_primitive()

        add_if_not_none(d, "default", self.default)
        return d


class DirectivesParser(ElementParser):
    def __init__(self, directives: List[Directive]):
        self.directives = directives

    def consume(self, reader: Reader):
        pass

    def next(self, reader: Reader):
        if reader.lookup_ch() == "@":
            return DirectiveParser(self.directives), 0

        return None, 1


class DirectiveParser(ElementParser):
    def __init__(self, directives: List[Directive]):
        self.directives = directives

        self.name = None
        self.arguments = []

        self.arguments_checked = False

    def consume(self, reader: Reader):
        self.assert_ch(reader, "@")

        self.name = self.read_name(reader)

    def next(self, reader: Reader):
        if not self.arguments_checked:
            self.arguments_checked = True

            if reader.lookup_ch() == "(":
                return ArgumentsParser(self.arguments), 0

        self.directives.append(Directive(self.name, self.arguments))
        return None, 1


class ArgumentsParser(ElementParser):
    def __init__(self, arguments: List[Argument]):
        self.arguments = arguments

    def consume(self, reader: Reader):
        self.assert_ch(reader, "(")

    def next(self, reader: Reader):
        if self.read_if(reader, ")"):
            if len(self.arguments) == 0:
                raise ParsingError("Empty arguments list is not allowed", reader)

            return None, 1

        return ArgumentParser(self.arguments), 0


class ArgumentParser(ElementParser):
    def __init__(self, arguments: List[Argument]):
        self.arguments = arguments

        self.name = None
        self.value = None

        self.value_parsed = False

    def consume(self, reader: Reader):
        self.name = self.read_name(reader)

        self.assert_ch(reader, ":")

    def next(self, reader: Reader):
        if self.value_parsed:
            self.arguments.append(Argument(self.name, self.value))
            return None, 1

        self.value_parsed = True

        def set_value(v):
            self.value = v

        return ValueParser(set_value, False), 0

    def to_dbg_repr(self):
        d = super().to_dbg_repr()

        add_if_not_none(d, "name", self.name)

        if self.value is not None:
            d["value"] = to_primitive(self.value)

        return d


class SelectionsParser(ElementParser):
    DETECT_FRAGMENT_SPREAD_RE = re.compile(r'\.\.\.[ \t]+([_A-Za-z][_0-9A-Za-z]*)')

    def __init__(self, selections: List[Selection]):
        self.selections = selections

    def consume(self, reader: Reader):
        self.assert_ch(reader, "{")

    def next(self, reader: Reader):
        if self.read_if(reader, "}"):

            if len(self.selections) == 0:
                raise ParsingError("Empty selection set is not allowed", reader)

            return None, 1

        if reader.lookup_ch() == ".":
            m = reader.match_re(self.DETECT_FRAGMENT_SPREAD_RE)
            if m is not None and m.group(1) != "on":
                return FragmentSpreadParser(self.selections), 0
            return InlineFragmentParser(self.selections), 0

        return FieldParser(self.selections), 0


class FieldParser(ElementParser):
    def __init__(self, selections: List[Selection]):
        self.parent_selections = selections

        self.alias = None
        self.name = None
        self.arguments = []
        self.directives = []
        self.selections = []

        self.can_be = {
            '(': self.next_arguments,
            '@': self.next_directives,
            '{': self.next_selections
        }

    def consume(self, reader: Reader):
        name = self.read_name(reader)

        if self.read_if(reader, ":"):
            self.alias = name
            self.name = self.read_name(reader)
        else:
            self.name = name

    def next(self, reader: Reader):
        ch = reader.lookup_ch()

        if ch in self.can_be:
            return self.can_be[ch]()

        self.parent_selections.append(Field(self.alias, self.name, self.arguments, self.directives, self.selections))

        return None, 1

    def next_arguments(self):
        del self.can_be['(']
        return ArgumentsParser(self.arguments), 0

    def next_directives(self):
        del self.can_be['(']
        del self.can_be['@']
        return DirectivesParser(self.directives), 0

    def next_selections(self):
        self.can_be.clear()
        return SelectionsParser(self.selections), 0

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        add_if_not_none(d, "name", self.name)
        add_if_not_none(d, "alias", self.alias)
        add_if_not_empty(d, "args", self.arguments)
        add_if_not_empty(d, "dirs", self.directives)
        add_if_not_empty(d, "sels", self.selections)
        return d


class ValueParser(ElementParser):
    INT_PART = r'-?(?:[1-9][0-9]+|0)'
    FR_PART = r'(?:\.[0-9]+)'
    EXP_PART = r'(?:[eE][+-]?[0-9]+)'
    INT_RE = re.compile(INT_PART)
    FLOAT_RE = re.compile(INT_PART + r'(?:' + FR_PART + EXP_PART + '?|' + EXP_PART + ')')

    def __init__(self, set_value, const=False):
        self.set_value = set_value
        self.const = const

    def consume(self, reader: Reader):
        pass

    def next(self, reader: Reader):
        ch = reader.lookup_ch()

        if ch == "$":
            if self.const:
                raise ParsingError("Unexpected '$'", reader)

            self.assert_ch(reader, "$")
            name = self.read_name(reader)

            self.set_value(Variable(name))

            return None, 1

        if ch == '"':
            return StringValueParser(self.set_value), 1

        if ch == "[":
            return ListValueParser(self.set_value, self.const), 1

        if ch == "{":
            return ObjectValueParser(self.set_value, self.const), 1

        if self.try_literal(reader, "true"):
            self.set_value(True)
            return None, 1

        if self.try_literal(reader, "false"):
            self.set_value(True)
            return None, 1

        if self.try_literal(reader, "null"):
            self.set_value(NullValue())
            return None, 1

        v = reader.next_re(NAME_RE)
        if v is not None:
            self.set_value(EnumValue(v))
            return None, 1

        v = reader.next_re(self.FLOAT_RE)
        if v is not None:
            self.set_value(float(v))
            return None, 1

        v = reader.next_re(self.INT_RE)
        if v is not None:
            self.set_value(int(v))
            return None, 1

        raise ParsingError("Value expected", reader)


class ListValueParser(ElementParser):
    def __init__(self, set_value, const):
        self.set_value = set_value
        self.const = const

        self.values = []

    def consume(self, reader: Reader):
        self.assert_ch(reader, "[")

    def next(self, reader: Reader):
        if self.read_if(reader, "]"):
            if self.const:
                self.set_value(ConstListValue(self.values))
            else:
                self.set_value(ListValue(self.values))

            return None, 1

        return ValueParser(self.append_value, self.const)

    def append_value(self, v):
        self.values.append(v)

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        d["values"] = [to_primitive(v) for v in self.values]
        return d


class ObjectValueParser(ElementParser):
    def __init__(self, set_value, const):
        self.set_value = set_value
        self.const = const

        self.values = {}

    def consume(self, reader: Reader):
        self.assert_ch(reader, "{")

    def next(self, reader: Reader):
        if self.read_if(reader, "}"):
            if self.const:
                self.set_value(ConstObjectValue(self.values))
            else:
                self.set_value(ObjectValue(self.values))

            return None, 1

        name = self.read_name(reader)

        self.assert_ch(reader, ":")

        return ValueParser(self.add_value(name), self.const)

    def add_value(self, name):
        def add(v):
            self.values[name] = v

        return add

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        d["values"] = dict(((k, to_primitive(v)) for k, v in self.values.items()))
        return d


class StringValueParser(ElementParser):
    HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

    def __init__(self, set_value):
        self.set_value = set_value

        self.value = ""

    def consume(self, reader: Reader):
        self.assert_ch(reader, '"')

    def next(self, reader: Reader):
        while True:
            ch = reader.str_next_ch()

            if ch == '"':
                self.set_value(self.value)
                return None, 1

            if ch == '\\':
                self.value += self.parse_escape(reader)
                continue

            if ch in {"\n", "\r"}:
                raise ParsingError("New line is not allowed in string literal", reader)

            if ch is None:
                raise ParsingError("Unexpected end of input", reader)

            self.value += ch

    def parse_escape(self, reader):
        ch = reader.str_next_ch()

        if ch == "u":
            return self.parse_unicode(reader)

        if ch == '"':
            return '"'

        if ch == '\\':
            return '\\'

        if ch == '/':
            return '/'

        if ch == 'b':
            return '\b'

        if ch == 'f':
            return '\f'

        if ch == 'n':
            return '\n'

        if ch == 'r':
            return '\r'

        if ch == 't':
            return '\t'

        raise ParsingError("Unexpected symbol '{}' after '\\' in string literal".format(ch), reader)

    def parse_unicode(self, reader):
        digits = []

        for i in range(4):
            digits.append(self.parse_hex_digit(reader))

        return chr(int(''.join(digits), 16))

    def parse_hex_digit(self, reader):
        ch = reader.str_next_ch()

        if ch in self.HEX_DIGITS:
            return ch

        raise ParsingError("Hex digit expected", reader)

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        d["value"] = self.value
        return d


class FragmentSpreadParser(ElementParser):
    def __init__(self, selections: List[Selection]):
        self.selections = selections

        self.name = None
        self.directives = []

    def consume(self, reader: Reader):
        self.assert_literal(reader, "...")

        self.name = self.read_name(reader)

    def next(self, reader: Reader):
        if reader.lookup_ch() == '@':
            return DirectivesParser(self.directives), 0

        self.selections.append(FragmentSpread(self.name, self.directives))

        return None, 1

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        add_if_not_none(d, "name", self.name)
        add_if_not_empty(d, "dirs", self.directives)


class InlineFragmentParser(ElementParser):
    on_type: Optional[NamedType]

    def __init__(self, selections: List[Selection]):
        self.parent_selections = selections

        self.on_type = None
        self.directives = []
        self.selections = []

        self.directives_parsed = False
        self.selections_parsed = False

    def consume(self, reader: Reader):
        self.assert_literal(reader, "...")

        if self.try_literal(reader, "on"):
            type_name = self.read_name(reader)

            self.on_type = NamedType(type_name, True)

    def next(self, reader: Reader):
        if not self.directives_parsed and reader.lookup_ch() == "@":
            self.directives_parsed = True
            return DirectivesParser(self.directives), 0

        if not self.selections_parsed:
            self.directives_parsed = True
            self.selections_parsed = True
            return SelectionsParser(self.selections), 0

        self.parent_selections.append(InlineFragment(self.on_type, self.directives, self.selections))
        return None, 1

    def to_dbg_repr(self):
        d = super().to_dbg_repr()

        if self.on_type is not None:
            d["on_type"] = self.on_type.to_primitive()

        add_if_not_empty(d, "dirs", self.directives)
        add_if_not_empty(d, "sels", self.selections)

        return d


class FragmentParser(ElementParser):
    def __init__(self, fragments: List[Fragment]):
        self.fragments = fragments

        self.name = None
        self.on_type = None
        self.directives = []
        self.selections = []

        self.directives_parsed = False
        self.selections_parsed = False

    def consume(self, reader: Reader):
        self.assert_literal(reader, "fragment")

        self.name = self.read_name(reader)

        if self.name == "on":
            raise ParsingError("Fragment can not have name \"on\"", reader)

        self.assert_literal(reader, "on")

        type_name = self.read_name(reader)

        self.on_type = NamedType(type_name, True)

    def next(self, reader: Reader):
        if not self.directives_parsed and reader.lookup_ch() == "@":
            self.directives_parsed = True
            return DirectivesParser(self.directives), 0

        if not self.selections_parsed:
            self.directives_parsed = True
            self.selections_parsed = True
            return SelectionsParser(self.selections), 0

        self.fragments.append(Fragment(self.name, self.on_type, self.directives, self.selections))
        return None, 1

    def to_dbg_repr(self):
        d = super().to_dbg_repr()

        add_if_not_none(d, "name", self.name)

        if self.on_type is not None:
            d["on_type"] = self.on_type.to_primitive()

        add_if_not_empty(d, "dirs", self.directives)
        add_if_not_empty(d, "sels", self.selections)

        return d
