import json
import unittest

from gql_alchemy.graphql_parser import parse, ParsingError

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
        d = parse(query)
        self.assertEqual(expected, json.dumps(d.to_dict(), sort_keys=True))

    def assertParsingError(self, lineno, query):
        with self.assertRaises(ParsingError) as cm:
            parse(query)
        self.assertEqual(lineno, cm.exception.lineno)


class TestShortcut(ParsingTest):
    def test(self):
        self.assertDocument(
            '{"selections": [{"name": "id", "type": "field"}, {"name": "name", "type": "field"}], "type": "document"}',
            """
            {
                id
                name
            }
            """
        )

        self.assertDocument(
            '{"selections": [{"name": "user", "selections": [{"name": "id", "type": "field"}, {"name": "name", "type": "field"}], "type": "field"}], "type": "document"}',
            """
            {
                user {
                    id
                    name
                }
            }
            """
        )


class TestQuery(ParsingTest):
    def test_simple(self):
        self.assertDocument(
            '{"operations": [{"sel": [{"name": "foo", "type": "field"}], "type": "query"}], "type": "document"}',
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
        d = parse(test)
        print(json.dumps(d.to_dict(), indent=2))
