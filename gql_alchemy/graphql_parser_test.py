import json
import unittest

from .graphql_parser import parse

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


class TestParse(unittest.TestCase):
    def test(self):
        d = parse(test)
        print(json.dumps(d.to_dict(), indent=2))
