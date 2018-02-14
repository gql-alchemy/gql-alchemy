import json
import typing as t
import unittest

import gql_alchemy.schema as s
from ..executor import Executor, Resolver
from ..utils import PrimitiveType


class ExecutorTest(unittest.TestCase):
    def assertQueryResult(self, expected: str, schema: s.Schema, resolver: t.Any,
                          query: str, variables: t.Optional[t.Mapping[str, PrimitiveType]] = None,
                          op_name: t.Optional[str] = None) -> None:
        e = Executor(schema, resolver)
        result = e.query(query, variables if variables is not None else {}, op_name)
        self.assertEqual(expected, json.dumps(result, sort_keys=True))

    def test_select_scalar(self) -> None:
        class QueryResolver(Resolver):
            def __init__(self):
                super().__init__("__Query")

            def foo(self) -> int:
                return 3

        self.assertQueryResult(
            '{"foo": 3}',
            s.Schema(
                [],
                s.Object("__Query", {
                    "foo": s.Int
                })
            ),
            QueryResolver(),
            "{foo}"
        )

    def test_select_with_arguments(self) -> None:
        class FooResolver(Resolver):
            def __init__(self, foo: int) -> None:
                super().__init__("Foo")

                self.__foo = foo

            def bar(self, abc: int) -> int:
                return abc + self.__foo

        class QueryResolver(Resolver):
            def __init__(self):
                super().__init__("__Query")

            def foo(self, foo: int) -> FooResolver:
                return FooResolver(foo)

        self.assertQueryResult(
            '{"foo": {"bar": 7}}',
            s.Schema(
                [
                    s.Object("Foo", {"bar": s.Field(s.Int, {"abc": s.Int})})
                ],
                s.Object("__Query", {
                    "foo": s.Field("Foo", {"foo": s.Int})
                })
            ),
            QueryResolver(),
            "{foo(foo: 3){bar(abc: 4)}}"
        )

    def test_fragment_select(self):
        class QueryResolver(Resolver):
            def __init__(self):
                super().__init__("Query")

            def foo(self):
                return "foo"

            def bar(self):
                return "bar"

        self.assertQueryResult(
            '{"bar": "bar", "foo": "foo"}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String,
                    "bar": s.String
                })
            ),
            QueryResolver(),
            "{ foo ...Bar} fragment Bar on Query { bar }"
        )
