import logging
import typing as t
import unittest

import gql_alchemy.schema as s
from gql_alchemy.parser import parse_document
from gql_alchemy.utils import PrimitiveType
from gql_alchemy.validator import validate, GqlValidationError

# sh = logging.StreamHandler()
# sh.setLevel(logging.DEBUG)
#
# logger = logging.getLogger("gql_alchemy")
# logger.setLevel(logging.DEBUG)
# logger.addHandler(sh)

logger = logging.getLogger("gql_alchemy.validator_test")
logger.setLevel(logging.DEBUG)


# logger.addHandler(sh)


class ValidatorTest(unittest.TestCase):
    def assertValidationError(self, query: str, schema: s.Schema,
                              error_message: str,
                              variables: t.Optional[t.Mapping[str, PrimitiveType]] = None) -> None:
        with self.assertRaises(GqlValidationError) as cm:
            validate(
                parse_document(query),
                schema,
                variables if variables is not None else {}
            )

        self.assertEqual(error_message, str(cm.exception))

    @staticmethod
    def assertNoErrors(query: str, schema: s.Schema,
                       variables: t.Optional[t.Mapping[str, PrimitiveType]] = None) -> None:
        validate(
            parse_document(query),
            schema,
            variables if variables is not None else {}
        )


class FieldsTest(ValidatorTest):
    def test_fields_exists(self) -> None:
        validate(
            parse_document("{ foo }"),
            s.Schema([], s.Object("Query", {"foo": s.Int})),
            {}
        )
        self.assertValidationError(
            "{ foo }",
            s.Schema([], s.Object("Query", {"bar": s.Int})),
            "`Query` type does not define `foo` field"
        )

    def test_subfield_exists(self) -> None:
        validate(
            parse_document("{ foo { bar } }"),
            s.Schema(
                [
                    s.Object("Foo", {
                        "bar": s.Int
                    })
                ],
                s.Object("Query", {"foo": "Foo"})
            ),
            {}
        )
        self.assertValidationError(
            "{ foo { bar } }",
            s.Schema(
                [
                    s.Object("Foo", {
                        "abc": s.Int
                    })
                ],
                s.Object("Query", {"foo": "Foo"})
            ),
            "`Foo` type does not define `bar` field"
        )

    def test_selectable_field_must_queries_with_selections(self) -> None:
        validate(
            parse_document("{ foo { bar } }"),
            s.Schema(
                [
                    s.Object("Foo", {
                        "bar": s.Int
                    })
                ],
                s.Object("Query", {"foo": "Foo"})
            ),
            {}
        )

        self.assertValidationError(
            "{ foo }",
            s.Schema(
                [
                    s.Object("Foo", {
                        "abc": s.Int
                    })
                ],
                s.Object("Query", {"foo": "Foo"})
            ),
            "Spreadable type `Foo` must be selected with sub-selections"
        )

    def test_select_field_of_wrapped_type(self) -> None:
        validate(
            parse_document("{ foo { bar } }"),
            s.Schema(
                [
                    s.Object("Foo", {
                        "bar": s.Int
                    })
                ],
                s.Object("Query", {"foo": s.NonNull(s.List(s.NonNull("Foo")))})
            ),
            {}
        )
        self.assertValidationError(
            "{ foo { bar } }",
            s.Schema(
                [
                    s.Object("Foo", {
                        "abc": s.Int
                    })
                ],
                s.Object("Query", {
                    "foo": s.NonNull(s.List(s.NonNull("Foo")))
                })
            ),
            "`Foo` type does not define `bar` field"
        )

    def test_select_fields_of_plain_type(self) -> None:
        schema = s.Schema(
            [
                s.Object("Foo", {
                    "abc": s.Int
                })
            ],
            s.Object("Query", {
                "foo": s.NonNull(s.List(s.NonNull("Foo")))
            })
        )

        self.assertNoErrors("{ foo {abc}}", schema)

        self.assertValidationError(
            "{ foo {abc { xxx }}}",
            schema,
            "Can not select from non spreadable type `Int`"
        )

    def test_required_arguments(self) -> None:
        schema = s.Schema(
            [
                s.Object("Foo", {
                    "abc": s.Int
                })
            ],
            s.Object("Query", {
                "foo": s.Field("Foo", {"bar": s.Int})
            })
        )
        self.assertNoErrors("{ foo(bar: 10) {abc}}", schema)
        self.assertValidationError("{ foo {abc}}", schema, "Argument `bar` is required")
