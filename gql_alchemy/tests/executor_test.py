import json
import typing as t
import unittest

import gql_alchemy.schema as s
from ..executor import Executor
from ..utils import PrimitiveType


class ExecutorTest(unittest.TestCase):
    def assertQueryResult(self, expected: str, schema: s.Schema, resolver: t.Any,
                          query: str, variables: t.Optional[t.Mapping[str, PrimitiveType]] = None,
                          op_name: t.Optional[str] = None) -> None:
        e = Executor(schema, resolver)
        result = e.query(query, variables if variables is not None else {}, op_name)
        self.assertEqual(expected, json.dumps(result, sort_keys=True))

    def test_select_scalar(self) -> None:
        class Resolver:
            def foo(self, args: t.Mapping[str, PrimitiveType]) -> int:
                return 3

        self.assertQueryResult(
            '{"foo": 3}',
            s.Schema(
                [],
                s.Object("__Query", {
                    "foo": s.Int
                })
            ),
            Resolver(),
            "{foo}"
        )

    def test_select_with_arguments(self) -> None:
        class FooResolver:
            type = "Foo"

            def __init__(self, foo: int) -> None:
                self.__foo = foo

            def bar(self, args: t.Mapping[str, PrimitiveType]) -> int:
                return args["abc"] + self.__foo

        class Resolver:
            def foo(self, args: t.Mapping[str, PrimitiveType]) -> FooResolver:
                return FooResolver(args["foo"])

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
            Resolver(),
            "{foo(foo: 3){bar(abc: 4)}}"
        )
