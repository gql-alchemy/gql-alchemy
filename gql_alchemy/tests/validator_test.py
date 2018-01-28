import logging
import typing as t
import unittest

import gql_alchemy.schema as s
from gql_alchemy.parser import parse_document
from gql_alchemy.utils import PrimitiveType
from gql_alchemy.validator import validate, GqlValidationError

logger = logging.getLogger("gql_alchemy.validator_test")
logger.setLevel(logging.DEBUG)
sh = logging.StreamHandler()
sh.setLevel(logging.DEBUG)
logger.addHandler(sh)


class ValidatorTest(unittest.TestCase):
    def assertValidationError(self, query: str, schema: s.Schema,
                              error_message: str,
                              variables: t.Optional[t.Mapping[str, PrimitiveType]] = None):
        with self.assertRaises(GqlValidationError) as cm:
            validate(
                parse_document(query),
                schema,
                variables if variables is not None else {}
            )

        self.assertEqual(error_message, str(cm.exception))

    @staticmethod
    def assertNoErrors(query: str, schema: s.Schema,
                       variables: t.Optional[t.Mapping[str, PrimitiveType]] = None):
        validate(
            parse_document(query),
            schema,
            variables if variables is not None else {}
        )


class FieldsTest(ValidatorTest):
    def test_fields_exists(self):
        validate(
            parse_document("{ foo }"),
            s.Schema({}, s.Object({"foo": s.Int()})),
            {}
        )
        self.assertValidationError(
            "{ foo }",
            s.Schema({}, s.Object({"bar": s.Int()})),
            "Selecting undefined field `foo` from @query type"
        )

    def test_subfield_exists(self):
        validate(
            parse_document("{ foo { bar } }"),
            s.Schema(
                {
                    "Foo": s.Object({
                        "bar": s.Int()
                    })
                },
                s.Object({"foo": "Foo"})
            ),
            {}
        )
        self.assertValidationError(
            "{ foo { bar } }",
            s.Schema(
                {
                    "Foo": s.Object({
                        "abc": s.Int()
                    })
                },
                s.Object({"foo": "Foo"})
            ),
            "Selecting undefined field `bar` from Foo type"
        )

    def test_selectable_field_must_queries_with_selections(self):
        validate(
            parse_document("{ foo { bar } }"),
            s.Schema(
                {
                    "Foo": s.Object({
                        "bar": s.Int()
                    })
                },
                s.Object({"foo": "Foo"})
            ),
            {}
        )

        self.assertValidationError(
            "{ foo }",
            s.Schema(
                {
                    "Foo": s.Object({
                        "abc": s.Int()
                    })
                },
                s.Object({"foo": "Foo"})
            ),
            "Spreadable type (interface, class, union) must be selected with fields"
        )

    def test_select_field_of_wrapped_type(self):
        validate(
            parse_document("{ foo { bar } }"),
            s.Schema(
                {
                    "Foo": s.Object({
                        "bar": s.Int()
                    })
                },
                s.Object({"foo": s.NonNull(s.List(s.NonNull("Foo")))})
            ),
            {}
        )
        self.assertValidationError(
            "{ foo { bar } }",
            s.Schema(
                {
                    "Foo": s.Object({
                        "abc": s.Int()
                    })
                },
                s.Object({
                    "foo": s.NonNull(s.List(s.NonNull("Foo")))
                })
            ),
            "Selecting undefined field `bar` from Foo type"
        )

    def test_select_fields_of_plain_type(self):
        schema = s.Schema(
            {
                "Foo": s.Object({
                    "abc": s.Int()
                })
            },
            s.Object({
                "foo": s.NonNull(s.List(s.NonNull("Foo")))
            })
        )

        self.assertNoErrors("{ foo {abc}}", schema)

        self.assertValidationError(
            "{ foo {abc { xxx }}}",
            schema,
            "Selecting fields for type without fields"
        )

    def test_required_arguments(self):
        schema = s.Schema(
            {
                "Foo": s.Object({
                    "abc": s.Int()
                })
            },
            s.Object({
                "foo": s.Field("Foo", {"bar": s.Int()})
            })
        )
        self.assertNoErrors("{ foo(bar: 10) {abc}}", schema)
        self.assertValidationError("{ foo {abc}}", schema, "Selection miss required arguments: bar")
