import typing as t
import unittest
from itertools import chain

import gql_alchemy.schema as s
from gql_alchemy.executor import Executor, Resolver, SomeResolver
from gql_alchemy.utils import PrimitiveType


class ListQuery:
    def __init__(self, iterable: t.Iterable[t.Any]) -> None:
        self.__iterable = iterable

    def attr(self, name: str) -> 'ListQuery':
        return ListQuery((self.__getattr(i, name) for i in self.__iterable))

    def filter(self, cond: t.Callable[[t.Any], bool]) -> 'ListQuery':
        return ListQuery((i for i in self.__iterable if cond(i)))

    def eq(self, attr: str, value: t.Any) -> 'ListQuery':
        return self.filter(lambda i: self.__getattr(i, attr) == value)

    def neq(self, attr: str, value: t.Any) -> 'ListQuery':
        return self.filter(lambda i: self.__getattr(i, attr) != value)

    def map(self, func: t.Callable[[t.Any], t.Any]) -> 'ListQuery':
        return ListQuery((func(i) for i in self.__iterable))

    def keys(self) -> 'ListQuery':
        return self.map(lambda i: set(i.keys()))

    def values(self) -> 'ListQuery':
        return self.map(lambda i: list(i.values()))

    def select(self, *names: str) -> 'ListQuery':
        def gen() -> t.Iterable[t.Any]:
            for i in self.__iterable:
                new_i = {}
                for f in names:
                    new_i[f] = self.__getattr(i, f)
                yield new_i

        return ListQuery(gen())

    def flatten(self) -> 'ListQuery':
        return ListQuery(chain.from_iterable(self.__iterable))

    def list(self) -> t.List[t.Any]:
        return list(self.__iterable)

    def set(self) -> t.MutableSet[t.Any]:
        return set(self.__iterable)

    def is_empty(self) -> bool:
        return len(self.list()) == 0

    def count(self) -> int:
        count = 0

        for _ in self.__iterable:
            count += 1

        return count

    @staticmethod
    def __getattr(item: t.Any, attr: str) -> t.Any:
        if isinstance(item, dict):
            return item[attr]
        return getattr(item, attr)


class IntrospectionTest(unittest.TestCase):
    def query(self, schema: s.Schema, query: str, query_resolver: SomeResolver,
              mutation_resolver: t.Optional[SomeResolver] = None,
              variables: t.Optional[t.Mapping[str, PrimitiveType]] = None,
              op_name: t.Optional[str] = None) -> PrimitiveType:
        e = Executor(schema, query_resolver, mutation_resolver)
        return e.query(query, variables if variables is not None else {}, op_name)

    def test_scalars(self) -> None:
        class Query(Resolver):
            foo = "foo"

        result = self.query(
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String,
                })
            ),
            """
            { __schema { types {
                kind name description
                fields { name }
                interfaces { name }
                possibleTypes { name }
                enumValues { name }
                inputFields { name }
                ofType { name }
            }}}
            """,
            Query()
        )

        scalars = ListQuery([result]).attr("__schema").attr("types").flatten().eq("kind", "SCALAR").list()

        self.assertEqual(
            {'SCALAR'},
            ListQuery(scalars).attr("kind").set()
        )

        self.assertEqual(
            {'Boolean', 'Int', 'Float', 'ID', 'String'},
            ListQuery(scalars).attr("name").set()
        )

        self.assertEqual(
            {None},
            ListQuery(scalars).select(
                "fields", "interfaces", "possibleTypes", "enumValues", "inputFields", "ofType"
            ).values().flatten().set()
        )

        self.assertEqual(
            {"Standard type"},
            ListQuery(scalars).attr("description").set()
        )

    def test_object(self) -> None:
        class Query(Resolver):
            foo = "foo"

        result = self.query(
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String,
                })
            ),
            """
            { __schema { types {
                kind name description
                fields { name }
                interfaces { name }
                possibleTypes { name }
                enumValues { name }
                inputFields { name }
                ofType { name }
            }}}
            """,
            Query()
        )

        objects = ListQuery([result]).attr("__schema").attr("types").flatten().eq("kind", "OBJECT").list()

        self.assertEqual(
            {'OBJECT'},
            ListQuery(objects).attr("kind").set()
        )

        self.assertEqual(
            {'Query'},
            ListQuery(objects).attr("name").set()
        )

        self.assertEqual(
            {"foo"},
            ListQuery(objects).attr("fields").flatten().attr("name").set()
        )

        self.assertTrue(
            ListQuery(objects).attr("interfaces").flatten().is_empty()
        )

        self.assertEqual(
            {None},
            ListQuery(objects).select(
                "possibleTypes", "enumValues", "inputFields", "ofType"
            ).values().flatten().set()
        )

    def test_query_type(self) -> None:
        class Query(Resolver):
            foo = "foo"

        result = self.query(
            s.Schema(
                [
                ],
                s.Object("Query", {
                    "foo": s.String,
                })
            ),
            """
            { __schema { queryType {
                kind name description
                fields { name }
                interfaces { name }
                possibleTypes { name }
                enumValues { name }
                inputFields { name }
                ofType { name }
            }}}
            """,
            Query()
        )

        objects = ListQuery([result]).attr("__schema").attr("queryType").list()

        self.assertEqual(
            {'OBJECT'},
            ListQuery(objects).attr("kind").set()
        )
