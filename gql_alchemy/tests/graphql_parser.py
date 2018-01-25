import unittest

from gql_alchemy.graphql_parser import *


class ParsingTest(unittest.TestCase):
    def init_parser(self) -> ElementParser:
        raise NotImplementedError()

    def get_result(self) -> Union[GraphQlModelType, List[GraphQlModelType]]:
        raise NotImplementedError()

    def assertParserResult(self, expected: str, query: str):
        parser = self.init_parser()
        parse(query, parser)
        result = self.get_result()
        self.assertEqual(expected, json.dumps(result.to_primitive(), sort_keys=True))

    def assertParserError(self, lineno: int, query: str):
        parser = self.init_parser()
        with self.assertRaises(ParsingError) as cm:
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
        with self.assertRaises(ParsingError) as cm:
            parse_document(query)
        self.assertEqual(lineno, cm.exception.lineno)


class DocumentParserTest(ParsingTest):
    def test_shortcut_form(self):
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}, {"name": "name", "type": "Field"}],'
            ' "type": "Query"}], "type": "Document"}',
            "{ id name }"
        )

        self.assertDocument(
            '{"operations": [{"selections": [{"name": "user", "selections": [{"name": "id", "type": "Field"},'
            ' {"name": "name", "type": "Field"}], "type": "Field"}], "type": "Query"}], "type": "Document"}',
            "{ user {id name} }"
        )

        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Mutation"}], "type": "Document"}',
            "{id} mutation {id}"
        )

        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Mutation"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}], "type": "Document"}',
            "mutation {id} {id}"
        )

        self.assertDocumentError(1, "{id} {id}")
        self.assertDocumentError(1, "query {id} {id}")
        self.assertDocumentError(1, "{id} query {id}")

    def test_query(self):
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}], "type": "Document"}',
            "query { id }"
        )

    def test_mutation(self):
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Mutation"}], '
            '"type": "Document"}',
            "mutation { id }"
        )

    def test_fragment(self):
        self.assertDocument(
            '{"fragments": [{"name": "foo", "on_type": {"@named": "Bar"}, '
            '"selections": [{"name": "id", "type": "Field"}], "type": "Fragment"}], "type": "Document"}',
            "fragment foo on Bar { id }"
        )

    def test_parse_many(self):
        self.assertDocument(
            '{"fragments": [{"name": "foo", "on_type": {"@named": "Bar"}, '
            '"selections": [{"name": "id", "type": "Field"}], "type": "Fragment"}, '
            '{"name": "foo1", "on_type": {"@named": "Bar"}, "selections": [{"name": "id", "type": "Field"}], '
            '"type": "Fragment"}], '
            '"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Mutation"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Mutation"}], "type": "Document"}',
            "query {id} query {id} query {id}"
            "mutation {id} mutation {id}"
            "fragment foo on Bar {id} fragment foo1 on Bar {id}"
        )
        self.assertDocument(
            '{"fragments": [{"name": "foo", "on_type": {"@named": "Bar"}, '
            '"selections": [{"name": "id", "type": "Field"}], "type": "Fragment"}, '
            '{"name": "foo1", "on_type": {"@named": "Bar"}, "selections": [{"name": "id", "type": "Field"}], '
            '"type": "Fragment"}], '
            '"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Mutation"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Mutation"}, '
            '{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}], "type": "Document"}',
            "query {id} mutation {id} query {id}"
            "mutation {id} fragment foo on Bar {id}"
            "query {id} fragment foo1 on Bar {id}"
        )

    def test_whitespaces(self):
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}], "type": "Document"}',
            ",,query,,{,,,id,},"
        )
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}], "type": "Document"}',
            "query{id}"
        )
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}], "type": "Document"}',
            "  query   {  id  }   "
        )
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}], "type": "Document"}',
            "\n\nquery\n\n{\n\n\nid\n}\n\n\n"
        )
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}], "type": "Document"}',
            "\t\tquery\t\t{\t\t\tid\t}\t\t\t"
        )

    def test_comments(self):
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "id", "type": "Field"}], "type": "Query"}], "type": "Document"}',
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
            '{"selections": [{"name": "foo", "type": "Field"}], "type": "Query"}',
            "query {foo}"
        )

        self.assertParserError(1, "mutation {foo}")

    def test_optionals(self):
        self.assertParserResult(
            '{"selections": [{"name": "foo", "type": "Field"}], "type": "Query"}',
            "query {foo}"
        )
        self.assertParserResult(
            '{"directives": [{"name": "bar", "type": "Directive"}], "name": "foo", '
            '"selections": [{"name": "abc", "type": "Field"}], "type": "Query", '
            '"variables": [["id", {"@named": "Bar"}, null]]}',
            "query foo ($id: Bar) @bar {abc}"
        )
        self.assertParserResult(
            '{"directives": [{"name": "bar", "type": "Directive"}], '
            '"selections": [{"name": "abc", "type": "Field"}], '
            '"type": "Query", '
            '"variables": [["id", {"@named": "Bar"}, null]]}',
            "query ($id: Bar) @bar {abc}"
        )
        self.assertParserResult(
            '{"directives": [{"name": "bar", "type": "Directive"}], '
            '"name": "foo", '
            '"selections": [{"name": "abc", "type": "Field"}], '
            '"type": "Query"}',
            "query foo @bar {abc}"
        )
        self.assertParserResult(
            '{"name": "foo", '
            '"selections": [{"name": "abc", "type": "Field"}], '
            '"type": "Query", '
            '"variables": [["id", {"@named": "Bar"}, null]]}',
            "query foo ($id: Bar) {abc}"
        )
        self.assertParserResult(
            '{"name": "foo", "selections": [{"name": "abc", "type": "Field"}], "type": "Query"}',
            "query foo {abc}"
        )
        self.assertParserResult(
            '{"selections": [{"name": "abc", "type": "Field"}], '
            '"type": "Query", "variables": [["id", {"@named": "Bar"}, null]]}',
            "query ($id: Bar) {abc}"
        )
        self.assertParserResult(
            '{"directives": [{"name": "bar", "type": "Directive"}], '
            '"selections": [{"name": "abc", "type": "Field"}], '
            '"type": "Query"}',
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
            '{"selections": [{"name": "foo", "type": "Field"}], "type": "Mutation"}',
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

    def test_error(self):
        self.assertParserError(1, "()")
        self.assertParserError(1, "(foo: Bar)")
        self.assertParserError(1, "($foo Bar)")
        self.assertParserError(1, "($foo Bar 3)")


class ConstValueParserTest(ParsingTest):
    def init_parser(self):
        self.value = None

        def set_value(v):
            self.value = v

        return ValueParser(set_value, True)

    def get_result(self):
        return self.value

    def test_simple(self):
        self.assertParserResult('{"@int": 3}', "3")
