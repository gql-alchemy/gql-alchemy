import unittest

from ..gql_schema import *


class Test(unittest.TestCase):
    def test(self):
        schema = Schema(
            {
                "t1": Object({
                    "foo": String(),
                    "bar": Int()
                }),
                "t2": Object({
                    "baz": Float(),
                    "abc": Boolean(),
                    "t1": NonNull(List(NonNull("t1")))
                }, ["i1"], "bla-bla-bla"),
                "i1": Interface({
                    "xyz": Float(),
                    "abc": Int(),
                    "foo": NonNull("t1"),
                    "haha": "t2",
                    "field": Field(
                        NonNull(Int()),
                        {
                            "foo": Int(),
                            "bar": InputValue(Float(), 1.1, "bla-bla-bla"),
                            "abc": "io1",
                            "abc1": InputValue("io1", {"foo": 3}, "ggg"),
                            "abc2": InputValue(List("io1"), {"foo": 3}, "ggg"),
                            "abc3": InputValue(NonNull(List("io1")), {"foo": 3}, "ggg")
                        }
                    )
                }),
                "e1": Enum(["foo", "bar"]),
                "io1": InputObject({
                    "foo": List("io2")
                }),
                "io2": InputObject({
                    "bar": Int()
                })
            },
            Object({
                "foo": "t2"
            }),
            Object({
                "mutate_me": Field("i1", {"foo": Int()})
            }),
            {
                "collapse": Directive({DirectiveLocations.FIELD})
            }
        )

        print(schema.format())
