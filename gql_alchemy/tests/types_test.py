import typing as t
import unittest

import gql_alchemy.query_model as qm
import gql_alchemy.types as gt
from gql_alchemy.errors import GqlSchemaError


class TypesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.type_registry = gt.TypeRegistry(
            [
                gt.Object("TestObject", {"foo": gt.Field(gt.Int, {})}, set()),
                gt.Object("TestObject2", {"bar": gt.Field(gt.Int, {})}, set()),
                gt.InputObject("TestInputObject", {"foo": gt.Float})
            ],
            [gt.Directive("TestDirective", {gt.DirectiveLocations.MUTATION}, {})]
        )


class ListTest(TypesTest):
    def test_str(self) -> None:
        self.assertEqual("[Boolean]", str(gt.List(gt.Boolean)))
        self.assertEqual("[Boolean!]", str(gt.List(gt.NonNull(gt.Boolean))))
        self.assertEqual("[[Boolean]]", str(gt.List(gt.List(gt.Boolean))))
        self.assertEqual("[Foo]", str(gt.List("Foo")))

    def test_assignment(self) -> None:
        self.assertTrue(gt.List(gt.Boolean).is_assignable([True, False, None], self.type_registry))
        self.assertTrue(gt.List(gt.Boolean).is_assignable(None, self.type_registry))
        self.assertTrue(gt.List(gt.Int).is_assignable([], self.type_registry))
        self.assertTrue(gt.List(gt.Int).is_assignable([1, None, 2, 3], self.type_registry))
        self.assertTrue(gt.List("TestInputObject").is_assignable([{"foo": 1.1}], self.type_registry))

        self.assertFalse(gt.List(gt.Boolean).is_assignable([True, False, 1], self.type_registry))
        self.assertFalse(gt.List(gt.NonNull(gt.Int)).is_assignable([1, None, 2, 3], self.type_registry))
        self.assertFalse(gt.List(gt.Boolean).is_assignable(True, self.type_registry))
        self.assertFalse(gt.List(gt.Int).is_assignable({}, self.type_registry))

        with self.assertRaises(RuntimeError) as m:
            gt.List("TestObject").is_assignable([{"foo": 1}], self.type_registry)
        self.assertEqual("Value must never be assigned to any composite type", str(m.exception))

    def test_validate_input(self) -> None:
        self.assertTrue(gt.List(gt.Boolean).validate_input(qm.ConstListValue([qm.BoolValue(True), qm.NullValue()]), {},
                                                           {}, self.type_registry))
        self.assertTrue(gt.List(gt.Boolean).validate_input(qm.NullValue(), {}, {}, self.type_registry))
        self.assertTrue(gt.List(gt.Int).validate_input(qm.ConstListValue([]), {}, {}, self.type_registry))
        self.assertTrue(gt.List(gt.Int).validate_input(qm.ListValue([qm.IntValue(1), qm.Variable("foo")]), {"foo": 4},
                                                       {"foo": gt.Int}, self.type_registry))
        self.assertTrue(gt.List(gt.Int).validate_input(qm.ListValue([qm.IntValue(1), qm.Variable("foo")]),
                                                       {"foo": None}, {"foo": gt.Int}, self.type_registry))
        self.assertTrue(gt.List(gt.Int).validate_input(qm.ListValue([qm.IntValue(1), qm.Variable("foo")]),
                                                       {}, {"foo": gt.Int}, self.type_registry))
        self.assertTrue(gt.List(gt.Int).validate_input(qm.Variable("foo"), {"foo": [1, 2, None]},
                                                       {"foo": gt.List(gt.Int)}, self.type_registry))
        self.assertTrue(gt.List(gt.Int).validate_input(qm.Variable("foo"), {}, {"foo": gt.List(gt.Int)},
                                                       self.type_registry))

        self.assertFalse(gt.List(gt.Boolean).validate_input(qm.ConstListValue([qm.BoolValue(True), qm.IntValue(1)]),
                                                            {}, {}, self.type_registry))
        self.assertFalse(gt.List(gt.Boolean).validate_input(qm.BoolValue(False), {}, {}, self.type_registry))
        self.assertFalse(gt.List(gt.Int).validate_input(qm.ObjectValue({}), {}, {}, self.type_registry))
        self.assertFalse(gt.List(gt.Int).validate_input(qm.Variable("foo"), {"foo": ["foo"]}, {"foo": gt.List(gt.Int)},
                                                        self.type_registry))
        self.assertFalse(gt.List(gt.Int).validate_input(qm.Variable("foo"), {"foo": "foo"}, {"foo": gt.List(gt.Int)},
                                                        self.type_registry))

        with self.assertRaises(RuntimeError) as m:
            gt.List("TestObject").validate_input(qm.ConstListValue([qm.ConstObjectValue({"foo": qm.IntValue(1)})]),
                                                 {}, {}, self.type_registry)
        self.assertEqual("Validating input for wrapper of non input type", str(m.exception))

    def test_of_type(self) -> None:
        self.assertEqual("Boolean", str(gt.List(gt.Boolean).of_type(self.type_registry)))
        self.assertEqual("Boolean!", str(gt.List(gt.NonNull(gt.Boolean)).of_type(self.type_registry)))
        self.assertEqual("[Boolean]", str(gt.List(gt.List(gt.Boolean)).of_type(self.type_registry)))
        self.assertEqual("TestObject", str(gt.List("TestObject").of_type(self.type_registry)))
        self.assertTrue(isinstance(gt.List("TestObject").of_type(self.type_registry), gt.GqlType))
        self.assertEqual("TestInputObject", str(gt.List("TestInputObject").of_type(self.type_registry)))
        self.assertTrue(isinstance(gt.List("TestInputObject").of_type(self.type_registry), gt.GqlType))
        with self.assertRaises(RuntimeError) as m:
            gt.List("Foo").of_type(self.type_registry)
        self.assertEqual("Can not resolve `Foo` type", str(m.exception))


class NonNullTest(TypesTest):
    def test_str(self) -> None:
        self.assertEqual("Boolean!", str(gt.NonNull(gt.Boolean)))
        self.assertEqual("[Boolean]!", str(gt.NonNull(gt.List(gt.Boolean))))
        self.assertEqual("Foo!", str(gt.NonNull("Foo")))

    def test_is_assignable(self) -> None:
        self.assertTrue(gt.NonNull(gt.Boolean).is_assignable(True, self.type_registry))
        self.assertFalse(gt.NonNull(gt.Boolean).is_assignable(None, self.type_registry))
        with self.assertRaises(RuntimeError) as m:
            gt.NonNull("TestObject").is_assignable("foo", self.type_registry)
        self.assertEqual("Value must never be assigned to any composite type", str(m.exception))

    def test_validate_input(self) -> None:
        self.assertTrue(gt.NonNull(gt.Boolean).validate_input(qm.BoolValue(True), {}, {}, self.type_registry))
        self.assertFalse(gt.NonNull(gt.Boolean).validate_input(qm.NullValue(), {}, {}, self.type_registry))
        self.assertTrue(gt.NonNull(gt.Boolean).validate_input(qm.Variable("foo"), {"foo": True},
                                                              {"foo": gt.NonNull(gt.Boolean)}, self.type_registry))
        self.assertFalse(gt.NonNull(gt.Boolean).validate_input(qm.Variable("foo"), {"foo": None},
                                                               {"foo": gt.NonNull(gt.Boolean)}, self.type_registry))
        self.assertFalse(gt.NonNull(gt.Boolean).validate_input(qm.Variable("foo"), {},
                                                               {"foo": gt.NonNull(gt.Boolean)}, self.type_registry))
        with self.assertRaises(RuntimeError) as m:
            gt.NonNull("TestObject").validate_input(qm.ObjectValue({"foo": qm.IntValue(1)}), {}, {}, self.type_registry)
        self.assertEqual("Validating input for wrapper of non input type", str(m.exception))


class ArgumentTest(TypesTest):
    def test_is_assignable(self) -> None:
        self.assertTrue(gt.Argument(gt.Boolean, None).is_assignable(True, self.type_registry))
        self.assertFalse(gt.Argument(gt.Boolean, None).is_assignable("foo", self.type_registry))
        self.assertFalse(gt.Argument(gt.NonNull(gt.Boolean), None).is_assignable(None, self.type_registry))
        self.assertTrue(gt.Argument("TestInputObject", None).is_assignable({"foo": 1.1}, self.type_registry))
        self.assertFalse(gt.Argument("TestInputObject", None).is_assignable({"foo": 1}, self.type_registry))

    def test_validate_input(self) -> None:
        self.assertTrue(gt.Argument(gt.Boolean, None).validate_input(qm.BoolValue(True), {}, {}, self.type_registry))
        self.assertTrue(gt.Argument(gt.Boolean, None).validate_input(qm.Variable("foo"), {"foo": False},
                                                                     {"foo": gt.Boolean}, self.type_registry))
        self.assertTrue(gt.Argument(gt.Boolean, None).validate_input(qm.Variable("foo"), {"foo": None},
                                                                     {"foo": gt.Boolean}, self.type_registry))
        self.assertTrue(gt.Argument(gt.Boolean, None).validate_input(qm.Variable("foo"), {}, {"foo": gt.Boolean},
                                                                     self.type_registry))
        self.assertFalse(gt.Argument(gt.Boolean, None).validate_input(qm.Variable("foo"), {"foo": 1},
                                                                      {"foo": gt.Boolean}, self.type_registry))

    def test_type(self) -> None:
        self.assertEqual(gt.Boolean, gt.Argument(gt.Boolean, None).type(self.type_registry))
        self.assertEqual("TestInputObject!",
                         str(gt.Argument(gt.NonNull("TestInputObject"), None).type(self.type_registry)))
        self.assertTrue(isinstance(gt.Argument("TestInputObject", None).type(self.type_registry), gt.InputObject))
        self.assertEqual("TestInputObject",
                         str(gt.Argument("TestInputObject", None).type(self.type_registry)))
        a = gt.Argument(gt.Boolean, None)
        self.assertEqual(a.type(self.type_registry), a.type(self.type_registry))
        a = gt.Argument("TestInputObject", None)
        self.assertEqual(a.type(self.type_registry), a.type(self.type_registry))


class FieldTest(TypesTest):
    def test_is_assignable(self) -> None:
        self.assertTrue(gt.Field(gt.Boolean, {}).is_assignable(True, self.type_registry))
        self.assertFalse(gt.Field(gt.Boolean, {}).is_assignable("foo", self.type_registry))
        self.assertFalse(gt.Field(gt.NonNull(gt.Boolean), {}).is_assignable(None, self.type_registry))

        with self.assertRaises(RuntimeError) as m:
            self.assertTrue(gt.Field("TestInputObject", {}).is_assignable({"foo": 1.1}, self.type_registry))
        self.assertEqual("Output type expected here", str(m.exception))

        with self.assertRaises(RuntimeError) as m:
            self.assertTrue(gt.Field("TestObject", {}).is_assignable({"foo": 1.1}, self.type_registry))
        self.assertEqual("Value must never be assigned to any composite type", str(m.exception))

    def test_type(self) -> None:
        self.assertEqual(gt.Boolean, gt.Field(gt.Boolean, {}).type(self.type_registry))
        self.assertEqual("Foo!", str(gt.Field(gt.NonNull("Foo"), {}).type(self.type_registry)))
        self.assertTrue(isinstance(gt.Field("TestObject", {}).type(self.type_registry), gt.Object))
        self.assertEqual("TestObject",
                         str(gt.Field("TestObject", {}).type(self.type_registry)))
        a = gt.Field(gt.Boolean, {})
        self.assertEqual(a.type(self.type_registry), a.type(self.type_registry))
        a = gt.Field("TestObject", {})
        self.assertEqual(a.type(self.type_registry), a.type(self.type_registry))

        with self.assertRaises(RuntimeError) as m:
            gt.Field("TestInputObject", {}).type(self.type_registry)
        self.assertEqual("Output type expected here", str(m.exception))


class BooleanTest(TypesTest):
    def test_name(self) -> None:
        self.assertEqual("Boolean", str(gt.Boolean))

    def test_is_assignable(self) -> None:
        self.assertTrue(gt.Boolean.is_assignable(True, self.type_registry))
        self.assertTrue(gt.Boolean.is_assignable(False, self.type_registry))
        self.assertTrue(gt.Boolean.is_assignable(None, self.type_registry))
        self.assertFalse(gt.Boolean.is_assignable(1, self.type_registry))

    def test_validate_input(self) -> None:
        self.assertTrue(gt.Boolean.validate_input(qm.BoolValue(True), {}, {}, self.type_registry))
        self.assertTrue(gt.Boolean.validate_input(qm.BoolValue(False), {}, {}, self.type_registry))
        self.assertTrue(gt.Boolean.validate_input(qm.NullValue(), {}, {}, self.type_registry))
        self.assertFalse(gt.Boolean.validate_input(qm.IntValue(1), {}, {}, self.type_registry))

        self.assertTrue(gt.Boolean.validate_input(qm.Variable("foo"), {"foo": True}, {"foo": gt.Boolean},
                                                  self.type_registry))
        self.assertTrue(gt.Boolean.validate_input(qm.Variable("foo"), {"foo": False}, {"foo": gt.Boolean},
                                                  self.type_registry))
        self.assertTrue(gt.Boolean.validate_input(qm.Variable("foo"), {"foo": None}, {"foo": gt.Boolean},
                                                  self.type_registry))
        self.assertTrue(gt.Boolean.validate_input(qm.Variable("foo"), {}, {"foo": gt.Boolean},
                                                  self.type_registry))
        self.assertFalse(gt.Boolean.validate_input(qm.Variable("foo"), {"foo": 1}, {"foo": gt.Boolean},
                                                   self.type_registry))


class IntTest(TypesTest):
    def test_name(self) -> None:
        self.assertEqual("Int", str(gt.Int))

    def test_is_assignable(self) -> None:
        self.assertTrue(gt.Int.is_assignable(1, self.type_registry))
        self.assertTrue(gt.Int.is_assignable(None, self.type_registry))
        self.assertFalse(gt.Int.is_assignable("1", self.type_registry))

    def test_validate_input(self) -> None:
        self.assertTrue(gt.Int.validate_input(qm.IntValue(1), {}, {}, self.type_registry))
        self.assertTrue(gt.Int.validate_input(qm.NullValue(), {}, {}, self.type_registry))
        self.assertFalse(gt.Int.validate_input(qm.StrValue(""), {}, {}, self.type_registry))

        self.assertTrue(gt.Int.validate_input(qm.Variable("foo"), {"foo": 1}, {"foo": gt.Int}, self.type_registry))
        self.assertTrue(gt.Int.validate_input(qm.Variable("foo"), {"foo": None}, {"foo": gt.Int}, self.type_registry))
        self.assertTrue(gt.Int.validate_input(qm.Variable("foo"), {}, {"foo": gt.Int}, self.type_registry))
        self.assertFalse(gt.Int.validate_input(qm.Variable("foo"), {"foo": 1.1}, {"foo": gt.Int}, self.type_registry))


class FloatTest(TypesTest):
    def test_name(self) -> None:
        self.assertEqual("Float", str(gt.Float))

    def test_is_assignable(self) -> None:
        self.assertTrue(gt.Float.is_assignable(1.1, self.type_registry))
        self.assertTrue(gt.Float.is_assignable(None, self.type_registry))
        self.assertFalse(gt.Float.is_assignable(1, self.type_registry))

    def test_validate_input(self) -> None:
        self.assertTrue(gt.Float.validate_input(qm.FloatValue(1.1), {}, {}, self.type_registry))
        self.assertTrue(gt.Float.validate_input(qm.NullValue(), {}, {}, self.type_registry))
        self.assertFalse(gt.Float.validate_input(qm.IntValue(1), {}, {}, self.type_registry))

        self.assertTrue(gt.Float.validate_input(qm.Variable("foo"), {"foo": 1.1}, {"foo": gt.Float},
                                                self.type_registry))
        self.assertTrue(gt.Float.validate_input(qm.Variable("foo"), {"foo": None}, {"foo": gt.Float},
                                                self.type_registry))
        self.assertTrue(gt.Float.validate_input(qm.Variable("foo"), {}, {"foo": gt.Float},
                                                self.type_registry))
        self.assertFalse(gt.Float.validate_input(qm.Variable("foo"), {"foo": 1}, {"foo": gt.Float},
                                                 self.type_registry))


class StringTest(TypesTest):
    def test_name(self) -> None:
        self.assertEqual("String", str(gt.String))

    def test_is_assignable(self) -> None:
        self.assertTrue(gt.String.is_assignable("foo", self.type_registry))
        self.assertTrue(gt.String.is_assignable(None, self.type_registry))
        self.assertFalse(gt.String.is_assignable(1, self.type_registry))

    def test_validate_input(self) -> None:
        self.assertTrue(gt.String.validate_input(qm.StrValue(""), {}, {}, self.type_registry))
        self.assertTrue(gt.String.validate_input(qm.NullValue(), {}, {}, self.type_registry))
        self.assertFalse(gt.String.validate_input(qm.IntValue(1), {}, {}, self.type_registry))

        self.assertTrue(gt.String.validate_input(qm.Variable("foo"), {"foo": "foo"}, {"foo": gt.String},
                                                 self.type_registry))
        self.assertTrue(gt.String.validate_input(qm.Variable("foo"), {"foo": None}, {"foo": gt.String},
                                                 self.type_registry))
        self.assertTrue(gt.String.validate_input(qm.Variable("foo"), {}, {"foo": gt.String}, self.type_registry))
        self.assertFalse(gt.String.validate_input(qm.Variable("foo"), {"foo": 1}, {"foo": gt.String},
                                                  self.type_registry))


class IdTest(TypesTest):
    def test_name(self) -> None:
        self.assertEqual("ID", str(gt.ID))

    def test_is_assignable(self) -> None:
        self.assertTrue(gt.ID.is_assignable(1, self.type_registry))
        self.assertTrue(gt.ID.is_assignable("foo", self.type_registry))
        self.assertTrue(gt.ID.is_assignable(None, self.type_registry))
        self.assertFalse(gt.ID.is_assignable(1.2, self.type_registry))

    def test_validate_input(self) -> None:
        self.assertTrue(gt.ID.validate_input(qm.IntValue(2), {}, {}, self.type_registry))
        self.assertTrue(gt.ID.validate_input(qm.StrValue("foo"), {}, {}, self.type_registry))
        self.assertTrue(gt.ID.validate_input(qm.NullValue(), {}, {}, self.type_registry))
        self.assertFalse(gt.ID.validate_input(qm.BoolValue(True), {}, {}, self.type_registry))

        self.assertTrue(gt.ID.validate_input(qm.Variable("foo"), {"foo": 1}, {"foo": gt.ID}, self.type_registry))
        self.assertTrue(gt.ID.validate_input(qm.Variable("foo"), {"foo": "bar"}, {"foo": gt.ID}, self.type_registry))
        self.assertTrue(gt.ID.validate_input(qm.Variable("foo"), {"foo": None}, {"foo": gt.ID}, self.type_registry))
        self.assertTrue(gt.ID.validate_input(qm.Variable("foo"), {}, {"foo": gt.ID}, self.type_registry))
        self.assertFalse(gt.ID.validate_input(qm.Variable("foo"), {"foo": 1.1}, {"foo": gt.ID}, self.type_registry))


class EnumTest(TypesTest):
    def test_valudation(self) -> None:
        with self.assertRaises(GqlSchemaError) as m:
            gt.Enum("Test", {"V1"})
        self.assertEqual("Enum must define at least 2 possible values", str(m.exception))
        with self.assertRaises(GqlSchemaError) as m:
            gt.Enum("Test", set())
        self.assertEqual("Enum must define at least 2 possible values", str(m.exception))
        gt.Enum("Test", {"V1", "V2"})

    def test_name(self) -> None:
        self.assertEqual("TestEnum", str(gt.Enum("TestEnum", {"V1", "V2"})))

    def test_is_assignable(self) -> None:
        self.assertTrue(gt.Enum("TestEnum", {"V1", "V2"}).is_assignable("V1", self.type_registry))
        self.assertTrue(gt.Enum("TestEnum", {"V1", "V2"}).is_assignable("V2", self.type_registry))
        self.assertTrue(gt.Enum("TestEnum", {"V1", "V2"}).is_assignable(None, self.type_registry))
        self.assertFalse(gt.Enum("TestEnum", {"V1", "V2"}).is_assignable("V3", self.type_registry))
        self.assertFalse(gt.Enum("TestEnum", {"V1", "V2"}).is_assignable(1, self.type_registry))

    def test_validate_input(self) -> None:
        test_enum = gt.Enum("TestEnum", {"V1", "V2"})

        self.assertTrue(test_enum.validate_input(qm.EnumValue("V1"), {}, {}, self.type_registry))
        self.assertTrue(test_enum.validate_input(qm.EnumValue("V2"), {}, {}, self.type_registry))
        self.assertTrue(test_enum.validate_input(qm.NullValue(), {}, {}, self.type_registry))
        self.assertFalse(test_enum.validate_input(qm.EnumValue("V3"), {}, {}, self.type_registry))
        self.assertFalse(test_enum.validate_input(qm.BoolValue(True), {}, {}, self.type_registry))

        self.assertTrue(test_enum.validate_input(qm.Variable("foo"), {"foo": "V1"}, {"foo": test_enum},
                                                 self.type_registry))
        self.assertTrue(test_enum.validate_input(qm.Variable("foo"), {"foo": "V2"}, {"foo": test_enum},
                                                 self.type_registry))
        self.assertTrue(test_enum.validate_input(qm.Variable("foo"), {"foo": None}, {"foo": test_enum},
                                                 self.type_registry))
        self.assertTrue(test_enum.validate_input(qm.Variable("foo"), {}, {"foo": test_enum},
                                                 self.type_registry))
        self.assertFalse(test_enum.validate_input(qm.Variable("foo"), {"foo": "V3"}, {"foo": test_enum},
                                                  self.type_registry))
        self.assertFalse(test_enum.validate_input(qm.Variable("foo"), {"foo": 1.1}, {"foo": test_enum},
                                                  self.type_registry))


class InputObjectTest(TypesTest):
    def test_validation(self) -> None:
        with self.assertRaises(GqlSchemaError) as m:
            gt.InputObject("Foo", {})
        self.assertEqual("InputObject must define at least one field", str(m.exception))

    def test_fields(self) -> None:
        fields = gt.InputObject("Foo", {
            "i": gt.Int,
            "w1": gt.NonNull(gt.Float),
            "w2": gt.NonNull("TestInputObject"),
            "io": "TestInputObject"
        }).fields(self.type_registry)
        self.assertEqual("Int", str(fields["i"]))
        self.assertEqual("Float!", str(fields["w1"]))
        self.assertEqual("TestInputObject!", str(fields["w2"]))
        self.assertEqual("TestInputObject", str(fields["io"]))
        self.assertTrue(isinstance(fields["io"], gt.InputObject))

        with self.assertRaises(RuntimeError) as m:
            gt.InputObject("Test", {"foo": "TestObject"}).fields(self.type_registry)
        self.assertEqual("Input type expected here", str(m.exception))

    def test_is_assignable(self) -> None:
        io = gt.InputObject("Foo", {
            "i": gt.Int,
            "w1": gt.NonNull(gt.Float),
            "w2": gt.NonNull("TestInputObject"),
            "io": "TestInputObject"
        })
        self.assertTrue(io.is_assignable({"i": None, "w1": 1.1, "w2": {"foo": 1.1}}, self.type_registry))
        self.assertFalse(io.is_assignable({"i": None, "w1": 1.1, "w2": {"foo": 1.1}, "foo": 1}, self.type_registry))
        self.assertFalse(io.is_assignable([], self.type_registry))

    def test_validate_input(self) -> None:
        io = gt.InputObject("Foo", {
            "i": gt.Int,
            "w1": gt.NonNull(gt.Float),
            "w2": gt.NonNull("TestInputObject"),
            "io": "TestInputObject"
        })
        self.assertTrue(io.validate_input(qm.ConstObjectValue({
            "i": qm.NullValue(),
            "w1": qm.FloatValue(1.1),
            "w2": qm.ConstObjectValue({"foo": qm.FloatValue(1.1)})
        }), {}, {}, self.type_registry))
        self.assertFalse(io.validate_input(qm.ConstObjectValue({
            "i": qm.NullValue(),
            "w1": qm.FloatValue(1.1),
            "w2": qm.ConstObjectValue({"foo": qm.FloatValue(1.1)}),
            "foo": qm.NullValue()
        }), {}, {}, self.type_registry))
        self.assertFalse(io.validate_input(qm.ConstListValue([]), {}, {}, self.type_registry))

        self.assertTrue(io.validate_input(qm.Variable("foo"), {}, {"foo": io}, self.type_registry))
        self.assertTrue(io.validate_input(qm.Variable("foo"), {"foo": {"i": None, "w1": 1.1, "w2": {"foo": 1.1}}},
                                          {"foo": io}, self.type_registry))
        self.assertTrue(io.validate_input(qm.ObjectValue({
            "i": qm.NullValue(),
            "w1": qm.FloatValue(1.1),
            "w2": qm.Variable("foo")
        }), {"foo": {"foo": 1.1}}, {"foo": gt.NonNull("TestInputObject")}, self.type_registry))
        self.assertFalse(io.validate_input(qm.ObjectValue({
            "i": qm.NullValue(),
            "w1": qm.FloatValue(1.1),
            "w2": qm.Variable("foo")
        }), {"foo": 1.1}, {"foo": gt.NonNull("TestInputObject")}, self.type_registry))


class ObjectTest(TypesTest):
    def test_validation(self) -> None:
        with self.assertRaises(GqlSchemaError) as m:
            gt.Object("Foo", {}, set())
        self.assertEqual("Object must define at least one field or implement interface", str(m.exception))
        gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())
        gt.Object("Foo", {}, set("I"))

    def test_name(self) -> None:
        self.assertEqual("Foo", str(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))


class UnionTest(TypesTest):
    def test_validation(self) -> None:
        with self.assertRaises(GqlSchemaError) as m:
            gt.Union("Foo", set())
        self.assertEqual("Union must unite at least 2 objects", str(m.exception))
        with self.assertRaises(GqlSchemaError) as m:
            gt.Union("Foo", {"TestObject"})
        self.assertEqual("Union must unite at least 2 objects", str(m.exception))

    def test_of_objects(self) -> None:
        with self.assertRaises(RuntimeError) as m:
            gt.Union("Foo", {"TestObject", "Abc"}).of_objects(self.type_registry)
        self.assertEqual("Can not resolve `Abc` type", str(m.exception))
        with self.assertRaises(RuntimeError) as m:
            gt.Union("Foo", {"TestObject", "TestInputObject"}).of_objects(self.type_registry)
        self.assertEqual("Object expected here", str(m.exception))

        union = gt.Union("Foo", {"TestObject", "TestObject2"})
        objs = union.of_objects(self.type_registry)
        self.assertEqual({"TestObject", "TestObject2"}, {str(obj) for obj in objs})

        for obj in objs:
            self.assertTrue(isinstance(obj, gt.Object))

        self.assertEqual(objs, union.of_objects(self.type_registry))

    def test_name(self) -> None:
        self.assertEqual("Foo", str(gt.Union("Foo", {"TestObject", "TestObject2"})))

    def test_is_assignable(self) -> None:
        with self.assertRaises(RuntimeError) as m:
            gt.Union("Foo", {"TestObject", "TestObject2"}).is_assignable(1, self.type_registry)
        self.assertEqual("Value must never be assigned to union", str(m.exception))


class TypeClassificationTest(TypesTest):
    def test_scalar(self) -> None:
        self.assertIsNotNone(gt.is_scalar(gt.Boolean))
        self.assertIsNotNone(gt.is_scalar(gt.Int))
        self.assertIsNotNone(gt.is_scalar(gt.Float))
        self.assertIsNotNone(gt.is_scalar(gt.String))
        self.assertIsNotNone(gt.is_scalar(gt.ID))
        self.assertIsNone(gt.is_scalar(gt.Enum("Foo", {"V1", "V2"})))
        self.assertIsNone(gt.is_scalar(gt.NonNull(gt.Int)))
        self.assertIsNone(gt.is_scalar(gt.List(gt.Int)))
        self.assertIsNone(gt.is_scalar(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})})))
        self.assertIsNone(gt.is_scalar(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))
        self.assertIsNone(gt.is_scalar(gt.Union("Foo", {"O1", "O2"})))
        self.assertIsNone(gt.is_scalar(gt.InputObject("Foo", {"foo": gt.Int})))

        with self.assertRaises(RuntimeError) as m:
            gt.assert_scalar(gt.Enum("Foo", {"V1", "V2"}))
        self.assertEqual("Scalar expected here", str(m.exception))
        gt.assert_scalar(gt.Int)

    def test_wrapper(self) -> None:
        self.assertIsNone(gt.is_wrapper(gt.Boolean))
        self.assertIsNone(gt.is_wrapper(gt.Int))
        self.assertIsNone(gt.is_wrapper(gt.Float))
        self.assertIsNone(gt.is_wrapper(gt.String))
        self.assertIsNone(gt.is_wrapper(gt.ID))
        self.assertIsNone(gt.is_wrapper(gt.Enum("Foo", {"V1", "V2"})))
        self.assertIsNotNone(gt.is_wrapper(gt.NonNull(gt.Int)))
        self.assertIsNotNone(gt.is_wrapper(gt.List(gt.Int)))
        self.assertIsNone(gt.is_wrapper(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})})))
        self.assertIsNone(gt.is_wrapper(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))
        self.assertIsNone(gt.is_wrapper(gt.Union("Foo", {"O1", "O2"})))
        self.assertIsNone(gt.is_wrapper(gt.InputObject("Foo", {"foo": gt.Int})))

        with self.assertRaises(RuntimeError) as m:
            gt.assert_wrapper(gt.Enum("Foo", {"V1", "V2"}))
        self.assertEqual("Wrapper expected here", str(m.exception))
        gt.assert_wrapper(gt.NonNull(gt.Int))

    def test_non_wrapper(self) -> None:
        self.assertIsNotNone(gt.is_non_wrapper(gt.Boolean))
        self.assertIsNotNone(gt.is_non_wrapper(gt.Int))
        self.assertIsNotNone(gt.is_non_wrapper(gt.Float))
        self.assertIsNotNone(gt.is_non_wrapper(gt.String))
        self.assertIsNotNone(gt.is_non_wrapper(gt.ID))
        self.assertIsNotNone(gt.is_non_wrapper(gt.Enum("Foo", {"V1", "V2"})))
        self.assertIsNone(gt.is_non_wrapper(gt.NonNull(gt.Int)))
        self.assertIsNone(gt.is_non_wrapper(gt.List(gt.Int)))
        self.assertIsNotNone(gt.is_non_wrapper(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})})))
        self.assertIsNotNone(gt.is_non_wrapper(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))
        self.assertIsNotNone(gt.is_non_wrapper(gt.Union("Foo", {"O1", "O2"})))
        self.assertIsNotNone(gt.is_non_wrapper(gt.InputObject("Foo", {"foo": gt.Int})))

        with self.assertRaises(RuntimeError) as m:
            gt.assert_non_wrapper(gt.NonNull(gt.Int))
        self.assertEqual("Non wrapper expected here", str(m.exception))
        gt.assert_non_wrapper(gt.Boolean)

    def test_spreadable(self) -> None:
        self.assertIsNone(gt.is_spreadable(gt.Boolean))
        self.assertIsNone(gt.is_spreadable(gt.Int))
        self.assertIsNone(gt.is_spreadable(gt.Float))
        self.assertIsNone(gt.is_spreadable(gt.String))
        self.assertIsNone(gt.is_spreadable(gt.ID))
        self.assertIsNone(gt.is_spreadable(gt.Enum("Foo", {"V1", "V2"})))
        self.assertIsNone(gt.is_spreadable(gt.NonNull(gt.Int)))
        self.assertIsNone(gt.is_spreadable(gt.List(gt.Int)))
        self.assertIsNotNone(gt.is_spreadable(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})})))
        self.assertIsNotNone(gt.is_spreadable(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))
        self.assertIsNotNone(gt.is_spreadable(gt.Union("Foo", {"O1", "O2"})))
        self.assertIsNone(gt.is_spreadable(gt.InputObject("Foo", {"foo": gt.Int})))

        with self.assertRaises(RuntimeError) as m:
            gt.assert_spreadable(gt.Enum("Foo", {"V1", "V2"}))
        self.assertEqual("Spreadable expected here", str(m.exception))
        gt.assert_spreadable(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})}))

    def test_selectable(self) -> None:
        self.assertIsNone(gt.is_selectable(gt.Boolean))
        self.assertIsNone(gt.is_selectable(gt.Int))
        self.assertIsNone(gt.is_selectable(gt.Float))
        self.assertIsNone(gt.is_selectable(gt.String))
        self.assertIsNone(gt.is_selectable(gt.ID))
        self.assertIsNone(gt.is_selectable(gt.Enum("Foo", {"V1", "V2"})))
        self.assertIsNone(gt.is_selectable(gt.NonNull(gt.Int)))
        self.assertIsNone(gt.is_selectable(gt.List(gt.Int)))
        self.assertIsNotNone(gt.is_selectable(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})})))
        self.assertIsNotNone(gt.is_selectable(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))
        self.assertIsNone(gt.is_selectable(gt.Union("Foo", {"O1", "O2"})))
        self.assertIsNone(gt.is_selectable(gt.InputObject("Foo", {"foo": gt.Int})))

        with self.assertRaises(RuntimeError) as m:
            gt.assert_selectable(gt.Enum("Foo", {"V1", "V2"}))
        self.assertEqual("Selectable expected here", str(m.exception))
        gt.assert_selectable(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})}))

    def test_input(self) -> None:
        self.assertIsNotNone(gt.is_input(gt.Boolean))
        self.assertIsNotNone(gt.is_input(gt.Int))
        self.assertIsNotNone(gt.is_input(gt.Float))
        self.assertIsNotNone(gt.is_input(gt.String))
        self.assertIsNotNone(gt.is_input(gt.ID))
        self.assertIsNotNone(gt.is_input(gt.Enum("Foo", {"V1", "V2"})))
        self.assertIsNone(gt.is_input(gt.NonNull(gt.Int)))
        self.assertIsNone(gt.is_input(gt.List(gt.Int)))
        self.assertIsNone(gt.is_input(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})})))
        self.assertIsNone(gt.is_input(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))
        self.assertIsNone(gt.is_input(gt.Union("Foo", {"O1", "O2"})))
        self.assertIsNotNone(gt.is_input(gt.InputObject("Foo", {"foo": gt.Int})))

        with self.assertRaises(RuntimeError) as m:
            gt.assert_input(gt.Union("Foo", {"O1", "O2"}))
        self.assertEqual("Input type expected here", str(m.exception))
        gt.assert_input(gt.Boolean)

    def test_output(self) -> None:
        self.assertIsNotNone(gt.is_output(gt.Boolean))
        self.assertIsNotNone(gt.is_output(gt.Int))
        self.assertIsNotNone(gt.is_output(gt.Float))
        self.assertIsNotNone(gt.is_output(gt.String))
        self.assertIsNotNone(gt.is_output(gt.ID))
        self.assertIsNotNone(gt.is_output(gt.Enum("Foo", {"V1", "V2"})))
        self.assertIsNone(gt.is_output(gt.NonNull(gt.Int)))
        self.assertIsNone(gt.is_output(gt.List(gt.Int)))
        self.assertIsNotNone(gt.is_output(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})})))
        self.assertIsNotNone(gt.is_output(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))
        self.assertIsNotNone(gt.is_output(gt.Union("Foo", {"O1", "O2"})))
        self.assertIsNone(gt.is_output(gt.InputObject("Foo", {"foo": gt.Int})))

        with self.assertRaises(RuntimeError) as m:
            gt.assert_output(gt.InputObject("Foo", {"foo": gt.Int}))
        self.assertEqual("Output type expected here", str(m.exception))
        gt.assert_output(gt.Boolean)

    def test_user(self) -> None:
        self.assertIsNone(gt.is_user(gt.Boolean))
        self.assertIsNone(gt.is_user(gt.Int))
        self.assertIsNone(gt.is_user(gt.Float))
        self.assertIsNone(gt.is_user(gt.String))
        self.assertIsNone(gt.is_user(gt.ID))
        self.assertIsNotNone(gt.is_user(gt.Enum("Foo", {"V1", "V2"})))
        self.assertIsNone(gt.is_user(gt.NonNull(gt.Int)))
        self.assertIsNone(gt.is_user(gt.List(gt.Int)))
        self.assertIsNotNone(gt.is_user(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})})))
        self.assertIsNotNone(gt.is_user(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))
        self.assertIsNotNone(gt.is_user(gt.Union("Foo", {"O1", "O2"})))
        self.assertIsNotNone(gt.is_user(gt.InputObject("Foo", {"foo": gt.Int})))

        with self.assertRaises(RuntimeError) as m:
            gt.assert_user(gt.ID)
        self.assertEqual("User defined type expected here", str(m.exception))
        gt.assert_user(gt.Enum("Foo", {"V1", "V2"}))

    def test_inline(self) -> None:
        self.assertIsNotNone(gt.is_inline(gt.Boolean))
        self.assertIsNotNone(gt.is_inline(gt.Int))
        self.assertIsNotNone(gt.is_inline(gt.Float))
        self.assertIsNotNone(gt.is_inline(gt.String))
        self.assertIsNotNone(gt.is_inline(gt.ID))
        self.assertIsNone(gt.is_inline(gt.Enum("Foo", {"V1", "V2"})))
        self.assertIsNotNone(gt.is_inline(gt.NonNull(gt.Int)))
        self.assertIsNotNone(gt.is_inline(gt.List(gt.Int)))
        self.assertIsNone(gt.is_inline(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})})))
        self.assertIsNone(gt.is_inline(gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())))
        self.assertIsNone(gt.is_inline(gt.Union("Foo", {"O1", "O2"})))
        self.assertIsNone(gt.is_inline(gt.InputObject("Foo", {"foo": gt.Int})))

        with self.assertRaises(RuntimeError) as m:
            gt.assert_inline(gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})}))
        self.assertEqual("Inline type expected expected here", str(m.exception))
        gt.assert_inline(gt.Boolean)


class DirectiveTest(TypesTest):
    def test_name(self) -> None:
        self.assertEqual("@foo", str(gt.Directive("foo", {gt.DirectiveLocations.MUTATION}, {})))


class TypeRegistryTest(TypesTest):
    def test_resolve_type(self) -> None:
        tr = self.type_registry
        self.assertEqual(gt.Boolean, tr.resolve_type("Boolean"))
        self.assertEqual(gt.Int, tr.resolve_type("Int"))
        self.assertEqual(gt.Float, tr.resolve_type("Float"))
        self.assertEqual(gt.String, tr.resolve_type("String"))
        self.assertEqual(gt.ID, tr.resolve_type("ID"))

        self.assertTrue(isinstance(tr.resolve_type("TestObject"), gt.Object))
        self.assertTrue(isinstance(tr.resolve_type("TestObject2"), gt.Object))
        self.assertTrue(isinstance(tr.resolve_type("TestInputObject"), gt.InputObject))

        self.assertTrue(isinstance(tr.resolve_type("__Schema"), gt.Object))
        self.assertTrue(isinstance(tr.resolve_type("__Type"), gt.Object))
        self.assertTrue(isinstance(tr.resolve_type("__Field"), gt.Object))
        self.assertTrue(isinstance(tr.resolve_type("__InputValue"), gt.Object))
        self.assertTrue(isinstance(tr.resolve_type("__EnumValue"), gt.Object))
        self.assertTrue(isinstance(tr.resolve_type("__TypeKind"), gt.Enum))
        self.assertTrue(isinstance(tr.resolve_type("__Directive"), gt.Object))
        self.assertTrue(isinstance(tr.resolve_type("__DirectiveLocation"), gt.Enum))

        with self.assertRaises(RuntimeError) as m:
            tr.resolve_type("Foo")
        self.assertEqual("Can not resolve `Foo` type", str(m.exception))

    def test_resolve_and_unwrap(self) -> None:
        tr = self.type_registry

        self.assertEqual(gt.Int, tr.resolve_and_unwrap(gt.Int))
        self.assertEqual(gt.Int, tr.resolve_and_unwrap(gt.NonNull(gt.Int)))
        self.assertEqual(gt.Int, tr.resolve_and_unwrap(gt.List(gt.NonNull(gt.Int))))
        self.assertEqual(gt.Int, tr.resolve_and_unwrap(gt.NonNull(gt.List(gt.NonNull(gt.Int)))))
        self.assertEqual(gt.Int, tr.resolve_and_unwrap(gt.List(gt.List(gt.NonNull(gt.Int)))))

        self.assertEqual("TestObject", str(tr.resolve_and_unwrap(gt.List(gt.List(gt.NonNull("TestObject"))))))
        self.assertTrue(isinstance(tr.resolve_and_unwrap(gt.List(gt.List(gt.NonNull("TestObject")))), gt.Object))

    def test_objects_by_interface(self) -> None:
        tr = gt.TypeRegistry(
            [
                gt.Interface("I1", {"foo": gt.Field(gt.Int, {})}),
                gt.Interface("I2", {"bar": gt.Field(gt.Int, {})}),
                gt.Object("O1", {}, {"I1"}),
                gt.Object("O2", {}, {"I1", "I2"}),
                gt.Object("O3", {}, {"I2"}),
                gt.Object("O4", {}, {"I2"}),
                gt.Object("O5", {}, {"I2"}),
                gt.Object("O6", {"foo": gt.Field(gt.Int, {})}, set())
            ], []
        )
        self.assertEqual({"O1", "O2"}, set((str(o) for o in tr.objects_by_interface("I1"))))
        self.assertEqual({"O2", "O3", "O4", "O5"}, set((str(o) for o in tr.objects_by_interface("I2"))))

    def assertValidationError(self, error: str, types: t.Sequence[gt.UserType],
                              directives: t.Optional[t.Sequence[gt.Directive]] = None) -> None:
        with self.assertRaises(GqlSchemaError) as m:
            gt.TypeRegistry(types, [] if directives is None else directives)
        self.assertEqual(error, str(m.exception))

    def test_validate_refs(self) -> None:
        self.assertValidationError("Can not resolve `IO` type; problem with `foo` field of `I1` type", [
            gt.Interface("I1", {"foo": gt.Field("IO", {})})
        ])

        self.assertValidationError("Can not resolve `Foo` type; problem with `a` argument of `foo` field of `I1` type",
                                   [
                                       gt.Interface("I1", {"foo": gt.Field(gt.Int, {"a": gt.Argument("Foo", None)})})
                                   ])

        self.assertValidationError("Can not resolve `IO` type; problem with `foo` field of `O1` type", [
            gt.Object("O1", {"foo": gt.Field("IO", {})}, set())
        ])

        self.assertValidationError(
            "Can not resolve `Foo` type; problem with `a` argument of `foo` field of `O1` type", [
                gt.Object("O1", {"foo": gt.Field(gt.Int, {"a": gt.Argument("Foo", None)})}, set())
            ]
        )

        gt.TypeRegistry([
            gt.InputObject("Foo", {"foo": gt.Int}),
            gt.Object("O1", {"foo": gt.Field(gt.Int, {"a": gt.Argument("Foo", None)})}, set())
        ], [])

        self.assertValidationError(
            "Can not resolve `I1` type; problem with `O1` object", [
                gt.Object("O1", {"foo": gt.Field(gt.Int, {})}, {"I1"})
            ]
        )

        self.assertValidationError(
            "Object must implement only interfaces; problem with `I1` interface of `O1` object", [
                gt.Object("I1", {"foo": gt.Field(gt.Int, {})}, set()),
                gt.Object("O1", {"foo": gt.Field(gt.Int, {})}, {"I1"})
            ]
        )

        self.assertValidationError(
            "Can not resolve `O2` type; problem with `U1` union", [
                gt.Object("O1", {"foo": gt.Field(gt.Int, {})}, set()),
                gt.Union("U1", {"O1", "O2"})
            ]
        )

        self.assertValidationError(
            "Union must unite only objects; problem with `I1` object of `U1` union", [
                gt.Object("O1", {"foo": gt.Field(gt.Int, {})}, set()),
                gt.Interface("I1", {"foo": gt.Field(gt.Int, {})}),
                gt.Union("U1", {"O1", "I1"})
            ]
        )

        self.assertValidationError(
            "Can not resolve `IO` type; problem with `foo` field of `IO1` input object", [
                gt.InputObject("IO1", {"foo": "IO"})
            ]
        )

    def test_validate_names(self) -> None:
        self.assertValidationError("Wrong type name: /[_A-Za-z][_0-9A-Za-z]*/ expected, but got '!Foo'", [
            gt.Interface("!Foo", {"foo": gt.Field(gt.Int, {})})
        ])

        self.assertValidationError(
            "Wrong name of field: /[_A-Za-z][_0-9A-Za-z]*/ expected, but got '!foo' in `Foo` type", [
                gt.Interface("Foo", {"!foo": gt.Field(gt.Int, {})})
            ]
        )

        self.assertValidationError(
            "Wrong name of field: /[_A-Za-z][_0-9A-Za-z]*/ expected, but got '!foo' in `Foo` type", [
                gt.InputObject("Foo", {"!foo": gt.Int})
            ]
        )

        self.assertValidationError(
            "Wrong name of argument: /[_A-Za-z][_0-9A-Za-z]*/ expected, but got '!bar'; "
            "problem with `!bar` argument of `foo` field of `Foo` type", [
                gt.Object("Foo", {"foo": gt.Field(gt.Int, {"!bar": gt.Argument(gt.Int, None)})}, set())
            ]
        )

        self.assertValidationError(
            "Can not redeclare standard type `__Schema`", [
                gt.Object("__Schema", {"foo": gt.Field(gt.Int, {})}, set())
            ]
        )

        self.assertValidationError(
            "Wrong name of directive: /[_A-Za-z][_0-9A-Za-z]*/ expected, but got '!foo'", [],
            [
                gt.Directive("!foo", {gt.DirectiveLocations.MUTATION}, {})
            ]
        )

        self.assertValidationError(
            "Type re-definition; problem with `Foo` type", [
                gt.Interface("Foo", {"foo": gt.Field(gt.Int, {})}),
                gt.InputObject("Foo", {"foo": gt.Int})
            ]
        )

    def test_input_output_types(self) -> None:
        self.assertValidationError(
            "Output type expected here; problem with `foo` field of `Foo` type", [
                gt.InputObject("IO1", {"foo": gt.Int}),
                gt.Interface("Foo", {"foo": gt.Field("IO1", {})})
            ]
        )

        self.assertValidationError(
            "Input type expected; problem with `bar` argument of `foo` field of `Foo` type", [
                gt.Object("O1", {"foo": gt.Field(gt.Int, {})}, set()),
                gt.Interface("Foo", {"foo": gt.Field(gt.Int, {"bar": gt.Argument("O1", None)})})
            ]
        )

    def test_argument_default(self) -> None:
        gt.TypeRegistry(
            [
                gt.InputObject("IO1", {"foo": gt.Int}),
                gt.Interface("Foo", {"foo": gt.Field(gt.Int, {"bar": gt.Argument("IO1", {"foo": 1})})})
            ],
            []
        )

        self.assertValidationError(
            "{\"foo\": 1.1} is not assignable to `IO1` type; problem with `bar` argument of `foo` field of `Foo` type",
            [
                gt.InputObject("IO1", {"foo": gt.Int}),
                gt.Interface("Foo", {"foo": gt.Field(gt.Int, {"bar": gt.Argument("IO1", {"foo": 1.1})})})
            ]
        )

    def test_fields_redeclaration(self) -> None:
        gt.TypeRegistry(
            [
                gt.Interface("I1", {"foo": gt.Field(gt.Int, {})}),
                gt.Interface("I2", {"bar": gt.Field(gt.Int, {})}),
                gt.Interface("I3", {"bar": gt.Field(gt.Int, {})}),
                gt.Object("O1", {"abc": gt.Field(gt.Int, {})}, {"I1", "I2"})
            ],
            []
        )

        self.assertValidationError(
            "Object `O1` redeclare `bar` field of `I2` interface",
            [
                gt.Interface("I1", {"foo": gt.Field(gt.Int, {})}),
                gt.Interface("I2", {"bar": gt.Field(gt.Int, {})}),
                gt.Interface("I3", {"bar": gt.Field(gt.Int, {})}),
                gt.Object("O1", {"bar": gt.Field(gt.Int, {})}, {"I1", "I2"})
            ]
        )

        self.assertValidationError(
            "Interfaces `I2` and `I3` of `O1` object both declare `bar` field",
            [
                gt.Interface("I1", {"foo": gt.Field(gt.Int, {})}),
                gt.Interface("I2", {"bar": gt.Field(gt.Int, {})}),
                gt.Interface("I3", {"bar": gt.Field(gt.Int, {})}),
                gt.Object("O1", {"abc": gt.Field(gt.Int, {})}, {"I1", "I2", "I3"})
            ]
        )

    def test_directive_args(self) -> None:
        gt.TypeRegistry(
            [], [
                gt.Directive("foo", {gt.DirectiveLocations.MUTATION}, {"foo": gt.Argument(gt.Int, 1)})
            ]
        )

        self.assertValidationError(
            "Can not resolve `Foo` type; problem with `foo` argument of `foo` directive", [],
            [
                gt.Directive("foo", {gt.DirectiveLocations.MUTATION}, {"foo": gt.Argument("Foo", None)})
            ]
        )

        self.assertValidationError(
            "Input type expected; problem with `foo` argument of `foo` directive",
            [
                gt.Object("Foo", {"foo": gt.Field(gt.Int, {})}, set())
            ],
            [
                gt.Directive("foo", {gt.DirectiveLocations.MUTATION}, {"foo": gt.Argument("Foo", None)})
            ]
        )

        self.assertValidationError(
            "\"1\" is not assignable to `Int` type; problem with `foo` argument of `foo` directive", [],
            [
                gt.Directive("foo", {gt.DirectiveLocations.MUTATION}, {"foo": gt.Argument(gt.Int, "1")})
            ]
        )
