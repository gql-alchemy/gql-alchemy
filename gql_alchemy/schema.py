import json
import typing as t
from itertools import chain

import gql_alchemy.types as gt
from .errors import GqlSchemaError
from .utils import PrimitiveType

Boolean = gt.Boolean
Int = gt.Int
Float = gt.Float
String = gt.String
ID = gt.ID


def NonNull(of_type: t.Union[gt.ScalarType, gt.List, str]) -> gt.NonNull:
    return gt.NonNull(of_type)


def List(of_type: t.Union[gt.InlineType, str]) -> gt.List:
    return gt.List(of_type)


class TypeDefinition:
    def __init__(self, name: str, description: t.Optional[str] = None) -> None:
        self.name = name
        self.description = description

    def to_type(self) -> gt.UserType:
        raise NotImplementedError()

    def to_pretty_str(self) -> str:
        raise NotImplementedError()


class EnumValue:
    def __init__(self, name: str, description: t.Optional[str] = None,
                 is_deprecated: bool = False, deprecation_reason: t.Optional[str] = None) -> None:
        self.name = name
        self.description = description
        self.is_deprecated = is_deprecated
        self.deprecation_reason = deprecation_reason


class Enum(TypeDefinition):
    def __init__(self, name: str, enum_values: t.Sequence[t.Union[EnumValue, str]],
                 description: t.Optional[str] = None) -> None:
        TypeDefinition.__init__(self, name, description)
        self.values: t.Sequence[EnumValue] = [EnumValue(i) if isinstance(i, str) else i for i in enum_values]
        self.__names = {v.name for v in self.values}

    def to_type(self) -> gt.UserType:
        return gt.Enum(self.name, {v.name for v in self.values})

    def to_pretty_str(self) -> str:
        if self.name is None:
            raise RuntimeError("Name is not filled in")

        lines: t.List[str] = []

        _format_description(lines, 0, self.description)

        lines.append("enum {} {{".format(self.name))

        for v in self.values:
            _format_description(lines, 2, v.description, v.is_deprecated, v.deprecation_reason)
            lines.append("  " + v.name)

        lines.append("}")

        return "\n".join(lines)


class InputValue:
    def __init__(self, type: t.Union[gt.InlineType, str],
                 default_value: PrimitiveType = None,
                 description: t.Optional[str] = None) -> None:
        self.type = type
        self.default_value = default_value
        self.description = description

    def to_type_arg(self) -> gt.Argument:
        return gt.Argument(self.type, self.default_value)


class Field:
    def __init__(self, type: t.Union[gt.InlineType, str],
                 args: t.Mapping[str, t.Union[InputValue, gt.InlineType, str]] = {},
                 description: t.Optional[str] = None,
                 is_deprecated: bool = False,
                 deprecation_reason: t.Optional[str] = None) -> None:
        self.type = type

        norm_args: t.Dict[str, InputValue] = {}
        for name, arg in args.items():
            if isinstance(arg, InputValue):
                norm_args[name] = arg
            else:
                norm_args[name] = InputValue(arg)

        self.args: t.Mapping[str, InputValue] = norm_args
        self.description = description
        self.is_deprecated = is_deprecated
        self.deprecation_reason = deprecation_reason

    def to_type_field(self) -> gt.Field:
        return gt.Field(self.type, dict(((arg_name, arg.to_type_arg()) for arg_name, arg in self.args.items())))

    def format(self, name: str) -> str:
        lines: t.List[str] = []

        if self.description is not None or self.is_deprecated:
            _format_description(lines, 2, self.description, self.is_deprecated, self.deprecation_reason)

        if self.args is not None:
            if self.description is not None or self.is_deprecated:
                lines.append("  #")
            _format_args_descriptions(lines, self.args)

        lines.append("  " + name + _format_args(self.args) + ": " + str(self.type))

        return "\n".join(lines)


class _SelectableTypeDefinition(TypeDefinition):
    """Object, Interface"""

    def __init__(self, name: str,
                 fields: t.Mapping[str, t.Union[Field, gt.InlineType, str]],
                 description: t.Optional[str]) -> None:
        super().__init__(name, description)

        norm_fields: t.Dict[str, Field] = {}

        for name, field in fields.items():
            if isinstance(field, Field):
                norm_fields[name] = field
            else:
                norm_fields[name] = Field(field)

        self.fields: t.Mapping[str, Field] = norm_fields

    def to_type(self) -> gt.UserType:
        raise NotImplementedError()

    def to_pretty_str(self) -> str:
        lines: t.List[str] = []

        if self.description is not None:
            _format_description(lines, 0, self.description)

        lines.append(self._format_first_line())

        for n, f in self.fields.items():
            lines.append(f.format(n))

        lines.append("}")
        lines.append("")

        return "\n".join(lines)

    def _format_first_line(self) -> str:
        raise NotImplementedError()


class Object(_SelectableTypeDefinition):
    def __init__(self, name: str, fields: t.Mapping[str, t.Union[Field, gt.InlineType, str]],
                 interfaces: t.Set[str] = set(),
                 description: t.Optional[str] = None) -> None:
        super().__init__(name, fields, description)

        self.interfaces = interfaces

    def to_type(self) -> gt.Object:
        return gt.Object(self.name,
                         dict(((field_name, field.to_type_field()) for field_name, field in self.fields.items())),
                         self.interfaces)

    def _format_first_line(self) -> str:
        first_line = "type " + self.name

        if len(self.interfaces) > 0:
            first_line += " implements " + ", ".join(self.interfaces) + " {"

        return first_line


class Interface(_SelectableTypeDefinition):
    def __init__(self, name: str, fields: t.Mapping[str, t.Union[Field, gt.InlineType, str]],
                 description: t.Optional[str] = None) -> None:
        super().__init__(name, fields, description)

    def to_type(self) -> gt.UserType:
        return gt.Interface(self.name,
                            dict(((field_name, field.to_type_field()) for field_name, field in self.fields.items())))

    def _format_first_line(self) -> str:
        return "interface " + self.name + " {"


class Union(TypeDefinition):
    def __init__(self, name: str, possible_types: t.Set[str], description: t.Optional[str] = None) -> None:
        super().__init__(name, description)
        self.possible_types = possible_types

    def to_type(self) -> gt.UserType:
        return gt.Union(self.name, self.possible_types)

    def to_pretty_str(self) -> str:
        return "union " + self.name + " = " + " | ".join(self.possible_types)


class IoField:
    def __init__(self, type: t.Union[gt.InlineType, str], description: t.Optional[str] = None) -> None:
        self.type = type
        self.description = description


class InputObject(TypeDefinition):
    def __init__(self, name: str, input_fields: t.Mapping[str, t.Union[IoField, gt.InlineType, str]],
                 description: t.Optional[str] = None) -> None:
        super().__init__(name, description)

        norm_infs: t.Dict[str, IoField] = {}

        if len(input_fields) == 0:
            raise GqlSchemaError("Input object must have at least one field")

        for name, inf in input_fields.items():
            if isinstance(inf, IoField):
                norm_infs[name] = inf
            else:
                norm_infs[name] = IoField(inf)

        self.input_fields: t.Mapping[str, IoField] = norm_infs

    def to_type(self) -> gt.InputObject:
        return gt.InputObject(
            self.name,
            dict(((field_name, field.type) for field_name, field in self.input_fields.items()))
        )

    def to_pretty_str(self) -> str:
        lines: t.List[str] = []

        if self.description is not None:
            _format_description(lines, 0, self.description)

        lines.append("input " + self.name + "{")

        for n, f in self.input_fields.items():
            if f.description is not None:
                _format_description(lines, 2, f.description)

            f_str = "  " + n + ": " + str(f.type)

            lines.append(f_str)

        lines.append("}")
        lines.append("")

        return "\n".join(lines)


DirectiveLocations = gt.DirectiveLocations


class Directive:
    def __init__(self, name: str, locations: t.Set[gt.DirectiveLocation],
                 args: t.Optional[t.Mapping[str, t.Union[InputValue, gt.InlineType, str]]] = None,
                 description: t.Optional[str] = None) -> None:
        self.name = name
        self.locations = locations

        norm_args: t.Dict[str, InputValue] = {}
        if args is not None:
            for name, arg in args:
                if isinstance(arg, InputValue):
                    norm_args[name] = arg
                else:
                    norm_args[name] = InputValue(arg)

        self.args: t.Mapping[str, InputValue] = norm_args

        self.description = description

    def to_directive(self) -> gt.Directive:
        return gt.Directive(self.name, self.locations,
                            dict(((arg_name, arg.to_type_arg()) for arg_name, arg in self.args.items())))

    def to_pretty_str(self) -> str:
        lines: t.List[str] = []

        if self.description is not None:
            _format_description(lines, 0, self.description)

        if self.args is not None:
            if self.description is not None:
                lines.append("#")
            _format_args_descriptions(lines, self.args)

        lines.append("directive " + self.name + _format_args(self.args))
        lines.append("")

        return "\n".join(lines)


class Schema:
    def __init__(self,
                 types: t.Sequence[t.Union[Enum, Object, Interface, Union, InputObject]],
                 query: Object,
                 mutation: t.Optional[Object] = None,
                 directives: t.Optional[t.Sequence[Directive]] = None) -> None:

        self.types = list(types)
        self.query_object_name = query.name

        self.mutation_object_name: t.Optional[str] = None
        if mutation is not None:
            self.types.append(mutation)
            self.mutation_object_name = mutation.name

        self.directives: t.Sequence[Directive] = directives or []
        self.type_registry = gt.TypeRegistry(
            list(chain(
                (type_def.to_type() for type_def in self.types),
                [_IntrospectionQueryObject(query.to_type())]
            )),
            [dir_def.to_directive() for dir_def in self.directives]
        )

        self.types.append(query)

    def format(self) -> str:
        lines: t.List[str] = []

        for type_def in self.types:
            lines.append(type_def.to_pretty_str())

        if self.directives is not None:
            for d in self.directives:
                lines.append(d.to_pretty_str())

        return "\n".join(lines)


def _format_description(lines: t.List[str],
                        indent: int,
                        description: t.Optional[str],
                        is_deprecated: bool = False,
                        deprecation_reason: t.Optional[str] = None) -> None:
    if description is not None:
        for l in description.splitlines(keepends=False):
            lines.append(" " * indent + "# " + l)

    if is_deprecated:
        if description is not None:
            lines.append(" " * indent + "#")
        lines.append(" " * indent + "# Deprecated!")

    if deprecation_reason is not None:
        for l in deprecation_reason.splitlines(keepends=False):
            lines.append(" " * indent + "# " + l)


def _format_args_descriptions(lines: t.List[str], args: t.Mapping[str, InputValue]) -> None:
    for n, a in args.items():
        if a.description is None:
            lines.append("  # " + n + ": undocumented")
        else:
            lines.append("  # " + n + ":")
            for l in a.description.splitlines(keepends=False):
                lines.append("  #   " + l)


def _format_args(args: t.Optional[t.Mapping[str, InputValue]]) -> str:
    if args is None:
        return ""

    parts = ["("]

    first = True

    for n, a in args.items():

        if not first:
            parts.append(", ")
        first = False

        parts.append(n)
        parts.append(": ")
        parts.append(str(a.type))
        if a.default_value is not None:
            parts.append(" = ")
            parts.append(json.dumps(a.default_value))

    parts.append(")")

    return "".join(parts)


class _IntrospectionQueryObject(gt.Object):
    def __init__(self, query_obj: gt.Object) -> None:
        super().__init__(str(query_obj), {
            "__schema": gt.Field(gt.NonNull("__Schema"), {}),
            "__type": gt.Field("__Type", {"name": gt.Argument(gt.NonNull(gt.String), None)})
        }, set())

        self.__query_obj = query_obj

    def fields(self, type_registry: gt.TypeRegistry) -> t.Mapping[str, gt.Field]:
        return dict(
            chain(
                self.__query_obj.fields(type_registry).items(),
                super().fields(type_registry).items()
            )
        )

    def own_fields(self) -> t.Mapping[str, gt.Field]:
        return dict(
            chain(
                self.__query_obj.own_fields().items(),
                super().own_fields().items()
            )
        )

    def implements(self, type_registry: gt.TypeRegistry) -> t.Sequence[gt.Interface]:
        return self.__query_obj.implements(type_registry)


__all__ = ["Boolean", "Int", "Float", "String", "ID", "NonNull", "List", "EnumValue", "Enum", "InputValue",
           "Field", "Object", "Interface", "Union", "IoField", "InputObject", "DirectiveLocations", "Directive",
           "Schema"]
