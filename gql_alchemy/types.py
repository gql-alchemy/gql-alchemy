import json
import re
import typing as t

import gql_alchemy.query_model as qm
from .errors import GqlSchemaError
from .utils import PrimitiveType


class _SchemaAssertionError(RuntimeError):
    def __init__(self, message: str, name: str) -> None:
        super().__init__(message, name)

    def __str__(self) -> str:
        return t.cast(str, self.args[0])


class TypeResolvingError(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__("Can not resolve `{}` type".format(name), name)

    def __str__(self) -> str:
        return t.cast(str, self.args[0])


class UndefinedVariableError(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__("Undefined variable `{}`".format(name), name)

    def __str__(self) -> str:
        return t.cast(str, self.args[0])


class NonCompatibleVariableType(RuntimeError):
    def __init__(self, var_name: str, expected: 'GqlType', got: 'GqlType') -> None:
        super().__init__(
            "Type of `{}` variable is not compatible, `{}` expected, but got `{}`".format(var_name, expected, got),
            var_name, expected, got)

    def __str__(self) -> str:
        return t.cast(str, self.args[0])


class GqlType:
    def __init__(self, name: str) -> None:
        self.__name = name

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        raise NotImplementedError()

    def __str__(self) -> str:
        return self.__name


class _PossibleInputType(GqlType):
    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        raise NotImplementedError()

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        raise NotImplementedError()


class _TypeWrapper(_PossibleInputType):
    def __init__(self, of_type: t.Union['InlineType', str]) -> None:
        if isinstance(of_type, GqlType):
            of_type_name = str(of_type)
        else:
            of_type_name = of_type

        super().__init__(self._create_name(of_type_name))

        self.__of_type = of_type
        self.__of_type_resolved: t.Optional[GqlType] = None

    def of_type(self, type_registry: 'TypeRegistry') -> GqlType:
        if self.__of_type_resolved is None:
            self.__of_type_resolved = type_registry.resolve_type(self.__of_type)
        return self.__of_type_resolved

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        raise NotImplementedError()

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        raise NotImplementedError()

    def _create_name(self, of_type: str) -> str:
        raise NotImplementedError()


class List(_TypeWrapper):
    def _create_name(self, of_type: str) -> str:
        return "[" + of_type + ']'

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        if value is None:
            return True

        if not isinstance(value, list):
            return False

        wrapped_type = self.of_type(type_registry)

        for el in value:
            if not wrapped_type.is_assignable(el, type_registry):
                return False

        return True

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        if isinstance(value, qm.Variable):
            _validate_variable(value, self, vars_defs)

            if vars_values is None:
                return True

            p_value = vars_values.get(value.name)
            return self.is_assignable(p_value, type_registry)

        if isinstance(value, qm.NullValue):
            return True

        if not (isinstance(value, qm.ListValue) or isinstance(value, qm.ConstListValue)):
            return False

        of_type = self.of_type(type_registry)
        if not isinstance(of_type, _PossibleInputType):
            raise _SchemaAssertionError("Validating input for wrapper of non input type", "of_type")

        for i in value.values:
            if not of_type.validate_input(i, vars_values, vars_defs, type_registry):
                return False

        return True


class NonNull(_TypeWrapper):
    def _create_name(self, of_type: str) -> str:
        return of_type + '!'

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        if value is None:
            return False

        wrapped_type = self.of_type(type_registry)

        return wrapped_type.is_assignable(value, type_registry)

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        if isinstance(value, qm.Variable):
            _validate_variable(value, self, vars_defs)

            if vars_values is None:
                return True

            p_value = vars_values.get(value.name)
            return self.is_assignable(p_value, type_registry)
        if isinstance(value, qm.NullValue):
            return False
        of_type = self.of_type(type_registry)
        if not isinstance(of_type, _PossibleInputType):
            raise _SchemaAssertionError("Validating input for wrapper of non input type", "of_type")
        return of_type.validate_input(value, vars_values, vars_defs, type_registry)


class Argument:
    def __init__(self, argument_type: t.Union['InlineType', str], default: 'PrimitiveType') -> None:
        self.__type = argument_type
        self.default = default
        self.__type_resolved: t.Optional[t.Union[InputType, WrapperType]] = None

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        self_type = self.type(type_registry)
        return self_type.is_assignable(value, type_registry)

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        self_type = self.type(type_registry)
        return self_type.validate_input(value, vars_values, vars_defs, type_registry)

    def type(self, type_registry: 'TypeRegistry') -> t.Union['InputType', 'WrapperType']:
        if self.__type_resolved is None:
            self_type = type_registry.resolve_type(self.__type)
            self.__type_resolved = is_input(self_type)
            if self.__type_resolved is None:
                self.__type_resolved = assert_wrapper(self_type)
            assert_input(type_registry.resolve_and_unwrap(self.__type_resolved))
        return self.__type_resolved


class Field:
    def __init__(self, field_type: t.Union['InlineType', str], args: t.Mapping[str, Argument]) -> None:
        self.__type = field_type
        self.args = args
        self.__type_resolved: t.Optional[t.Union[OutputType, WrapperType]] = None

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        self_type = self.type(type_registry)
        return self_type.is_assignable(value, type_registry)

    def type(self, type_registry: 'TypeRegistry') -> t.Union['OutputType', 'WrapperType']:
        if self.__type_resolved is None:
            resolved_type = type_registry.resolve_type(self.__type)
            wrapper = is_wrapper(resolved_type)
            if wrapper is not None:
                self.__type_resolved = wrapper
            else:
                self.__type_resolved = assert_output(resolved_type)
        return self.__type_resolved


class _GqlCompositeType(GqlType):
    def __init__(self, name: str, fields: t.Mapping[str, Field]) -> None:
        super().__init__(name)
        self._fields = fields

    def fields(self, type_registry: 'TypeRegistry') -> t.Mapping[str, Field]:
        return self._fields

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        raise RuntimeError("Value must never be assigned to any composite type")


class _Scalar(_PossibleInputType):
    def __init__(self) -> None:
        super().__init__(type(self).__name__[1:])

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        raise NotImplementedError()

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        raise NotImplementedError()


class _Boolean(_Scalar):
    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        return value is None or isinstance(value, bool)

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        if isinstance(value, qm.Variable):
            _validate_variable(value, self, vars_defs)

            if vars_values is None:
                return True

            p_value = vars_values.get(value.name)
            return self.is_assignable(p_value, type_registry)
        return isinstance(value, qm.BoolValue) or isinstance(value, qm.NullValue)


class _Int(_Scalar):
    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        return value is None or isinstance(value, int)

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        if isinstance(value, qm.Variable):
            _validate_variable(value, self, vars_defs)

            if vars_values is None:
                return True

            p_value = vars_values.get(value.name)
            return self.is_assignable(p_value, type_registry)
        return isinstance(value, qm.IntValue) or isinstance(value, qm.NullValue)


class _Float(_Scalar):
    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        return value is None or isinstance(value, float)

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        if isinstance(value, qm.Variable):
            _validate_variable(value, self, vars_defs)

            if vars_values is None:
                return True

            p_value = vars_values.get(value.name)
            return self.is_assignable(p_value, type_registry)
        return isinstance(value, qm.FloatValue) or isinstance(value, qm.NullValue)


class _String(_Scalar):
    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        return value is None or isinstance(value, str)

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        if isinstance(value, qm.Variable):
            _validate_variable(value, self, vars_defs)

            if vars_values is None:
                return True

            p_value = vars_values.get(value.name)
            return self.is_assignable(p_value, type_registry)
        return isinstance(value, qm.StrValue) or isinstance(value, qm.NullValue)


class _ID(_Scalar):
    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        return value is None or isinstance(value, int) or isinstance(value, str)

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        if isinstance(value, qm.Variable):
            _validate_variable(value, self, vars_defs)

            if vars_values is None:
                return True

            p_value = vars_values.get(value.name)
            return self.is_assignable(p_value, type_registry)
        return isinstance(value, qm.IntValue) or isinstance(value, qm.StrValue) or isinstance(value, qm.NullValue)


Boolean = _Boolean()
Int = _Int()
Float = _Float()
String = _String()
ID = _ID()


class Enum(GqlType):
    def __init__(self, name: str, values: t.Set[str]) -> None:
        super().__init__(name)
        if len(values) < 2:
            raise GqlSchemaError("Enum must define at least 2 possible values")
        self.values = values

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        return value is None or isinstance(value, str) and value in self.values

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        if isinstance(value, qm.Variable):
            _validate_variable(value, self, vars_defs)

            if vars_values is None:
                return True

            p_value = vars_values.get(value.name)
            return self.is_assignable(p_value, type_registry)
        if isinstance(value, qm.NullValue):
            return True
        if not isinstance(value, qm.EnumValue):
            return False
        return value.value in self.values


class Interface(_GqlCompositeType):
    def of_objects(self, type_registry: 'TypeRegistry') -> t.Sequence['Object']:
        return type_registry.objects_by_interface(str(self))


class InputObject(_PossibleInputType):
    def __init__(self, name: str, fields: t.Mapping[str, t.Union['InlineType', str]]) -> None:
        super().__init__(name)

        if len(fields) == 0:
            raise GqlSchemaError("InputObject must define at least one field")

        self.__fields = fields
        self.__fields_resolved: t.Optional[t.Mapping[str, t.Union[InputType, WrapperType]]] = None

    def fields(self, type_registry: 'TypeRegistry') -> t.Mapping[str, t.Union['InputType', 'WrapperType']]:
        if self.__fields_resolved is None:
            fields_resolved: t.Dict[str, t.Union[InputType, WrapperType]] = {}
            for value_name, value_type in self.__fields.items():
                try:
                    value_type_resolved = type_registry.resolve_type(value_type)
                except TypeResolvingError as e:
                    raise _SchemaAssertionError(str(e), value_name) from e
                value_type_wrapper = is_wrapper(value_type_resolved)
                if value_type_wrapper is not None:
                    assert_input(type_registry.resolve_and_unwrap(value_type_wrapper))
                    fields_resolved[value_name] = value_type_wrapper
                else:
                    fields_resolved[value_name] = assert_input(value_type_resolved)
            self.__fields_resolved = fields_resolved
        return self.__fields_resolved

    def validate_input(self, value: t.Union[qm.Value, qm.ConstValue],
                       vars_values: t.Optional[t.Mapping[str, PrimitiveType]],
                       vars_defs: t.Mapping[str, GqlType],
                       type_registry: 'TypeRegistry') -> bool:
        if isinstance(value, qm.Variable):
            _validate_variable(value, self, vars_defs)

            if vars_values is None:
                return True

            p_value = vars_values.get(value.name)
            return self.is_assignable(p_value, type_registry)
        if isinstance(value, qm.NullValue):
            return True
        if isinstance(value, qm.ConstObjectValue) or isinstance(value, qm.ObjectValue):
            fields = self.fields(type_registry)

            value_keys = frozenset(value.values.keys())

            if len(value_keys.difference(fields)) > 0:
                return False

            for key, field_type in fields.items():
                field_value = value.values.get(key)
                if field_value is None:
                    field_value = qm.NullValue()
                if not field_type.validate_input(field_value, vars_values, vars_defs, type_registry):
                    return False
            return True
        return False

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        if value is None:
            return True

        if not isinstance(value, dict):
            return False

        value_keys = frozenset(value.keys())
        fields = self.fields(type_registry)

        if len(value_keys.difference(fields.keys())) > 0:
            return False

        for value_name, field_type in fields.items():
            if not field_type.is_assignable(value.get(value_name), type_registry):
                return False

        return True


class Object(_GqlCompositeType):
    def __init__(self, name: str, fields: t.Mapping[str, Field],
                 implements: t.Set[str]) -> None:
        super().__init__(name, fields)

        if len(fields) == 0 and len(implements) == 0:
            raise GqlSchemaError("Object must define at least one field or implement interface")

        self.__implements = implements
        self.__implements_resolved: t.Optional[t.Sequence[Interface]] = None

    def fields(self, type_registry: 'TypeRegistry') -> t.Mapping[str, Field]:
        fields: t.Dict[str, Field] = {}
        for i in self.implements(type_registry):
            for n, f in i.fields(type_registry).items():
                fields[n] = f
        for n, f in self._fields.items():
            fields[n] = f
        return fields

    def own_fields(self) -> t.Mapping[str, Field]:
        return self._fields

    def implements(self, type_registry: 'TypeRegistry') -> t.Sequence[Interface]:
        if self.__implements_resolved is None:
            self.__implements_resolved = []
            for interface_name in self.__implements:
                interface = type_registry.resolve_type(interface_name)
                if not isinstance(interface, Interface):
                    raise _SchemaAssertionError("Interface expected here", interface_name)
                self.__implements_resolved.append(interface)
        return self.__implements_resolved


class Union(GqlType):
    def __init__(self, name: str, of_objects: t.Set[str]) -> None:
        super().__init__(name)

        if len(of_objects) < 2:
            raise GqlSchemaError("Union must unite at least 2 objects")

        self.__of_objects = of_objects
        self.__of_objects_resolved: t.Optional[t.Sequence[Object]] = None

    def of_objects(self, type_registry: 'TypeRegistry') -> t.Sequence[Object]:
        if self.__of_objects_resolved is None:
            self.__of_objects_resolved = []
            for object_name in self.__of_objects:
                object_type = type_registry.resolve_type(object_name)
                if not isinstance(object_type, Object):
                    raise _SchemaAssertionError("Object expected here", object_name)
                self.__of_objects_resolved.append(object_type)
        return self.__of_objects_resolved

    def is_assignable(self, value: PrimitiveType, type_registry: 'TypeRegistry') -> bool:
        raise RuntimeError("Value must never be assigned to union")


ScalarType = t.Union[_Boolean, _Int, _Float, _String, _ID]


def is_scalar(type_to_test: GqlType) -> t.Optional[ScalarType]:
    if isinstance(type_to_test, _Boolean):
        return type_to_test
    if isinstance(type_to_test, _Int):
        return type_to_test
    if isinstance(type_to_test, _Float):
        return type_to_test
    if isinstance(type_to_test, _String):
        return type_to_test
    if isinstance(type_to_test, _ID):
        return type_to_test
    return None


def assert_scalar(type_to_test: GqlType) -> ScalarType:
    scalar = is_scalar(type_to_test)
    if scalar is None:
        raise _SchemaAssertionError("Scalar expected here", str(type_to_test))
    return scalar


WrapperType = t.Union[List, NonNull]


def is_wrapper(type_to_test: GqlType) -> t.Optional[WrapperType]:
    if isinstance(type_to_test, List):
        return type_to_test
    if isinstance(type_to_test, NonNull):
        return type_to_test
    return None


def assert_wrapper(type_to_test: GqlType) -> WrapperType:
    wrapper = is_wrapper(type_to_test)
    if wrapper is None:
        raise _SchemaAssertionError("Wrapper expected here", str(type_to_test))
    return wrapper


NonWrapperType = t.Union[ScalarType, Enum, Interface, Object, Union, InputObject]


def is_non_wrapper(type_to_test: GqlType) -> t.Optional[NonWrapperType]:
    if is_wrapper(type_to_test) is not None:
        return None
    return t.cast(NonWrapperType, type_to_test)


def assert_non_wrapper(type_to_test: GqlType) -> NonWrapperType:
    non_wrapper = is_non_wrapper(type_to_test)
    if non_wrapper is None:
        raise _SchemaAssertionError("Non wrapper expected here", str(type_to_test))
    return non_wrapper


SpreadableType = t.Union[Interface, Object, Union]


def is_spreadable(type_to_test: GqlType) -> t.Optional[SpreadableType]:
    if isinstance(type_to_test, Interface):
        return type_to_test
    if isinstance(type_to_test, Object):
        return type_to_test
    if isinstance(type_to_test, Union):
        return type_to_test
    return None


def assert_spreadable(type_to_test: GqlType) -> SpreadableType:
    spreadable = is_spreadable(type_to_test)
    if spreadable is None:
        raise _SchemaAssertionError("Spreadable expected here", str(type_to_test))
    return spreadable


SelectableType = t.Union[Interface, Object]


def is_selectable(type_to_test: GqlType) -> t.Optional[SelectableType]:
    if isinstance(type_to_test, Interface):
        return type_to_test
    if isinstance(type_to_test, Object):
        return type_to_test
    return None


def assert_selectable(type_to_test: GqlType) -> SelectableType:
    selectable = is_selectable(type_to_test)
    if selectable is None:
        raise _SchemaAssertionError("Selectable expected here", str(type_to_test))
    return selectable


InputType = t.Union[ScalarType, Enum, InputObject]


def is_input(type_to_test: GqlType) -> t.Optional[InputType]:
    if isinstance(type_to_test, _Boolean):
        return type_to_test
    if isinstance(type_to_test, _Int):
        return type_to_test
    if isinstance(type_to_test, _Float):
        return type_to_test
    if isinstance(type_to_test, _String):
        return type_to_test
    if isinstance(type_to_test, _ID):
        return type_to_test
    if isinstance(type_to_test, Enum):
        return type_to_test
    if isinstance(type_to_test, InputObject):
        return type_to_test
    return None


def assert_input(type_to_test: GqlType) -> InputType:
    input_type = is_input(type_to_test)
    if input_type is None:
        raise _SchemaAssertionError("Input type expected here", str(type_to_test))
    return input_type


OutputType = t.Union[ScalarType, Enum, Interface, Object, Union]


def is_output(type_to_test: GqlType) -> t.Optional[OutputType]:
    if isinstance(type_to_test, InputObject):
        return None
    if is_wrapper(type_to_test) is not None:
        return None
    return t.cast(OutputType, type_to_test)


def assert_output(type_to_test: GqlType) -> OutputType:
    output = is_output(type_to_test)
    if output is None:
        raise _SchemaAssertionError("Output type expected here", str(type_to_test))
    return output


UserType = t.Union[Enum, Interface, Object, Union, InputObject]


def is_user(type_to_test: GqlType) -> t.Optional[UserType]:
    if isinstance(type_to_test, Enum):
        return type_to_test
    if isinstance(type_to_test, Interface):
        return type_to_test
    if isinstance(type_to_test, Object):
        return type_to_test
    if isinstance(type_to_test, Union):
        return type_to_test
    if isinstance(type_to_test, InputObject):
        return type_to_test
    return None


def assert_user(type_to_test: GqlType) -> UserType:
    user = is_user(type_to_test)
    if user is None:
        raise _SchemaAssertionError("User defined type expected here", str(type_to_test))
    return user


InlineType = t.Union['ScalarType', 'WrapperType']


def is_inline(type_to_test: GqlType) -> t.Optional[t.Union['ScalarType', 'WrapperType']]:
    scalar = is_scalar(type_to_test)
    if scalar is not None:
        return scalar
    wrapper = is_wrapper(type_to_test)
    if wrapper is not None:
        return wrapper
    return None


def assert_inline(type_to_test: GqlType) -> t.Union['ScalarType', 'WrapperType']:
    inline = is_inline(type_to_test)
    if inline is None:
        raise _SchemaAssertionError("Inline type expected expected here", str(type_to_test))
    return inline


DirectiveLocation = t.NewType("DirectiveLocation", str)


class DirectiveLocations:
    QUERY = DirectiveLocation("QUERY")
    MUTATION = DirectiveLocation("MUTATION")
    FIELD = DirectiveLocation("FIELD")
    FRAGMENT_DEFINITION = DirectiveLocation("FRAGMENT_DEFINITION")
    FRAGMENT_SPREAD = DirectiveLocation("FRAGMENT_SPREAD")
    INLINE_FRAGMENT = DirectiveLocation("INLINE_FRAGMENT")


class Directive:
    def __init__(self, name: str, locations: t.Set[DirectiveLocation], args: t.Mapping[str, Argument]) -> None:
        self.__name = name
        self.locations = locations
        self.args = args

    def __str__(self) -> str:
        return "@" + self.__name


class TypeRegistry:
    def __init__(self, type_defs: t.Sequence[UserType], directives: t.Sequence[Directive]) -> None:
        for user_type in type_defs:
            if str(user_type) in {"Boolean", "Int", "Float", "String", "ID",
                                  "__Schema", "__Type", "__Field", "__InputValue", "__EnumValue", "__TypeKind",
                                  "__Directive", "__DirectiveLocation"}:
                raise GqlSchemaError("Can not redeclare standard type `{}`".format(str(user_type)))

        self.__types: t.List[GqlType] = list(type_defs)

        self.__types.extend((
            Boolean,
            Int,
            Float,
            String,
            ID,

            Object("__Schema", {
                "types": Field(NonNull(List(NonNull("__Type"))), {}),
                "queryType": Field(NonNull("__Type"), {}),
                "mutationType": Field("__Type", {}),
                "directives": Field(NonNull(List(NonNull("__Directive"))), {})
            }, set()),

            Object("__Type", {
                "kind": Field(NonNull("__TypeKind"), {}),
                "name": Field(String, {}),
                "description": Field(String, {}),
                "fields": Field(
                    List(NonNull("__Field")),
                    {"includeDeprecated": Argument(Boolean, False)}
                ),
                "interfaces": Field(List(NonNull("__Type")), {}),
                "possibleTypes": Field(List(NonNull("__Type")), {}),
                "enumValues": Field(
                    List(NonNull("__EnumValue")),
                    {"includeDeprecated": Argument(Boolean, False)}
                ),
                "inputFields": Field(List(NonNull("__InputValue")), {}),
                "ofType": Field("__Type", {})
            }, set()),

            Object("__Field", {
                "name": Field(NonNull(String), {}),
                "description": Field(String, {}),
                "args": Field(NonNull(List(NonNull("__InputValue"))), {}),
                "type": Field(NonNull("__Type"), {}),
                "isDeprecated": Field(NonNull(Boolean), {}),
                "deprecationReason": Field(String, {})
            }, set()),

            Object("__InputValue", {
                "name": Field(NonNull(String), {}),
                "description": Field(String, {}),
                "type": Field(NonNull("__Type"), {}),
                "defaultValue": Field(String, {})
            }, set()),

            Object("__EnumValue", {
                "name": Field(NonNull(String), {}),
                "description": Field(String, {}),
                "isDeprecated": Field(NonNull(Boolean), {}),
                "deprecationReason": Field(String, {})
            }, set()),

            Enum("__TypeKind", {
                "SCALAR",
                "OBJECT",
                "INTERFACE",
                "UNION",
                "ENUM",
                "INPUT_OBJECT",
                "LIST",
                "NON_NULL"
            }),

            Object("__Directive", {
                "name": Field(NonNull(String), {}),
                "description": Field(String, {}),
                "locations": Field(NonNull(List(NonNull("__DirectiveLocation"))), {}),
                "args": Field(NonNull(List(NonNull("__InputValue"))), {})
            }, set()),

            Enum("__DirectiveLocation", {
                "QUERY",
                "MUTATION",
                "FIELD",
                "FRAGMENT_DEFINITION",
                "FRAGMENT_SPREAD",
                "INLINE_FRAGMENT"
            })
        ))
        self.__types_by_names: t.Dict[str, GqlType] = {}

        for type_def in self.__types:
            if str(type_def) in self.__types_by_names:
                raise GqlSchemaError("Type re-definition; problem with `{}` type".format(str(type_def)))
            self.__types_by_names[str(type_def)] = type_def

        self.__directives = list(directives)

        self.__directives.append(Directive(
            "skip",
            {DirectiveLocations.INLINE_FRAGMENT, DirectiveLocations.FRAGMENT_SPREAD, DirectiveLocations.FIELD},
            {"if": Argument(Boolean, None)}
        ))
        self.__directives.append(Directive(
            "include",
            {DirectiveLocations.INLINE_FRAGMENT, DirectiveLocations.FRAGMENT_SPREAD, DirectiveLocations.FIELD},
            {"if": Argument(Boolean, None)}
        ))

        self.__directives_by_names = dict(((str(directive)[1:], directive) for directive in self.__directives))

        self.__validate()

        self.__objects_by_interfaces: t.Dict[str, t.List[Object]] = {}

        for gql_type in self.__types:
            if isinstance(gql_type, Object):
                for interface in gql_type.implements(self):
                    self.__objects_by_interfaces.setdefault(str(interface), [])
                    objects = self.__objects_by_interfaces[str(interface)]
                    objects.append(gql_type)
            if isinstance(gql_type, Interface):
                self.__objects_by_interfaces.setdefault(str(gql_type), [])

    def resolve_type(self, type_or_ref: t.Union[GqlType, str]) -> GqlType:
        if isinstance(type_or_ref, GqlType):
            return type_or_ref
        if type_or_ref not in self.__types_by_names:
            raise TypeResolvingError(type_or_ref)
        return self.__types_by_names[type_or_ref]

    def resolve_and_unwrap(self, type_or_ref: t.Union[GqlType, str]) -> NonWrapperType:
        gql_type = self.resolve_type(type_or_ref)

        wrapper = is_wrapper(gql_type)
        while wrapper is not None:
            gql_type = wrapper.of_type(self)
            wrapper = is_wrapper(gql_type)

        return assert_non_wrapper(gql_type)

    def objects_by_interface(self, interface_name: str) -> t.Sequence[Object]:
        return self.__objects_by_interfaces[interface_name]

    def directive(self, name: str) -> Directive:
        if name in self.__directives_by_names:
            return self.__directives_by_names[name]

        raise TypeResolvingError("Directive `{}` not found".format(name))

    __NAME_RE = re.compile(r'^[_A-Za-z][_0-9A-Za-z]*$')

    def __validate(self) -> None:
        for user_type in self.__types:
            if self.__NAME_RE.match(str(user_type)) is None:
                raise GqlSchemaError(
                    "Wrong type name: /{}/ expected, but got '{}'".format(self.__NAME_RE.pattern[1:-1], str(user_type)))

            if isinstance(user_type, Interface):
                self.__validate_fields(user_type)
            if isinstance(user_type, Object):
                self.__validate_object(user_type)
            if isinstance(user_type, Union):
                try:
                    user_type.of_objects(self)
                except TypeResolvingError as e:
                    raise GqlSchemaError(
                        "{}; problem with `{}` union".format(str(e), str(user_type))
                    ) from e
                except _SchemaAssertionError as e:
                    raise GqlSchemaError(
                        "Union must unite only objects; "
                        "problem with `{}` object of `{}` union".format(e.args[1], str(user_type))
                    ) from e
            if isinstance(user_type, InputObject):
                try:
                    declared_fields = user_type.fields(self)
                except _SchemaAssertionError as e:
                    raise GqlSchemaError(
                        "{}; problem with `{}` field of `{}` input object".format(str(e), e.args[1], str(user_type))
                    ) from e
                for field_name in declared_fields.keys():
                    if self.__NAME_RE.match(str(field_name)) is None:
                        raise GqlSchemaError(
                            "Wrong name of field: /{}/ expected, but got '{}' in `{}` type".format(
                                self.__NAME_RE.pattern[1:-1], field_name, str(user_type)
                            )
                        )
        for directive in self.__directives:
            if self.__NAME_RE.match(str(directive)[1:]) is None:
                raise GqlSchemaError(
                    "Wrong name of directive: /{}/ expected, but got '{}'".format(
                        self.__NAME_RE.pattern[1:-1], str(directive)[1:]
                    ))
            try:
                self.__validate_args(directive.args)
            except _SchemaAssertionError as e:
                raise GqlSchemaError(
                    "{}; problem with `{}` argument of `{}` directive".format(
                        str(e), e.args[1], str(directive)[1:]
                    )
                )

    def __validate_fields(self, selectable_type: SelectableType) -> None:
        for field_name, field in selectable_type.fields(self).items():
            if self.__NAME_RE.match(str(field_name)) is None:
                raise GqlSchemaError(
                    "Wrong name of field: /{}/ expected, but got '{}' in `{}` type".format(
                        self.__NAME_RE.pattern[1:-1], field_name, str(selectable_type)
                    )
                )

            try:
                field.type(self)
            except TypeResolvingError as e:
                raise GqlSchemaError(
                    "{}; problem with `{}` field of `{}` type".format(str(e), field_name, str(selectable_type))
                )
            except _SchemaAssertionError as e:
                raise GqlSchemaError(
                    "{}; problem with `{}` field of `{}` type".format(
                        str(e), field_name, str(selectable_type)
                    )
                ) from e
            try:
                self.__validate_args(field.args)
            except _SchemaAssertionError as e:
                raise GqlSchemaError(
                    "{}; problem with `{}` argument of `{}` field of `{}` type".format(
                        str(e), e.args[1], field_name, str(selectable_type)
                    )
                ) from e

    def __validate_args(self, args: t.Mapping[str, Argument]) -> None:
        for arg_name, arg in args.items():
            if self.__NAME_RE.match(str(arg_name)) is None:
                raise _SchemaAssertionError(
                    "Wrong name of argument: /{}/ expected, but got '{}'".format(
                        self.__NAME_RE.pattern[1:-1], arg_name
                    ), arg_name
                )

            try:
                arg_type = self.resolve_type(arg.type(self))
            except TypeResolvingError as e:
                raise _SchemaAssertionError(str(e), arg_name) from e
            except _SchemaAssertionError as e:
                raise _SchemaAssertionError("Input type expected", arg_name) from e
            if arg.default is not None and not arg_type.is_assignable(arg.default, self):
                raise _SchemaAssertionError("{} is not assignable to `{}` type".format(
                    json.dumps(arg.default), str(arg_type)
                ), arg_name)

    def __validate_object(self, obj: Object) -> None:
        try:
            interfaces = list(obj.implements(self))
        except TypeResolvingError as e:
            raise GqlSchemaError(
                "{}; problem with `{}` object".format(str(e), str(obj))
            ) from e
        except _SchemaAssertionError as e:
            raise GqlSchemaError(
                "Object must implement only interfaces; "
                "problem with `{}` interface of `{}` object".format(e.args[1], str(obj))
            ) from e
        declared_fields: t.Dict[str, str] = {}
        interfaces.sort(key=lambda i: str(i))
        for interface in interfaces:
            for field_name in interface.fields(self).keys():
                if field_name in declared_fields:
                    raise GqlSchemaError(
                        "Interfaces `{}` and `{}` of `{}` object both declare `{}` field".format(
                            declared_fields[field_name], str(interface), str(obj), field_name
                        )
                    )
                declared_fields[field_name] = str(interface)
        for field_name in obj.own_fields().keys():
            if field_name in declared_fields:
                raise GqlSchemaError(
                    "Object `{}` redeclare `{}` field of `{}` interface".format(
                        str(obj), field_name, declared_fields[field_name]
                    )
                )
        self.__validate_fields(obj)


def _validate_variable(var: qm.Variable, expected: GqlType, vars_defs: t.Mapping[str, GqlType]) -> None:
    if var.name not in vars_defs:
        raise UndefinedVariableError(var.name)

    var_def = vars_defs[var.name]
    if str(expected) != str(var_def):
        raise NonCompatibleVariableType(var.name, expected, var_def)


__all__ = ["TypeResolvingError", "GqlType", "List", "NonNull", "Argument", "Field", "Boolean", "Int", "Float",
           "String", "ID", "Enum", "Interface", "InputObject", "Object", "Union", "ScalarType", "is_scalar",
           "assert_scalar", "WrapperType", "is_wrapper", "assert_wrapper", "NonWrapperType", "is_non_wrapper",
           "assert_non_wrapper", "SpreadableType", "is_spreadable", "assert_spreadable", "SelectableType",
           "is_selectable", "assert_selectable", "InputType", "is_input", "assert_input", "OutputType",
           "is_output", "assert_output", "UserType", "is_user", "assert_user", "InlineType", "is_inline",
           "assert_inline", "DirectiveLocation", "DirectiveLocations", "Directive", "TypeRegistry"]
