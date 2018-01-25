import json
import unittest

from gql_alchemy.graphql_parser import parse_document, ParsingError

test = """
mutation CreateReviewForEpisode($ep: Episode!, $review: ReviewInput!) {
    createReview(episode: $ep, review: $review) {
        stars
        commentary
    }
}
"""


class ParsingTest(unittest.TestCase):
    def assertDocument(self, expected, query):
        d = parse_document(query)
        self.assertEqual(expected, json.dumps(d.to_primitive(), sort_keys=True))

    def assertParsingError(self, lineno, query):
        with self.assertRaises(ParsingError) as cm:
            parse_document(query)
        self.assertEqual(lineno, cm.exception.lineno)


class TestDocument(ParsingTest):
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

        self.assertParsingError(1, "{id} {id}")
        self.assertParsingError(1, "query {id} {id}")
        self.assertParsingError(1, "{id} query {id}")

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
            "# comment\n  #\nquery{id} # comment\n# query {foo}\n#\n"
        )

    def test_failures(self):
        self.assertParsingError(1, "sfs")
        self.assertParsingError(1, "query{id} fds")
        self.assertParsingError(1, "a query{id}")






class TestQuery(ParsingTest):
    def test_simple(self):
        self.assertDocument(
            '{"operations": [{"selections": [{"name": "foo", "type": "Field"}], "type": "Query"}], "type": "Document"}',
            """
            query {
                foo
            }
            """
        )

    def test_selections_required(self):
        self.assertParsingError(
            1,
            """ query """
        )

    def test_no_empty_selections(self):
        self.assertParsingError(
            1,
            """ query {}"""
        )


class TestParse(unittest.TestCase):
    def test(self):
        d = parse_document(test)
        print(json.dumps(d.to_primitive(), indent=2))
