import json
import logging
import re
import typing as t

import gql_alchemy.gql_query_model as qm
from .gql_errors import GqlParsingError
from .raw_reader import Reader, format_position
from .utils import PrimitiveType, add_if_not_empty, add_if_not_none

logger = logging.getLogger("gql_alchemy")


def log_stack(stack: t.Sequence['ElementParser']):
    if not logger.isEnabledFor(logging.DEBUG):
        return

    logger.debug("Stack: %s", json.dumps([i.to_dbg_repr() for i in stack]))


def log_position(reader: Reader):
    if not logger.isEnabledFor(logging.DEBUG):
        return

    lineno = reader.lineno
    line_pos = reader.line_pos()
    lines = [reader.prev_line(), reader.current_line(), reader.next_line()]

    for line in format_position(lineno, line_pos, lines):
        logger.debug(line)


def parse_document(text_input: str) -> qm.Document:
    document = []

    def set_document(d):
        document.append(d)

    parser = DocumentParser(set_document)

    parse(text_input, parser)

    return document[0]


def push_to_stack(stack: t.List['ElementParser'], parser: 'ElementParser', reader: Reader):
    stack.append(parser)

    log_stack(stack)

    index_before = reader.index
    parser.consume(reader)
    index_after = reader.index

    if index_after != index_before:
        logger.debug("READ DETECTED")
        log_position(reader)
        log_stack(stack)


def parse(text_input: str, initial_parser: 'ElementParser'):
    stack: t.List[ElementParser] = []
    reader = Reader(text_input)

    logger.debug("=== START PARSING ===")
    logger.debug("INPUT\n%s\n===", text_input)
    push_to_stack(stack, initial_parser, reader)

    while True:
        if len(stack) == 0:
            logger.debug("=== FINISH PARSING ===")
            log_stack(stack)

            if reader.lookup_ch() is not None:
                log_position(reader)
                raise GqlParsingError("Not all input parsed", reader)

            logger.debug("EOI")
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
            log_position(reader)
            log_stack(stack)

        if remove_count > 0:
            stack[-remove_count:] = []
            log_stack(stack)

        if to_add is not None:
            push_to_stack(stack, to_add, reader)


class LiteralExpected(GqlParsingError):
    def __init__(self, symbols: t.Sequence[str], reader: Reader) -> None:
        if len(symbols) == 1:
            msg = "Expected '{}'".format(symbols[0])
        else:
            msg = "One of {} and {} expected".format(
                ', '.join(('"{}"'.format(s) for s in symbols[:-1])),
                '"{}"'.format(symbols[-1]))
        super().__init__(msg, reader)
        self.symbols = symbols


NAME_RE = re.compile(r'[_A-Za-z][_0-9A-Za-z]*')


class ElementParser:
    @staticmethod
    def assert_ch(reader: Reader, ch: str):
        next_ch = reader.read_ch()
        if next_ch != ch:
            raise LiteralExpected([ch], reader)

    @staticmethod
    def assert_literal(reader: Reader, literal: str):
        next_literal = reader.read_re(re.compile(r'(?:' + literal + r')(?=[^_0-9A-Za-z]|$)'))
        if next_literal is None:
            raise LiteralExpected([literal], reader)

    @staticmethod
    def try_literal(reader: Reader, literal: str):
        next_literal = reader.read_re(re.compile(r'(?:' + literal + r')(?=[^_0-9A-Za-z]|$)'))
        return next_literal is not None

    @staticmethod
    def read_if(reader: Reader, ch: str):
        next_ch = reader.lookup_ch()

        if next_ch == ch:
            reader.read_ch()
            return True

        return False

    @staticmethod
    def read_name(reader: Reader):
        name = reader.read_re(NAME_RE)

        if name is None:
            raise GqlParsingError("Name expected (forgot to finish selections by '}'?)", reader)

        return name

    def consume(self, reader: Reader):
        raise NotImplementedError()

    def next(self, reader: Reader) -> t.Tuple[t.Optional['ElementParser'], int]:
        raise NotImplementedError()

    def to_dbg_repr(self) -> PrimitiveType:
        return {
            "parser": type(self).__name__
        }


class DocumentParser(ElementParser):
    def __init__(self, set_document) -> None:
        self.set_document = set_document

        self.operations: t.List[qm.Operation] = []
        self.fragments: t.List[qm.Fragment] = []
        self.selections: t.List[qm.Selection] = []

        self.selection_allowed = True
        self.query_allowed = True

    def consume(self, reader: Reader):
        pass

    def next(self, reader):
        if len(self.selections) > 0:
            self.operations.append(qm.Query(None, [], [], self.selections))
            self.selections = []

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
            self.set_document(qm.Document(self.operations, self.fragments))
            return None, 1

        raise GqlParsingError("One of top-level declaration expected", reader)

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        add_if_not_empty(d, "ops", self.operations)
        add_if_not_empty(d, "frgs", self.fragments)
        add_if_not_empty(d, "sels", self.selections)
        return d


class OperationParser(ElementParser):
    variables: t.List[qm.VariableDefinition]
    directives: t.List[qm.Directive]
    selections: t.List[qm.Selection]

    def __init__(self, operation_type, operations: t.List[qm.Operation]) -> None:
        self.operation_type = operation_type
        self.operations = operations

        self.name: t.Optional[str] = None
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
            name = reader.read_re(NAME_RE)
            if name is None:
                raise GqlParsingError("One of `name`, '(', '@' or '{' expected", reader)
            self.name = name

    def next(self, reader):

        if len(self.expected) == 0:
            if self.operation_type == "query":
                self.operations.append(qm.Query(self.name, self.variables, self.directives, self.selections))
            else:
                self.operations.append(qm.Mutation(self.name, self.variables, self.directives, self.selections))
            return None, 1

        ch = reader.lookup_ch()

        if ch not in self.expected:
            raise LiteralExpected(list(self.expected.keys()), reader)

        return self.expected[ch]()

    def next_variables(self):
        del self.expected['(']
        return VariablesParser(self.variables), 0

    def next_directives(self):
        if '(' in self.expected:
            del self.expected['(']
        del self.expected['@']
        return DirectivesParser(self.directives), 0

    def next_selections(self):
        self.expected.clear()
        return SelectionsParser(self.selections), 0

    def to_dbg_repr(self):
        d = {
            "type": self.operation_type
        }
        add_if_not_none(d, "name", self.name)
        add_if_not_empty(d, "vars", self.variables)
        add_if_not_empty(d, "dirs", self.directives)
        add_if_not_empty(d, "sels", self.selections)
        return d


class VariablesParser(ElementParser):
    def __init__(self, variables: t.List[qm.VariableDefinition]) -> None:
        self.variables = variables

    def consume(self, reader):
        self.assert_ch(reader, "(")

    def next(self, reader: Reader):
        ch = reader.lookup_ch()

        if ch == "$":
            return VariableDefinitionParser(self.variables), 0

        if ch == ")":
            if len(self.variables) == 0:
                raise GqlParsingError("Empty variable definition is not allowed", reader)
            reader.read_ch()
            return None, 1

        raise LiteralExpected(["$", ")"], reader)


class VariableDefinitionParser(ElementParser):
    type: t.Optional[qm.Type]

    def __init__(self, variables: t.List[qm.VariableDefinition]) -> None:
        self.variables = variables

        self.name: t.Optional[str] = None
        self.type: t.Optional[qm.Type] = None
        self.default: t.Optional[qm.ConstValue] = None

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

        return qm.NamedType(type_name, not self.read_if(reader, "!"))

    def parse_list_type(self, reader: Reader):
        self.assert_ch(reader, "[")

        el_type = self.parse_type(reader)

        self.assert_ch(reader, "]")

        return qm.ListType(el_type, not self.read_if(reader, "!"))

    def next(self, reader: Reader):
        if not self.default_checked:
            self.default_checked = True

            if self.read_if(reader, "="):
                def set_default(v):
                    self.default = v

                return ValueParser(set_default, True), 0

        if self.name is None or self.type is None:
            raise RuntimeError("Unexpected `None`")

        self.variables.append(qm.VariableDefinition(self.name, self.type, self.default))

        return None, 1

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        add_if_not_none(d, "name", self.name)

        if self.type is not None:
            d["type"] = self.type.to_primitive()

        if self.default is not None:
            d["default"] = self.default.to_primitive()
        return d


class DirectivesParser(ElementParser):
    def __init__(self, directives: t.List[qm.Directive]) -> None:
        self.directives = directives

    def consume(self, reader: Reader):
        pass

    def next(self, reader: Reader):
        if reader.lookup_ch() == "@":
            return DirectiveParser(self.directives), 0

        return None, 1


class DirectiveParser(ElementParser):
    def __init__(self, directives: t.List[qm.Directive]) -> None:
        self.directives = directives

        self.name = None
        self.arguments: t.List[qm.Argument] = []

        self.arguments_checked = False

    def consume(self, reader: Reader):
        self.assert_ch(reader, "@")

        self.name = self.read_name(reader)

    def next(self, reader: Reader):
        if not self.arguments_checked:
            self.arguments_checked = True

            if reader.lookup_ch() == "(":
                return ArgumentsParser(self.arguments), 0

        if self.name is None:
            raise RuntimeError("Unexpected `None`")

        self.directives.append(qm.Directive(self.name, self.arguments))
        return None, 1


class ArgumentsParser(ElementParser):
    def __init__(self, arguments: t.List[qm.Argument]) -> None:
        self.arguments = arguments

    def consume(self, reader: Reader):
        self.assert_ch(reader, "(")

    def next(self, reader: Reader):
        if self.read_if(reader, ")"):
            if len(self.arguments) == 0:
                raise GqlParsingError("Empty arguments list is not allowed", reader)

            return None, 1

        return ArgumentParser(self.arguments), 0


class ArgumentParser(ElementParser):
    def __init__(self, arguments: t.List[qm.Argument]) -> None:
        self.arguments = arguments

        self.name: t.Optional[str] = None
        self.value: t.Optional[qm.Value] = None

        self.value_parsed = False

    def consume(self, reader: Reader):
        self.name = self.read_name(reader)

        self.assert_ch(reader, ":")

    def next(self, reader: Reader):
        if self.value_parsed:

            if self.name is None or self.value is None:
                raise RuntimeError("Unexpected `None`")

            self.arguments.append(qm.Argument(self.name, self.value))

            return None, 1

        self.value_parsed = True

        def set_value(v):
            self.value = v

        return ValueParser(set_value, False), 0

    def to_dbg_repr(self):
        d = super().to_dbg_repr()

        add_if_not_none(d, "name", self.name)

        if self.value is not None:
            d["value"] = self.value.to_primitive()

        return d


class SelectionsParser(ElementParser):
    DETECT_FRAGMENT_SPREAD_RE = re.compile(r'\.\.\.[ \t]+([_A-Za-z][_0-9A-Za-z]*)')

    def __init__(self, selections: t.List[qm.Selection]) -> None:
        self.selections = selections

    def consume(self, reader: Reader):
        self.assert_ch(reader, "{")

    def next(self, reader: Reader):
        if self.read_if(reader, "}"):

            if len(self.selections) == 0:
                raise GqlParsingError("Empty selection set is not allowed", reader)

            return None, 1

        if reader.lookup_ch() == ".":
            m = reader.match_re(self.DETECT_FRAGMENT_SPREAD_RE)
            if m is not None and m.group(1) != "on":
                return FragmentSpreadParser(self.selections), 0
            return InlineFragmentParser(self.selections), 0

        return FieldParser(self.selections), 0


class FieldParser(ElementParser):
    def __init__(self, selections: t.List[qm.Selection]) -> None:
        self.parent_selections = selections

        self.alias: t.Optional[str] = None
        self.name: t.Optional[str] = None
        self.arguments: t.List[qm.Argument] = []
        self.directives: t.List[qm.Directive] = []
        self.selections: t.List[qm.Selection] = []

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

        if self.name is None:
            raise RuntimeError("Unexpected `None`")

        self.parent_selections.append(qm.FieldSelection(self.alias, self.name, self.arguments, self.directives,
                                                        self.selections))

        return None, 1

    def next_arguments(self):
        del self.can_be['(']
        return ArgumentsParser(self.arguments), 0

    def next_directives(self):
        if '(' in self.can_be:
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
    INT_PART = r'-?(?:[1-9][0-9]*|0)'
    FR_PART = r'(?:\.[0-9]+)'
    EXP_PART = r'(?:[eE][+-]?[0-9]+)'
    INT_RE = re.compile(INT_PART)
    FLOAT_RE = re.compile(INT_PART + r'(?:' + FR_PART + EXP_PART + '?|' + EXP_PART + ')')

    def __init__(self, set_value, const=False) -> None:
        self.set_value = set_value
        self.const = const

    def consume(self, reader: Reader):
        pass

    def next(self, reader: Reader):
        ch = reader.lookup_ch()

        if ch == "$":
            if self.const:
                raise GqlParsingError("Unexpected '$'", reader)

            self.assert_ch(reader, "$")
            name = self.read_name(reader)

            self.set_value(qm.Variable(name))

            return None, 1

        if ch == '"':
            return StringValueParser(self.set_value), 1

        if ch == "[":
            return ListValueParser(self.set_value, self.const), 1

        if ch == "{":
            return ObjectValueParser(self.set_value, self.const), 1

        if self.try_literal(reader, "true"):
            self.set_value(qm.BoolValue(True))
            return None, 1

        if self.try_literal(reader, "false"):
            self.set_value(qm.BoolValue(False))
            return None, 1

        if self.try_literal(reader, "null"):
            self.set_value(qm.NullValue())
            return None, 1

        v = reader.read_re(NAME_RE)
        if v is not None:
            self.set_value(qm.EnumValue(v))
            return None, 1

        v = reader.read_re(self.FLOAT_RE)
        if v is not None:
            self.set_value(qm.FloatValue(float(v)))
            return None, 1

        v = reader.read_re(self.INT_RE)
        if v is not None:
            self.set_value(qm.IntValue(int(v)))
            return None, 1

        raise GqlParsingError("Value expected", reader)


class ListValueParser(ElementParser):
    def __init__(self, set_value, const) -> None:
        self.set_value = set_value
        self.const = const

        self.values: t.List[qm.Value] = []

    def consume(self, reader: Reader):
        self.assert_ch(reader, "[")

    def next(self, reader: Reader):
        if self.read_if(reader, "]"):
            if self.const:
                self.set_value(qm.ConstListValue(self.values))  # type: ignore
            else:
                self.set_value(qm.ListValue(self.values))

            return None, 1

        return ValueParser(self.append_value, self.const), 0

    def append_value(self, v):
        self.values.append(v)

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        add_if_not_empty(d, "values", self.values)
        return d


class ObjectValueParser(ElementParser):
    def __init__(self, set_value, const) -> None:
        self.set_value = set_value
        self.const = const

        self.values: t.Dict[str, qm.Value] = {}

    def consume(self, reader: Reader):
        self.assert_ch(reader, "{")

    def next(self, reader: Reader):
        if self.read_if(reader, "}"):
            if self.const:
                self.set_value(qm.ConstObjectValue(self.values))  # type: ignore
            else:
                self.set_value(qm.ObjectValue(self.values))

            return None, 1

        name = self.read_name(reader)

        self.assert_ch(reader, ":")

        return ValueParser(self.add_value(name), self.const), 0

    def add_value(self, name):
        def add(v):
            self.values[name] = v

        return add

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        d["values"] = dict(((k, v.to_primitive()) for k, v in self.values.items()))
        return d


class StringValueParser(ElementParser):
    HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

    def __init__(self, set_value) -> None:
        self.set_value = set_value

        self.value = ""

    def consume(self, reader: Reader):
        self.assert_ch(reader, '"')

    def next(self, reader: Reader):
        while True:
            ch = reader.str_read_ch()

            if ch == '"':
                self.set_value(qm.StrValue(self.value))
                return None, 1

            if ch == '\\':
                self.value += self.parse_escape(reader)
                continue

            if ch in {"\n", "\r"}:
                raise GqlParsingError("New line is not allowed in string literal", reader)

            if ch is None:
                raise GqlParsingError("Unexpected end of input", reader)

            self.value += ch

    def parse_escape(self, reader: Reader):
        ch = reader.str_read_ch()

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

        raise GqlParsingError("Unexpected symbol '{}' after '\\' in string literal".format(ch), reader)

    def parse_unicode(self, reader):
        digits = []

        for i in range(4):
            digits.append(self.parse_hex_digit(reader))

        return chr(int(''.join(digits), 16))

    def parse_hex_digit(self, reader: Reader):
        ch = reader.str_read_ch()

        if ch in self.HEX_DIGITS:
            return ch

        raise GqlParsingError("Hex digit expected", reader)

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        d["value"] = self.value
        return d


class FragmentSpreadParser(ElementParser):
    def __init__(self, selections: t.List[qm.Selection]) -> None:
        self.selections = selections

        self.name: t.Optional[str] = None
        self.directives: t.List[qm.Directive] = []

    def consume(self, reader: Reader):
        self.assert_literal(reader, "...")

        self.name = self.read_name(reader)

    def next(self, reader: Reader):
        if reader.lookup_ch() == '@':
            return DirectivesParser(self.directives), 0

        if self.name is None:
            raise RuntimeError("Unexpected `None`")

        self.selections.append(qm.FragmentSpread(self.name, self.directives))

        return None, 1

    def to_dbg_repr(self):
        d = super().to_dbg_repr()
        add_if_not_none(d, "name", self.name)
        add_if_not_empty(d, "dirs", self.directives)


class InlineFragmentParser(ElementParser):
    on_type: t.Optional[qm.NamedType]

    def __init__(self, selections: t.List[qm.Selection]) -> None:
        self.parent_selections = selections

        self.on_type: t.Optional[qm.NamedType] = None
        self.directives: t.List[qm.Directive] = []
        self.selections: t.List[qm.Selection] = []

        self.directives_parsed = False
        self.selections_parsed = False

    def consume(self, reader: Reader):
        self.assert_literal(reader, "...")

        if self.try_literal(reader, "on"):
            type_name = self.read_name(reader)

            self.on_type = qm.NamedType(type_name, True)

    def next(self, reader: Reader):
        if not self.directives_parsed and reader.lookup_ch() == "@":
            self.directives_parsed = True
            return DirectivesParser(self.directives), 0

        if not self.selections_parsed:
            self.directives_parsed = True
            self.selections_parsed = True
            return SelectionsParser(self.selections), 0

        self.parent_selections.append(qm.InlineFragment(self.on_type, self.directives, self.selections))
        return None, 1

    def to_dbg_repr(self):
        d = super().to_dbg_repr()

        if self.on_type is not None:
            d["on_type"] = self.on_type.to_primitive()

        add_if_not_empty(d, "dirs", self.directives)
        add_if_not_empty(d, "sels", self.selections)

        return d


class FragmentParser(ElementParser):
    def __init__(self, fragments: t.List[qm.Fragment]) -> None:
        self.fragments = fragments

        self.name: t.Optional[str] = None
        self.on_type: t.Optional[qm.NamedType] = None
        self.directives: t.List[qm.Directive] = []
        self.selections: t.List[qm.Selection] = []

        self.directives_parsed = False
        self.selections_parsed = False

    def consume(self, reader: Reader):
        self.assert_literal(reader, "fragment")

        self.name = self.read_name(reader)

        if self.name == "on":
            raise GqlParsingError("Fragment can not have name \"on\"", reader)

        self.assert_literal(reader, "on")

        type_name = self.read_name(reader)

        self.on_type = qm.NamedType(type_name, True)

    def next(self, reader: Reader):
        if not self.directives_parsed and reader.lookup_ch() == "@":
            self.directives_parsed = True
            return DirectivesParser(self.directives), 0

        if not self.selections_parsed:
            self.directives_parsed = True
            self.selections_parsed = True
            return SelectionsParser(self.selections), 0

        if self.name is None or self.on_type is None:
            raise RuntimeError("Unexpected `None`")

        self.fragments.append(qm.Fragment(self.name, self.on_type, self.directives, self.selections))
        return None, 1

    def to_dbg_repr(self):
        d = super().to_dbg_repr()

        add_if_not_none(d, "name", self.name)

        if self.on_type is not None:
            d["on_type"] = self.on_type.to_primitive()

        add_if_not_empty(d, "dirs", self.directives)
        add_if_not_empty(d, "sels", self.selections)

        return d


__all__ = ["parse_document", "parse", "ElementParser", "DocumentParser", "OperationParser", "VariablesParser",
           "VariableDefinitionParser", "DirectivesParser", "DirectiveParser", "ArgumentsParser",
           "ArgumentParser", "SelectionsParser", "FieldParser", "ValueParser", "ListValueParser",
           "ObjectValueParser", "StringValueParser", "FragmentSpreadParser", "InlineFragmentParser",
           "FragmentParser"]
