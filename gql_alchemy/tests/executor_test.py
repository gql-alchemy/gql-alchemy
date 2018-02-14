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

    def test_inline_fragment_select(self):
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
            "{ foo ... { bar }}"
        )

    def test_inline_fragment_type_selection(self):
        class FooBarResolver(Resolver):
            def foo(self):
                return "foo from foobar"

            def bar(self):
                return "bar"

        class FooAbcResolver(Resolver):
            def foo(self):
                return "foo from fooabc"

            def abc(self):
                return "abc"

        class QueryResolver(Resolver):
            def list(self):
                return [FooBarResolver(), FooAbcResolver()]

        self.assertQueryResult(
            '{"list": [{"bar": "bar", "foo": "foo from foobar"}, {"foo": "foo from fooabc"}]}',
            s.Schema(
                [
                    s.Interface("Foo", {"foo": s.String}),
                    s.Object("FooBar", {"bar": s.String}, {"Foo"}),
                    s.Object("FooAbc", {"abc": s.String}, {"Foo"})
                ],
                s.Object("Query", {
                    "list": s.List("Foo"),
                })
            ),
            QueryResolver(),
            "{ list { foo ... on FooBar { bar } }}"
        )
