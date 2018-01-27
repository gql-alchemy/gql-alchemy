import json
import logging
import typing as t
import unittest

import gql_alchemy.gql_errors as e
import gql_alchemy.gql_query_model as qm
from gql_alchemy.gql_parser import *

logger = logging.getLogger("gql_alchemy")
logger.setLevel(logging.DEBUG)
# sh = logging.StreamHandler()
# sh.setLevel(logging.DEBUG)
# logger.addHandler(sh)


class ParsingTest(unittest.TestCase):
    def init_parser(self) -> ElementParser:
        raise NotImplementedError()

    def get_result(self) -> t.Union[qm.GraphQlModelType, t.List[qm.GraphQlModelType]]:
        raise NotImplementedError()

    def assertParserResult(self, expected: str, query: str):
        parser = self.init_parser()
        parse(query, parser)
        result = self.get_result()
        self.assertEqual(expected, json.dumps(result.to_primitive(), sort_keys=True))

    def assertParserError(self, lineno: int, query: str):
        parser = self.init_parser()
        with self.assertRaises(e.GqlParsingError) as cm:
            parse(query, parser)
        self.assertEqual(lineno, cm.exception.lineno)

    def assertParserResults(self, query: str, *expected: str):
        parser = self.init_parser()
        parse(query, parser)
        result = self.get_result()
        self.assertEqual(len(expected), len(result))
        for e, r in zip(expected, result):
            self.assertEqual(e, json.dumps(r.to_primitive(), sort_keys=True))

    def assertDocument(self, expected: str, query: str):
        d = parse_document(query)
        self.assertEqual(expected, json.dumps(d.to_primitive(), sort_keys=True))

    def assertDocumentError(self, lineno: int, query: str):
        with self.assertRaises(e.GqlParsingError) as cm:
            parse_document(query)
        self.assertEqual(lineno, cm.exception.lineno)


class DocumentParserTest(ParsingTest):
    maxDiff = None

    def test_shortcut_form(self):
        self.assertDocument(
            '{"@doc": null, "operations": [{"@q": null, "selections": [{"@f": "id"}, {"@f": "name"}]}]}',
            "{ id name }"
        )

        self.assertDocument(
            '{"@doc": null, "operations": [{"@q": null, "selections": ['
            '{"@f": "user", "selections": [{"@f": "id"}, {"@f": "name"}]}]}]}',
            "{ user {id name} }"
        )

        self.assertDocument(
            '{"@doc": null, "operations": ['
            '{"@q": null, "selections": [{"@f": "id"}]}, '
            '{"@m": null, "selections": [{"@f": "id"}]}]}',
            "{id} mutation {id}"
        )

        self.assertDocument(
            '{"@doc": null, "operations": ['
            '{"@m": null, "selections": [{"@f": "id"}]}, '
            '{"@q": null, "selections": [{"@f": "id"}]}]}',
            "mutation {id} {id}"
        )

        self.assertDocumentError(1, "{id} {id}")
        self.assertDocumentError(1, "query {id} {id}")
        self.assertDocumentError(1, "{id} query {id}")

    def test_query(self):
        self.assertDocument(
            '{"@doc": null, "operations": [{"@q": null, "selections": [{"@f": "id"}]}]}',
            "query { id }"
        )

    def test_mutation(self):
        self.assertDocument(
            '{"@doc": null, "operations": [{"@m": null, "selections": [{"@f": "id"}]}]}',
            "mutation { id }"
        )

    def test_fragment(self):
        self.assertDocument(
            '{"@doc": null, '
            '"fragments": [{"@frg": "foo", "on_type": {"@named": "Bar"}, "selections": [{"@f": "id"}]}]}',
            "fragment foo on Bar { id }"
        )

    def test_parse_many(self):
        self.assertDocument(
            '{"@doc": null, "fragments": ['
            '{"@frg": "foo", "on_type": {"@named": "Bar"}, "selections": [{"@f": "id"}]}, '
            '{"@frg": "foo1", "on_type": {"@named": "Bar"}, "selections": [{"@f": "id"}]}], "operations": ['
            '{"@q": null, "selections": [{"@f": "id"}]}, '
            '{"@q": null, "selections": [{"@f": "id"}]}, '
            '{"@q": null, "selections": [{"@f": "id"}]}, '
            '{"@m": null, "selections": [{"@f": "id"}]}, '
            '{"@m": null, "selections": [{"@f": "id"}]}]}',
            "query {id} query {id} query {id}"
            "mutation {id} mutation {id}"
            "fragment foo on Bar {id} fragment foo1 on Bar {id}"
        )
        self.assertDocument(
            '{"@doc": null, "fragments": ['
            '{"@frg": "foo", "on_type": {"@named": "Bar"}, "selections": [{"@f": "id"}]}, '
            '{"@frg": "foo1", "on_type": {"@named": "Bar"}, "selections": [{"@f": "id"}]}], "operations": ['
            '{"@q": null, "selections": [{"@f": "id"}]}, '
            '{"@m": null, "selections": [{"@f": "id"}]}, '
            '{"@q": null, "selections": [{"@f": "id"}]}, '
            '{"@m": null, "selections": [{"@f": "id"}]}, '
            '{"@q": null, "selections": [{"@f": "id"}]}]}',
            "query {id} mutation {id} query {id}"
            "mutation {id} fragment foo on Bar {id}"
            "query {id} fragment foo1 on Bar {id}"
        )

    def test_whitespaces(self):
        self.assertDocument(
            '{"@doc": null, "operations": [{"@q": null, "selections": [{"@f": "id"}]}]}',
            ",,query,,{,,,id,},"
        )
        self.assertDocument(
            '{"@doc": null, "operations": [{"@q": null, "selections": [{"@f": "id"}]}]}',
            "query{id}"
        )
        self.assertDocument(
            '{"@doc": null, "operations": [{"@q": null, "selections": [{"@f": "id"}]}]}',
            "  query   {  id  }   "
        )
        self.assertDocument(
            '{"@doc": null, "operations": [{"@q": null, "selections": [{"@f": "id"}]}]}',
            "\n\nquery\n\n{\n\n\nid\n}\n\n\n"
        )
        self.assertDocument(
            '{"@doc": null, "operations": [{"@q": null, "selections": [{"@f": "id"}]}]}',
            "\t\tquery\t\t{\t\t\tid\t}\t\t\t"
        )

    def test_comments(self):
        self.assertDocument(
            '{"@doc": null, "operations": [{"@q": null, "selections": [{"@f": "id"}]}]}',
            "# comment\n  #\nquery{id} # comment\n# query {foo}\n#\n# comment"
        )

    def test_failures(self):
        self.assertDocumentError(1, "sfs")
        self.assertDocumentError(1, "query{id} fds")
        self.assertDocumentError(1, "a query{id}")


class QueryOperationParserTest(ParsingTest):
    def init_parser(self):
        self.operations = []
        return OperationParser("query", self.operations)

    def get_result(self):
        return self.operations[0]

    def test_operation_type(self):
        self.assertParserResult(
            '{"@q": null, "selections": [{"@f": "foo"}]}',
            "query {foo}"
        )

        self.assertParserError(1, "mutation {foo}")

    def test_optionals(self):
        self.assertParserResult(
            '{"@q": null, "selections": [{"@f": "foo"}]}',
            "query {foo}"
        )
        self.assertParserResult(
            '{"@q": "foo", "directives": [{"@dir": "bar"}], "selections": [{"@f": "abc"}], '
            '"variables": [["id", {"@named": "Bar"}, null]]}',
            "query foo ($id: Bar) @bar {abc}"
        )
        self.assertParserResult(
            '{"@q": null, "directives": [{"@dir": "bar"}], "selections": [{"@f": "abc"}], '
            '"variables": [["id", {"@named": "Bar"}, null]]}',
            "query ($id: Bar) @bar {abc}"
        )
        self.assertParserResult(
            '{"@q": "foo", "directives": [{"@dir": "bar"}], "selections": [{"@f": "abc"}]}',
            "query foo @bar {abc}"
        )
        self.assertParserResult(
            '{"@q": "foo", "selections": [{"@f": "abc"}], "variables": [["id", {"@named": "Bar"}, null]]}',
            "query foo ($id: Bar) {abc}"
        )
        self.assertParserResult(
            '{"@q": "foo", "selections": [{"@f": "abc"}]}',
            "query foo {abc}"
        )
        self.assertParserResult(
            '{"@q": null, "selections": [{"@f": "abc"}], '
            '"variables": [["id", {"@named": "Bar"}, null]]}',
            "query ($id: Bar) {abc}"
        )
        self.assertParserResult(
            '{"@q": null, "directives": [{"@dir": "bar"}], "selections": [{"@f": "abc"}]}',
            "query @bar {abc}"
        )
        self.assertParserError(1, "query @bar foo {abc}")
        self.assertParserError(1, "query ($id: Bar) foo {abc}")
        self.assertParserError(1, "query @bar ($id: Bar) {abc}")

    def test_selections_required(self):
        self.assertDocumentError(
            1,
            """ query """
        )

    def test_no_empty_selections(self):
        self.assertDocumentError(
            1,
            """ query {}"""
        )

    def test_no_variables(self):
        self.assertDocumentError(
            1,
            """ query () {foo}"""
        )


class MutationOperationParserTest(ParsingTest):
    def init_parser(self):
        self.operations = []
        return OperationParser("mutation", self.operations)

    def get_result(self):
        return self.operations[0]

    def test_parse(self):
        self.assertParserResult(
            '{"@m": null, "selections": [{"@f": "foo"}]}',
            "mutation {foo}"
        )
        self.assertParserError(1, "query {foo}")


class VariablesParserTest(ParsingTest):
    def init_parser(self):
        self.variables = []
        return VariablesParser(self.variables)

    def get_result(self):
        return self.variables

    def test_parse(self):
        self.assertParserResults(
            "($foo: Bar)",
            '["foo", {"@named": "Bar"}, null]'
        )

        self.assertParserResults(
            "($foo: Bar = 3)",
            '["foo", {"@named": "Bar"}, {"@int": 3}]'
        )

        self.assertParserResults(
            "($foo: Bar!)",
            '["foo", {"@named!": "Bar"}, null]'
        )

        self.assertParserResults(
            "($foo: Bar! = 3)",
            '["foo", {"@named!": "Bar"}, {"@int": 3}]'
        )

        self.assertParserResults(
            "($foo: [Bar])",
            '["foo", {"@list": {"@named": "Bar"}}, null]'
        )

        self.assertParserResults(
            "($foo: [[Bar]])",
            '["foo", {"@list": {"@list": {"@named": "Bar"}}}, null]'
        )

        self.assertParserResults(
            "($foo: [Bar]!)",
            '["foo", {"@list!": {"@named": "Bar"}}, null]'
        )

        self.assertParserResults(
            "($foo: [[Bar!]!]!)",
            '["foo", {"@list!": {"@list!": {"@named!": "Bar"}}}, null]'
        )

        self.assertParserResults(
            "($foo: [Bar] = [3])",
            '["foo", {"@list": {"@named": "Bar"}}, {"@const-list": [{"@int": 3}]}]'
        )

        self.assertParserResults(
            "($foo: Bar = 3 $a: [B], $g: ggg)",
            '["foo", {"@named": "Bar"}, {"@int": 3}]',
            '["a", {"@list": {"@named": "B"}}, null]',
            '["g", {"@named": "ggg"}, null]'
        )

    def test_const(self):
        self.assertParserError(1, "$foo: Bar = $var")

    def test_error(self):
        self.assertParserError(1, "()")
        self.assertParserError(1, "(foo: Bar)")
        self.assertParserError(1, "($foo Bar)")
        self.assertParserError(1, "($foo Bar 3)")


class DirectivesParserTest(ParsingTest):
    def init_parser(self):
        self.directives = []
        return DirectivesParser(self.directives)

    def get_result(self):
        return self.directives

    def test_parse(self):
        self.assertParserResults(
            ""
        )

        self.assertParserResults(
            "@foo",
            '{"@dir": "foo"}'
        )

        self.assertParserResults(
            "@foo@bar",
            '{"@dir": "foo"}',
            '{"@dir": "bar"}'
        )

        self.assertParserResults(
            "@foo @bar @abc",
            '{"@dir": "foo"}',
            '{"@dir": "bar"}',
            '{"@dir": "abc"}'
        )

        self.assertParserResults(
            "@foo(id: 3) @bar @abc(foo: 2.5 abc: null)",
            '{"@dir": "foo", "arguments": [["id", {"@int": 3}]]}',
            '{"@dir": "bar"}',
            '{"@dir": "abc", "arguments": [["foo", {"@float": 2.5}], ["abc", {"@null": null}]]}'
        )

    def test_fails(self):
        self.assertParserError(1, "@foo ()")
        self.assertParserError(1, "foo")
        self.assertParserError(1, "@foo bar")


class ArgumentsParserTest(ParsingTest):
    def init_parser(self):
        self.arguments = []
        return ArgumentsParser(self.arguments)

    def get_result(self):
        return self.arguments

    def test_success(self):
        self.assertParserResults(
            "(id: 3)",
            '["id", {"@int": 3}]'
        )

        self.assertParserResults(
            "(id: 3 name: foo)",
            '["id", {"@int": 3}]',
            '["name", {"@enum": "foo"}]',
        )

    def test_fail(self):
        self.assertParserError(1, "()")
        self.assertParserError(1, "(id 3)")
        self.assertParserError(1, "(id:: 3)")
        self.assertParserError(1, "(id:)")


class SelectionsParserTest(ParsingTest):
    def init_parser(self):
        self.selections = []
        return SelectionsParser(self.selections)

    def get_result(self):
        return self.selections

    def test_success(self):
        self.assertParserResults(
            "{ id }",
            '{"@f": "id"}'
        )
        self.assertParserResults(
            "{ id name }",
            '{"@f": "id"}',
            '{"@f": "name"}'
        )
        self.assertParserResults(
            "{ id ... { name }}",
            '{"@f": "id"}',
            '{"@frg-inline": null, "selections": [{"@f": "name"}]}'
        )
        self.assertParserResults(
            "{ id ... foo }",
            '{"@f": "id"}',
            '{"@frg-spread": "foo"}'
        )
        self.assertParserResults(
            "{ id ... { name } ... foo}",
            '{"@f": "id"}',
            '{"@frg-inline": null, "selections": [{"@f": "name"}]}',
            '{"@frg-spread": "foo"}'
        )
        self.assertParserResults(
            "{ id ... on Foo { name }}",
            '{"@f": "id"}',
            '{"@frg-inline": null, "on_type": {"@named": "Foo"}, "selections": [{"@f": "name"}]}',
        )
        self.assertParserResults(
            "{ id id2: id}",
            '{"@f": "id"}',
            '{"@f": "id", "alias": "id2"}',
        )

    def test_errors(self):
        self.assertParserError(1, "{}")
        self.assertParserError(1, "{ 3 }")
        self.assertParserError(1, "{ .. on Foo {name} }")
        self.assertParserError(1, "{ ... }")


class FieldParserTest(ParsingTest):
    def init_parser(self):
        self.fields = []
        return FieldParser(self.fields)

    def get_result(self):
        return self.fields[0]

    def test_parse(self):
        self.assertParserResult(
            '{"@f": "foo"}',
            "foo"
        )
        self.assertParserResult(
            '{"@f": "foo", "alias": "bar", "arguments": [["id", {"@int": 3}]], '
            '"directives": [{"@dir": "bar"}], "selections": [{"@f": "abc"}]}',
            "bar:foo(id: 3)@bar{abc}"
        )
        self.assertParserResult(
            '{"@f": "foo", "arguments": [["id", {"@int": 3}]], '
            '"directives": [{"@dir": "bar"}], "selections": [{"@f": "abc"}]}',
            "foo(id: 3)@bar{abc}"
        )
        self.assertParserResult(
            '{"@f": "foo", "alias": "bar", '
            '"directives": [{"@dir": "bar"}], "selections": [{"@f": "abc"}]}',
            "bar:foo@bar{abc}"
        )
        self.assertParserResult(
            '{"@f": "foo", "alias": "bar", "arguments": [["id", {"@int": 3}]], '
            '"selections": [{"@f": "abc"}]}',
            "bar:foo(id: 3){abc}"
        )
        self.assertParserResult(
            '{"@f": "foo", "alias": "bar", "arguments": [["id", {"@int": 3}]], '
            '"directives": [{"@dir": "bar"}]}',
            "bar:foo(id: 3)@bar"
        )
        self.assertParserResult(
            '{"@f": "foo", '
            '"directives": [{"@dir": "bar"}], "selections": [{"@f": "abc"}]}',
            "foo@bar{abc}"
        )
        self.assertParserResult(
            '{"@f": "foo", "arguments": [["id", {"@int": 3}]], '
            '"selections": [{"@f": "abc"}]}',
            "foo(id: 3){abc}"
        )
        self.assertParserResult(
            '{"@f": "foo", "arguments": [["id", {"@int": 3}]], '
            '"directives": [{"@dir": "bar"}]}',
            "foo(id: 3)@bar"
        )
        self.assertParserResult(
            '{"@f": "foo", "alias": "bar", '
            '"selections": [{"@f": "abc"}]}',
            "bar:foo{abc}"
        )
        self.assertParserResult(
            '{"@f": "foo", "alias": "bar", '
            '"directives": [{"@dir": "bar"}]}',
            "bar:foo@bar"
        )
        self.assertParserResult(
            '{"@f": "foo", "alias": "bar", "arguments": [["id", {"@int": 3}]]}',
            "bar:foo(id: 3)"
        )
        self.assertParserResult(
            '{"@f": "foo", "selections": [{"@f": "abc"}]}',
            "foo{abc}"
        )
        self.assertParserResult(
            '{"@f": "foo", "directives": [{"@dir": "bar"}]}',
            "foo@bar"
        )
        self.assertParserResult(
            '{"@f": "foo", "arguments": [["id", {"@int": 3}]]}',
            "foo(id: 3)"
        )
        self.assertParserResult(
            '{"@f": "foo", "alias": "bar"}',
            "bar:foo"
        )

    def test_errors(self):
        self.assertParserError(1, "bar!foo")
        self.assertParserError(1, "bar:foo@bar(id: 3)(id: 3){abc}")
        self.assertParserError(1, "bar:foo{abc}(id: 3)@bar")
        self.assertParserError(1, "bar:foo(id: 3){abc}@bar")
        self.assertParserError(1, "foo{}")


class ValueParserTest(ParsingTest):
    def init_parser(self):
        self.value = None

        def set_value(v):
            self.value = v

        return ValueParser(set_value)

    def get_result(self):
        return self.value

    def test_int(self):
        self.assertParserResult('{"@int": 0}', "0")
        self.assertParserResult('{"@int": 0}', "-0")
        self.assertParserResult('{"@int": 3}', "3")
        self.assertParserResult('{"@int": -3}', "-3")
        self.assertParserResult('{"@int": 1234567890}', "1234567890")
        self.assertParserResult('{"@int": -1234567890}', "-1234567890")
        self.assertParserError(1, '01')

    def test_float(self):
        self.assertParserResult('{"@float": 0.0}', "0.0")
        self.assertParserResult('{"@float": -0.0}', "-0.0")
        self.assertParserResult('{"@float": 0.0123456789}', "0.0123456789")
        self.assertParserResult('{"@float": -0.0123456789}', "-0.0123456789")

        self.assertParserResult('{"@float": 10.0}', "0.1e2")
        self.assertParserResult('{"@float": 10.0}', "0.1E2")
        self.assertParserResult('{"@float": 0.001}', "0.1e-2")
        self.assertParserResult('{"@float": 10.0}', "0.1e+2")
        self.assertParserResult('{"@float": -10.0}', "-0.1e2")
        self.assertParserResult('{"@float": -10.0}', "-0.1E2")
        self.assertParserResult('{"@float": -0.001}', "-0.1e-2")
        self.assertParserResult('{"@float": -10.0}', "-0.1e+2")

        self.assertParserResult('{"@float": 100.0}', "1e2")
        self.assertParserResult('{"@float": 100.0}', "1E2")
        self.assertParserResult('{"@float": 0.01}', "1e-2")
        self.assertParserResult('{"@float": 100.0}', "1e+2")
        self.assertParserResult('{"@float": -100.0}', "-1e2")
        self.assertParserResult('{"@float": -100.0}', "-1E2")
        self.assertParserResult('{"@float": -0.01}', "-1e-2")
        self.assertParserResult('{"@float": -100.0}', "-1e+2")

        self.assertParserError(1, "1.")

    def test_simple(self):
        self.assertParserResult('{"@bool": true}', "true")
        self.assertParserResult('{"@bool": false}', "false")
        self.assertParserResult('{"@null": null}', "null")
        self.assertParserResult('{"@enum": "foo"}', "foo")
        self.assertParserResult('{"@var": "foo"}', "$foo")

    def test_variable(self):
        self.assertParserResult('{"@obj": {"a": {"@list": [{"@obj": {"b": {"@var": "v"}}}]}}}', "{a: [{b: $v}]}")
        self.assertParserResult('{"@list": [{"@obj": {"foo": {"@list": [{"@var": "v"}]}}}]}', "[{foo: [$v]}]")
        self.assertParserResult('{"@list": [{"@list": [{"@list": [{"@var": "v"}]}]}]}', "[[[$v]]]")
        self.assertParserResult('{"@obj": {"a": {"@obj": {"b": {"@obj": {"c": {"@var": "v"}}}}}}}', "{a: {b: {c: $v}}}")

    def test_list(self):
        self.assertParserResult('{"@list": []}', "[]")
        self.assertParserResult('{"@list": [{"@int": 1}]}', "[1]")
        self.assertParserResult('{"@list": [{"@int": 1}, {"@int": 2}]}', "[1 2]")
        self.assertParserResult('{"@list": [{"@list": [{"@int": 1}]}]}', "[[1]]")
        self.assertParserResult('{"@list": [{"@obj": {"foo": {"@int": 1}}}, {"@int": 1}]}', "[{foo: 1} 1]")
        self.assertParserResult('{"@list": [{"@obj": {"foo": {"@var": "v"}}}, {"@var": "r"}]}', "[{foo: $v} $r]")

    def test_obj(self):
        self.assertParserResult('{"@obj": {}}', "{}")
        self.assertParserResult('{"@obj": {"x": {"@int": 1}}}', "{x: 1}")
        self.assertParserResult('{"@obj": {"x": {"@list": [{"@int": 1}]}, "y": {"@int": 2}}}', "{x: [1] y: 2}")
        self.assertParserResult('{"@obj": {"x": {"@list": [{"@var": "v"}]}, "y": {"@var": "r"}}}', "{x: [$v] y: $r}")

    def test_str(self):
        self.assertParserResult('{"@str": ""}', '""')
        self.assertParserResult('{"@str": "foo"}', '"foo"')
        self.assertParserResult(r'{"@str": "\u20ac\"\\/\b\f\n\r\t\u20ac"}', r'"\u20ac\"\\\/\b\f\n\r\t\u20AC"')

        self.assertParserError(1, '"\n"')
        self.assertParserError(1, r'"\x"')
        self.assertParserError(1, r'"x')
        self.assertParserError(1, r'"\ui345')


class ConstValueParserTest(ParsingTest):
    def init_parser(self):
        self.value = None

        def set_value(v):
            self.value = v

        return ConstValueParser(set_value)

    def get_result(self):
        return self.value

    def test_success(self):
        self.assertParserResult('{"@int": 0}', "0")
        self.assertParserResult('{"@float": 0.0}', "0.0")
        self.assertParserResult('{"@bool": true}', "true")
        self.assertParserResult('{"@bool": false}', "false")
        self.assertParserResult('{"@null": null}', "null")
        self.assertParserResult('{"@enum": "foo"}', "foo")
        self.assertParserResult('{"@const-list": []}', "[]")
        self.assertParserResult('{"@const-list": [{"@int": 1}]}', "[1]")
        self.assertParserResult('{"@const-obj": {}}', "{}")
        self.assertParserResult('{"@const-obj": {"x": {"@int": 1}}}', "{x: 1}")
        self.assertParserResult('{"@str": ""}', '""')

    def test_errors(self):
        self.assertParserError(1, "$v")
        self.assertParserError(1, "[$v]")
        self.assertParserError(1, "[{foo: $v}]")
        self.assertParserError(1, "{foo: $v}")
        self.assertParserError(1, "{foo: [$v]}")
        self.assertParserError(1, "{a: [{b: $v}]}")
        self.assertParserError(1, "[{foo: [$v]}]")
        self.assertParserError(1, "[[[$v]]]")
        self.assertParserError(1, "{a: {b: {c: $v}}}")



class FragmentSpreadParserTest(ParsingTest):
    def init_parser(self):
        self.fields = []
        return FragmentSpreadParser(self.fields)

    def get_result(self):
        return self.fields[0]

    def test_success(self):
        self.assertParserResult('{"@frg-spread": "foo"}', "... foo")
        self.assertParserResult('{"@frg-spread": "foo", "directives": [{"@dir": "bar"}]}', "... foo @bar")
        self.assertParserResult(
            '{"@frg-spread": "foo", "directives": [{"@dir": "bar"}, {"@dir": "abc"}]}',
            "... foo @bar @abc"
        )

    def test_error(self):
        self.assertParserError(1, "... ")
        self.assertParserError(1, "... foo()")
        self.assertParserError(1, "... foo bar")


class InlineFragmentParserTest(ParsingTest):
    def init_parser(self):
        self.fields = []
        return InlineFragmentParser(self.fields)

    def get_result(self):
        return self.fields[0]

    def test_success(self):
        self.assertParserResult('{"@frg-inline": null, "selections": [{"@f": "foo"}]}', "... {foo}")
        self.assertParserResult(
            '{"@frg-inline": null, "on_type": {"@named": "Bar"}, "selections": [{"@f": "foo"}]}',
            "... on Bar {foo}"
        )
        self.assertParserResult(
            '{"@frg-inline": null, "directives": [{"@dir": "abc"}], "selections": [{"@f": "foo"}]}',
            "... @abc {foo}"
        )
        self.assertParserResult(
            '{"@frg-inline": null, "directives": [{"@dir": "abc"}], "on_type": {"@named": "Bar"}, "selections": [{"@f": "foo"}]}',
            "... on Bar @abc {foo}"
        )

    def test_errors(self):
        self.assertParserError(1, "... on Bar")
        self.assertParserError(1, "... @abc on Bar {foo}")
        self.assertParserError(1, ".. on Bar {foo}")
        self.assertParserError(1, "... {}")


class FragmentParserTest(ParsingTest):
    def init_parser(self):
        self.fragments = []
        return FragmentParser(self.fragments)

    def get_result(self):
        return self.fragments[0]

    def test_success(self):
        self.assertParserResult(
            '{"@frg": "foo", "on_type": {"@named": "Foo"}, "selections": [{"@f": "bar"}]}',
            "fragment foo on Foo {bar}"
        )
        self.assertParserResult(
            '{"@frg": "foo", "directives": [{"@dir": "d"}], "on_type": {"@named": "Foo"}, '
            '"selections": [{"@f": "bar"}]}',
            "fragment foo on Foo @d {bar}"
        )

    def test_errors(self):
        self.assertParserError(1, "fragment on Foo {bar}")
        self.assertParserError(1, "fragment foo Foo {bar}")
        self.assertParserError(1, "fragment foo on {bar}")
        self.assertParserError(1, "fragment foo {bar}")
        self.assertParserError(1, "fragment foo on Foo {}")
        self.assertParserError(1, "fragment foo on Foo")
        self.assertParserError(1, "fragmen foo on Foo {bar}")
        self.assertParserError(1, "fragment on Foo foo {bar}")