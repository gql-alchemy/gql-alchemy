import unittest

from .graphql_parser import parse

test = """
mutation CreateReviewForEpisode($ep: Episode!, $review: ReviewInput!) {
    createReview(episode: $ep, review: $review) {
        stars
        commentary
    }
"""


class TestParse(unittest.TestCase):
    def test(self):
        parse(test)
