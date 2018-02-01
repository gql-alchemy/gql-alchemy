import unittest

from ..schema import *


class Test(unittest.TestCase):
    def test(self) -> None:
        schema = Schema(
            [
                Object("t1", {
                    "foo": String,
                    "bar": Int
                }),
                Object("t2", {
                    "baz": Float,
                    "abc1": Boolean,
                    "t1": NonNull(List(NonNull("t1")))
                }, {"i1"}, "bla-bla-bla"),
                Interface("i1", {
                    "xyz": Float,
                    "abc": Int,
                    "foo": NonNull("t1"),
                    "haha": "t2",
                    "field": Field(
                        NonNull(Int),
                        {
                            "foo": Int,
                            "bar": InputValue(Float, 1.1, "bla-bla-bla"),
                            "abc": "io1",
                            "abc1": InputValue("io1", {"foo": [{"bar": 3}, {"bar": 4}]}, "ggg"),
                            "abc2": InputValue(List("io2"), [{"bar": 3}], "ggg"),
                            "abc3": InputValue(NonNull(List("io2")), [{"bar": 3}], "ggg")
                        }
                    )
                }),
                Enum("e1", ["foo", "bar"]),
                InputObject("io1", {
                    "foo": List("io2")
                }),
                InputObject("io2", {
                    "bar": Int
                })
            ],
            Object("QueryRoot", {
                "foo": "t2"
            }),
            Object("MutationRoot", {
                "mutate_me": Field("i1", {"foo": Int})
            }),
            [
                Directive("collapse", {DirectiveLocations.FIELD})
            ]
        )

        print(schema.format())
