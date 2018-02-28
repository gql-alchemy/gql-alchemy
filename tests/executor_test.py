import json
import typing as t
import unittest

import gql_alchemy.schema as s
from gql_alchemy.executor import Executor, Resolver, SomeResolver
from gql_alchemy.utils import PrimitiveType


class ExecutorTest(unittest.TestCase):
    def assertQueryResult(self, expected: str, schema: s.Schema, query: str, query_resolver: SomeResolver,
                          mutation_resolver: SomeResolver = None,
                          variables: t.Optional[t.Mapping[str, PrimitiveType]] = None,
                          op_name: t.Optional[str] = None) -> None:
        e = Executor(schema, query_resolver, mutation_resolver)
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
            "{foo}",
            QueryResolver()
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
            "{foo(foo: 3){bar(abc: 4)}}",
            QueryResolver()
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
            "{ foo ...Bar} fragment Bar on Query { bar }",
            QueryResolver())

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
            "{ foo ... { bar }}",
            QueryResolver()
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
            "{ list { foo ... on FooBar { bar } }}",
            QueryResolver()
        )

    def test_non_callable_resolving(self):
        class Bar(Resolver):
            bar_field = "bar_field"

        class Query(Resolver):
            foo = "foo"

            bar = Bar()

        self.assertQueryResult('{"bar": {"bar_field": "bar_field"}, "foo": "foo"}', s.Schema(
            [
                s.Object("Bar", {
                    "bar_field": s.String
                })
            ],
            s.Object("Query", {
                "foo": s.String,
                "bar": "Bar"
            })
        ), "{ foo bar { bar_field }}", Query())

    def test_operation_selection(self):
        class Query(Resolver):
            foo = "foo"
            bar = "bar"

        self.assertQueryResult(
            '{"foo": "foo"}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String,
                    "bar": s.String
                })
            ),
            "query selectAll { foo bar } query selectFoo { foo }",
            Query(),
            variables={}, op_name="selectFoo"
        )

    def test_mutation(self):
        class Query(Resolver):
            foo = "foo"

        class Mutation(Resolver):
            bar = "bar"

        self.assertQueryResult(
            '{"bar": "bar"}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String,
                }),
                s.Object("Mutation", {
                    "bar": s.String,
                })
            ),
            "mutation { bar }",
            Query(),
            Mutation()
        )

    def test_variables(self):
        class Query(Resolver):
            def foo(self, a, b):
                return a + b

        self.assertQueryResult(
            '{"foo": 8}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.Field(s.Int, {"a": s.Int, "b": s.Int}),
                })
            ),
            "query ($v: Int){ foo(a: 3, b: $v) }",
            Query(),
            variables={"v": 5}
        )

    def test_variables_with_default(self):
        class Query(Resolver):
            def foo(self, a, b):
                return a + b

        self.assertQueryResult(
            '{"foo": 6}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.Field(s.Int, {"a": s.Int, "b": s.Int}),
                })
            ),
            "query ($v1: Int, $v2: Int = 5){ foo(a: $v1, b: $v2) }",
            Query(),
            variables={"v1": 1}
        )

    def test_fragment_on_union(self):
        class Foo(Resolver):
            foo = "foo"

        class Query(Resolver):
            u = Foo()

        self.assertQueryResult(
            '{"u": {"foo": "foo"}}',
            s.Schema(
                [
                    s.Object("Foo", {
                        "foo": s.String
                    }),
                    s.Object("Bar", {
                        "bar": s.String
                    }),
                    s.Union("FooOrBar", {"Foo", "Bar"})
                ],
                s.Object("Query", {
                    "u": "FooOrBar"
                })
            ),
            "{ u {...Foo} } fragment Foo on Foo { foo }",
            Query()
        )

    def test_skip_fragment_on_union_if_types_not_match(self):
        class Bar(Resolver):
            bar = "bar"

        class Query(Resolver):
            u = Bar()

        self.assertQueryResult(
            '{"u": {}}',
            s.Schema(
                [
                    s.Object("Foo", {
                        "foo": s.String
                    }),
                    s.Object("Bar", {
                        "bar": s.String
                    }),
                    s.Union("FooOrBar", {"Foo", "Bar"})
                ],
                s.Object("Query", {
                    "u": "FooOrBar"
                })
            ),
            "{ u {...Foo} } fragment Foo on Foo { foo }",
            Query()
        )

    def test_return_none_for_plain_field(self):
        class Query(Resolver):
            foo = None

        self.assertQueryResult(
            '{"foo": null}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.Int
                })
            ),
            "{ foo }",
            Query()
        )

    def test_return_none_for_selectable_field(self):
        class Query(Resolver):
            foo = None

        self.assertQueryResult(
            '{"foo": null}',
            s.Schema(
                [
                    s.Object("Foo", {"foo": s.Int})
                ],
                s.Object("Query", {
                    "foo": "Foo"
                })
            ),
            "{ foo { foo } }",
            Query()
        )

    def test_fragment_on_interface(self):
        class Foo(Resolver):
            foo = "foo"

        class Query(Resolver):
            foo = Foo()

        self.assertQueryResult(
            '{"foo": {"foo": "foo"}}',
            s.Schema(
                [
                    s.Interface("FooInt", {"foo": s.String}),
                    s.Object("Foo", {}, {"FooInt"}),
                ],
                s.Object("Query", {
                    "foo": "FooInt"
                })
            ),
            "{ foo {...Foo} } fragment Foo on FooInt { foo }",
            Query()
        )

    def test_skip_true_directive_on_field(self):
        class Query(Resolver):
            foo = "foo"

        self.assertQueryResult(
            '{}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String
                })
            ),
            "{ foo @skip(if: true) }",
            Query()
        )

    def test_skip_false_directive_on_field(self):
        class Query(Resolver):
            foo = "foo"

        self.assertQueryResult(
            '{"foo": "foo"}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String
                })
            ),
            "{ foo @skip(if: false) }",
            Query()
        )

    def test_include_true_directive_on_field(self):
        class Query(Resolver):
            foo = "foo"

        self.assertQueryResult(
            '{"foo": "foo"}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String
                })
            ),
            "{ foo @include(if: true) }",
            Query()
        )

    def test_include_false_directive_on_field(self):
        class Query(Resolver):
            foo = "foo"

        self.assertQueryResult(
            '{}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String
                })
            ),
            "{ foo @include(if: false) }",
            Query()
        )

    def test_skip_true_directive_on_fragment_spread(self):
        class Query(Resolver):
            foo = "foo"

        self.assertQueryResult(
            '{}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String
                })
            ),
            "{ ... Foo @skip(if: true) } fragment Foo on Query { foo }",
            Query()
        )

    def test_skip_false_directive_on_fragment_spread(self):
        class Query(Resolver):
            foo = "foo"

        self.assertQueryResult(
            '{"foo": "foo"}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String
                })
            ),
            "{ ... Foo @skip(if: false) } fragment Foo on Query { foo }",
            Query()
        )

    def test_skip_true_directive_on_inline_spread(self):
        class Query(Resolver):
            foo = "foo"

        self.assertQueryResult(
            '{}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String
                })
            ),
            "{ ... @skip(if: true) { foo } }",
            Query()
        )

    def test_skip_false_directive_on_inline_spread(self):
        class Query(Resolver):
            foo = "foo"

        self.assertQueryResult(
            '{"foo": "foo"}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String
                })
            ),
            "{ ... @skip(if: false) { foo } }",
            Query()
        )

    def test_directive_affect_its_target_only(self):
        class Query(Resolver):
            foo = "foo"
            bar = 10

        self.assertQueryResult(
            '{"bar": 10}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String,
                    "bar": s.Int
                })
            ),
            "{ ... @skip(if: true) { foo } bar }",
            Query()
        )

    def test_default_argument(self):
        class Query(Resolver):
            def foo(self, a: int) -> int:
                return a + 5

        self.assertQueryResult(
            '{"foo": 7}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.Field(s.Int, {"a": s.InputValue(s.Int, 2)}),
                })
            ),
            "{ foo }",
            Query()
        )

    def test_null_by_default(self):
        class Query(Resolver):
            def foo(self, a: t.Optional[int]) -> int:
                if a is None:
                    return 1
                return a + 5

        self.assertQueryResult(
            '{"foo": 1}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.Field(s.Int, {"a": s.Int}),
                })
            ),
            "{ foo }",
            Query()
        )

    def test_non_null_param_with_default(self):
        class Query(Resolver):
            def foo(self, a: int) -> int:
                return a + 5

        self.assertQueryResult(
            '{"foo": 8}',
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.Field(s.Int, {"a": s.NonNull(s.Int)}),
                })
            ),
            "query ($a: Int! = 3){ foo(a: $a) }",
            Query()
        )
