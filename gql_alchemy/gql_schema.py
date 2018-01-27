import json
import re
import typing as t

from .gql_errors import GqlSchemaError
from .utils import PrimitiveType

NAME_RE = re.compile(r'^[_A-Za-z][_0-9A-Za-z]*$')


class GqlType:
    """All schema types"""

    def __init__(self, description: t.Optional[str] = None) -> None:
        self.description = description
        self.name: t.Optional[str] = None

    def pretty_str(self) -> str:
        raise NotImplementedError()


class GqlUnwrappedType(GqlType):
    "Int, Float, Str, Bool, ID, Enum, Interface, Object, Union, InputObject"
    pass


class GqlWrappedType(GqlType):
    """NonNull, List"""
    of_type: t.Union['GqlWrappedType', 'GqlScalarType', 'Ref']

    def __init__(self, of_type: t.Union['GqlWrappedType', 'GqlScalarType', str],
                 description: t.Optional[str] = None) -> None:
        GqlType.__init__(self, description)
        if isinstance(of_type, str):
            self.of_type = Ref(of_type)
        else:
            self.of_type = of_type

    def unwrap(self) -> GqlUnwrappedType:
        type: t.Optional[t.Union[GqlType, Ref]] = self.of_type
        while isinstance(type, GqlWrappedType):
            type = type.of_type

        if isinstance(type, GqlUnwrappedType):
            return type

        if isinstance(type, Ref):
            type = type.ref_type

            if type is None:
                raise RuntimeError("unwrap called before ref resolution")

            if isinstance(type, GqlUnwrappedType):
                return type

            if isinstance(type, GqlWrappedType):
                return type.unwrap()

        raise RuntimeError("Error in unwrap method implementation")

    def pretty_str(self) -> str:
        if self.name is None:
            raise RuntimeError("Name is not filled in")

        return '\n'.join([
            format_description(0, self.description),
            self.name + ": " + self.pretty_short_str(),
            ""
        ])

    def pretty_short_str(self) -> str:
        raise NotImplementedError()


class GqlInputType(GqlUnwrappedType):
    "Int, Float, Str, Bool, ID, Enum, InputObject"
    pass


class GqlOutputType(GqlUnwrappedType):
    "Int, Float, Str, Bool, ID, Enum, Interface, Object, Union"
    pass


class GqlPlainType(GqlInputType, GqlOutputType):
    "Int, Float, Str, Bool, ID, Enum"
    pass


class GqlScalarType(GqlPlainType):
    """Int, Float, Str, Bool and ID"""

    def pretty_str(self) -> str:
        if self.name is None:
            raise RuntimeError("Name is not filled in")

        return '\n'.join([
            format_description(0, self.description),
            self.name + ": " + self.pretty_short_str(),
            ""
        ])

    def pretty_short_str(self) -> str:
        return type(self).__name__


class GqlSpreadableType(GqlOutputType):
    """Object, Interface and Union"""
    pass


class GqlSelectableType(GqlSpreadableType):
    """Object, Interface"""
    pass


class Ref:
    """Reference to other type"""

    def __init__(self, type_name: str) -> None:
        if NAME_RE.match(type_name) is None:
            raise GqlSchemaError("Wrong name in reference, /{}/ required, got {}".format(NAME_RE.pattern, type_name))
        self.type_name = type_name
        self.ref_type: t.Optional[t.Union[GqlUnwrappedType, GqlWrappedType]] = None

    def pretty_short_str(self) -> str:
        return self.type_name


def format_description(intent: int, description: t.Optional[str], is_deprecated: bool = False,
                       deprecation_reason: t.Optional[str] = None) -> str:
    lines = []
    if description is not None:
        for l in description.splitlines(keepends=False):
            lines.append(" " * intent + "# " + l)

    if is_deprecated:
        if description is not None:
            lines.append(" " * intent + "#")
        lines.append(" " * intent + "# Deprecated!")

    if deprecation_reason is not None:
        for l in deprecation_reason.splitlines(keepends=False):
            lines.append(" " * intent + "# " + l)

    return "\n".join(lines)


class Int(GqlScalarType):
    pass


class Float(GqlScalarType):
    pass


class String(GqlScalarType):
    pass


class Boolean(GqlScalarType):
    pass


class ID(GqlScalarType):
    pass


class EnumValue:
    def __init__(self, name: str, description: t.Optional[str] = None,
                 is_deprecated: bool = False, deprecation_reason: t.Optional[str] = None) -> None:
        self.name = name
        self.description = description
        self.is_deprecated = is_deprecated
        self.deprecation_reason = deprecation_reason


class Enum(GqlPlainType):
    def __init__(self, enum_values: t.Sequence[t.Union[EnumValue, str]], description: t.Optional[str] = None) -> None:
        GqlType.__init__(self, description)
        self.values = [EnumValue(i) if isinstance(i, str) else i for i in enum_values]
        self.__names = {v.name for v in self.values}

    def pretty_str(self) -> str:
        if self.name is None:
            raise RuntimeError("Name is not filled in")

        lines = []

        if self.description is not None:
            lines.append(format_description(0, self.description))

        lines.append("enum {} {{".format(self.name))

        for v in self.values:
            if v.description is not None or v.is_deprecated:
                lines.append(format_description(2, v.description, v.is_deprecated, v.deprecation_reason))
            lines.append("  " + v.name)

        lines.append("}")
        lines.append("")

        return "\n".join(lines)


class List(GqlWrappedType):
    def __init__(self, of_type: t.Union[GqlWrappedType, GqlScalarType, str],
                 description: t.Optional[str] = None) -> None:
        GqlWrappedType.__init__(self, of_type, description)

    def pretty_short_str(self) -> str:
        if isinstance(self.of_type, Ref):
            return "[" + self.of_type.type_name + "]"
        return "[" + self.of_type.pretty_short_str() + "]"


class NonNull(GqlWrappedType):
    def __init__(self, of_type: t.Union[List, GqlScalarType, str],
                 description: t.Optional[str] = None) -> None:
        GqlWrappedType.__init__(self, of_type, description)

    def pretty_short_str(self) -> str:
        if isinstance(self.of_type, Ref):
            return self.of_type.type_name + "!"
        return self.of_type.pretty_short_str() + "!"


class InputValue:
    type: t.Union[GqlScalarType, GqlWrappedType, Ref]

    def __init__(self, type: t.Union[GqlScalarType, GqlWrappedType, str],
                 default_value: PrimitiveType = None,
                 description: t.Optional[str] = None) -> None:
        if isinstance(type, str):
            self.type = Ref(type)
        else:
            self.type = type
        self.default_value = default_value
        self.description = description


def format_args_descriptions(args: t.Mapping[str, InputValue]) -> str:
    lines = []
    for n, a in args.items():
        if a.description is None:
            lines.append("  # " + n + ": undocumented")
        else:
            lines.append("  # " + n + ":")
            for l in a.description.splitlines(keepends=False):
                lines.append("  #   " + l)

    return "\n".join(lines)


def format_args(args: t.Optional[t.Mapping[str, InputValue]]) -> str:
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
        parts.append(a.type.pretty_short_str())
        if a.default_value is not None:
            parts.append(" = ")
            parts.append(json.dumps(a.default_value))

    parts.append(")")

    return "".join(parts)


class Field:
    type: t.Union[GqlScalarType, GqlWrappedType, Ref]
    args: t.Optional[t.Mapping[str, InputValue]] = None

    def __init__(self, type: t.Union[GqlScalarType, GqlWrappedType, str],
                 args: t.Optional[t.Mapping[str, t.Union[InputValue, GqlScalarType, GqlWrappedType, str]]] = None,
                 description: t.Optional[str] = None,
                 is_deprecated: bool = False,
                 deprecation_reason: t.Optional[str] = None) -> None:
        if isinstance(type, str):
            self.type = Ref(type)
        else:
            self.type = type

        norm_args: t.Optional[t.Dict[str, InputValue]] = None
        if args is not None:
            norm_args = {}

            for name, arg in args.items():
                if NAME_RE.match(name) is None:
                    raise GqlSchemaError("Wrong argument name, /{}/ required, was {}".format(NAME_RE.pattern, name))
                if isinstance(arg, InputValue):
                    norm_args[name] = arg
                else:
                    norm_args[name] = InputValue(arg)

        self.args = norm_args
        self.description = description
        self.is_deprecated = is_deprecated
        self.deprecation_reason = deprecation_reason

    def format(self, name: str) -> str:
        lines = []

        if self.description is not None or self.is_deprecated:
            lines.append(format_description(2, self.description, self.is_deprecated, self.deprecation_reason))

        if self.args is not None:
            if self.description is not None or self.is_deprecated:
                lines.append("  #")
            lines.append(format_args_descriptions(self.args))

        lines.append("  " + name + format_args(self.args) + ": " + self.type.pretty_short_str())

        return "\n".join(lines)


class Object(GqlSelectableType):
    def __init__(self, fields: t.Mapping[str, t.Union[Field, GqlScalarType, GqlWrappedType, str]],
                 interfaces: t.Sequence[str] = tuple(),
                 description: t.Optional[str] = None) -> None:
        super().__init__(description)

        norm_fields: t.Dict[str, Field] = {}

        for name, field in fields.items():
            if NAME_RE.match(name) is None:
                raise GqlSchemaError("Wrong field name, /{}/ required, was {}".format(NAME_RE.pattern, name))
            if isinstance(field, Field):
                norm_fields[name] = field
            else:
                norm_fields[name] = Field(field)

        self.fields: t.Mapping[str, Field] = norm_fields

        self.interfaces = [Ref(i) for i in interfaces]

    def pretty_str(self) -> str:
        if self.name is None:
            raise RuntimeError("Name not filled in")

        first_line = "type " + self.name

        if len(self.interfaces) > 0:
            first_line += " implements " + ", ".join((r.pretty_short_str() for r in self.interfaces))

        lines = []

        if self.description is not None:
            lines.append(format_description(0, self.description))

        lines.append(first_line)

        for n, f in self.fields.items():
            lines.append(f.format(n))

        lines.append("}")
        lines.append("")

        return "\n".join(lines)


class Interface(GqlSelectableType):
    def __init__(self, fields: t.Mapping[str, t.Union[Field, GqlScalarType, GqlWrappedType, str]],
                 description: t.Optional[str] = None) -> None:
        super().__init__(description)

        norm_fields: t.Dict[str, Field] = {}

        for name, field in fields.items():
            if NAME_RE.match(name) is None:
                raise GqlSchemaError("Wrong field name, /{}/ required, was {}".format(NAME_RE.pattern, name))
            if isinstance(field, Field):
                norm_fields[name] = field
            else:
                norm_fields[name] = Field(field)

        self.fields: t.Mapping[str, Field] = norm_fields

    def pretty_str(self) -> str:
        if self.name is None:
            raise RuntimeError("Name not filled in")

        first_line = "interface " + self.name + " {"

        lines = []

        if self.description is not None:
            lines.append(format_description(0, self.description))

        lines.append(first_line)

        for n, f in self.fields.items():
            lines.append(f.format(n))

        lines.append("}")
        lines.append("")

        return "\n".join(lines)


class Union(GqlSpreadableType):
    def __init__(self, possible_types: t.Sequence[str], description: t.Optional[str] = None) -> None:
        super().__init__(description)
        self.possible_types = [Ref(tp) for tp in possible_types]

    def pretty_str(self) -> str:
        if self.name is None:
            raise RuntimeError("Name not filled in")

        return "union " + self.name + " = " + " | ".join((r.pretty_short_str() for r in self.possible_types))


class InputObject(GqlInputType):
    def __init__(self, input_fields: t.Mapping[str, t.Union[InputValue, GqlScalarType, GqlWrappedType, str]],
                 description: t.Optional[str] = None) -> None:
        super().__init__(description)

        norm_infs: t.Dict[str, InputValue] = {}

        if len(input_fields) == 0:
            raise GqlSchemaError("Input object must have at least one field")

        for name, inf in input_fields.items():
            if NAME_RE.match(name) is None:
                raise GqlSchemaError("Wrong filed name, /{}/ required, was {}".format(NAME_RE.pattern, name))
            if isinstance(inf, InputValue):
                norm_infs[name] = inf
            else:
                norm_infs[name] = InputValue(inf)

        self.input_fields: t.Mapping[str, InputValue] = norm_infs

    def pretty_str(self) -> str:
        if self.name is None:
            raise RuntimeError("Name not filled in")

        lines = []

        if self.description is not None:
            lines.append(format_description(0, self.description))

        lines.append("input " + self.name + "{")

        for n, f in self.input_fields.items():
            if f.description is not None:
                format_description(2, f.description)

            f_str = "  " + n + ": " + f.type.pretty_short_str()
            if f.default_value != None:
                f_str += " = " + json.dumps(f.default_value)

            lines.append(f_str)

        lines.append("}")
        lines.append("")

        return "\n".join(lines)


DirectiveLocation = t.NewType("DirectiveLocation", str)


class DirectiveLocations:
    QUERY = DirectiveLocation("QUERY")
    MUTATION = DirectiveLocation("MUTATION")
    FIELD = DirectiveLocation("FIELD")
    FRAGMENT_DEFINITION = DirectiveLocation("FRAGMENT_DEFINITION")
    FRAGMENT_SPREAD = DirectiveLocation("FRAGMENT_SPREAD")
    INLINE_FRAGMENT = DirectiveLocation("INLINE_FRAGMENT")


class Directive:
    def __init__(self, locations: t.Set[DirectiveLocation],
                 args: t.Optional[t.Mapping[str, t.Union[InputValue, GqlScalarType, GqlWrappedType, str]]] = None,
                 description: t.Optional[str] = None) -> None:
        self.locations = locations

        norm_args: t.Dict[str, InputValue] = None
        if args is not None:
            norm_args = {}
            for name, arg in args:
                if NAME_RE.match(name) is None:
                    raise GqlSchemaError("Wrong argument name, /{}/ required, was {}".format(NAME_RE.pattern, name))
                if isinstance(arg, InputValue):
                    norm_args[name] = arg
                else:
                    norm_args[name] = InputValue(arg)

        self.args: t.Mapping[str, InputValue] = norm_args

        self.description = description

        self.name: t.Optional[str] = None

    def pretty_str(self):
        if self.name is None:
            raise RuntimeError("Name not filled in")

        parts = []

        if self.description is not None:
            parts.append(format_description(0, self.description))
            parts.append("\n")

        if self.args is not None:
            if self.description is not None:
                parts.append("\n#\n")
            parts.append(format_args_descriptions(self.args))
            parts.append("\n")

        parts.append("directive ")
        parts.append(self.name)
        parts.append(format_args(self.args))
        parts.append("\n")

        return "".join(parts)


class Schema:
    def __init__(self,
                 types: t.Mapping[str, t.Union[GqlWrappedType, Object, Interface, Union, InputObject]],
                 query: Object,
                 mutation: t.Optional[Object] = None,
                 directives: t.Optional[t.Mapping[str, Directive]] = None) -> None:

        for name, t in types.items():
            if NAME_RE.match(name) is None:
                raise GqlSchemaError("Wrong type name, /{}/ required, got {}".format(NAME_RE.pattern, name))
            t.name = name

        if directives is not None:
            for name, d in directives.items():
                if NAME_RE.match(name) is None:
                    raise GqlSchemaError("Wrong type name, /{}/ required, got {}".format(NAME_RE.pattern, name))
                d.name = name

        query.name = "@query"
        if mutation is not None:
            mutation.name = "@mutation"

        self.types = types
        self.query = query
        self.mutation = mutation
        self.directives = directives

        self.__resolve_all_refs()
        self.__verify_in_out_refs()

    def format(self) -> str:
        lines = []

        for t in self.types.values():
            lines.append(t.pretty_str())

        if self.directives is not None:
            for d in self.directives.values():
                lines.append(d.pretty_str())

        lines.append(self.query.pretty_str())
        if self.mutation is not None:
            lines.append(self.mutation.pretty_str())

        return "\n".join(lines)

    def __resolve_all_refs(self) -> None:
        for name, type in self.types.items():
            try:
                if isinstance(type, GqlWrappedType):
                    self.__resolve_ref(type)

                if isinstance(type, Object):
                    for ref in type.interfaces:
                        self.__resolve_ref(ref)
                        if not isinstance(ref.ref_type, Interface):
                            raise GqlSchemaError(
                                "Can extend interfaces only, {} is not interface".format(ref.type_name)
                            )

                if isinstance(type, Object) or isinstance(type, Interface):
                    for f in type.fields.values():
                        self.__resolve_ref(f.type)

                        if f.args is not None:
                            for a in f.args.values():
                                self.__resolve_ref(a.type)

                if isinstance(type, Union):
                    for ref in type.possible_types:
                        self.__resolve_ref(ref)
                        if not isinstance(ref.ref_type, Object):
                            raise GqlSchemaError(
                                "Union can be defined for objects only, {} is not object".format(ref.type_name)
                            )

                if isinstance(type, InputObject):
                    for inf in type.input_fields.values():
                        self.__resolve_ref(inf.type)
            except GqlSchemaError as e:
                raise GqlSchemaError("Error resolving ref for {} type".format(name)) from e

    def __resolve_ref(self, type: t.Union[GqlScalarType, GqlWrappedType, Ref]) -> None:
        if isinstance(type, Ref):
            if type.type_name not in self.types:
                raise GqlSchemaError("Reference to unknown type: " + type.type_name)

            type.ref_type = self.types[type.type_name]
        if isinstance(type, GqlWrappedType):
            type = type.of_type

            while isinstance(type, GqlWrappedType):
                type = type.of_type

            if isinstance(type, Ref):
                self.__resolve_ref(type)

    def __verify_in_out_refs(self) -> None:
        for name, type in self.types.items():
            if isinstance(type, Object) or isinstance(type, Interface):
                for f_name, f in type.fields.items():
                    f_type = self.__resolve_type(f.type)
                    if not isinstance(f_type, GqlOutputType):
                        raise GqlSchemaError("Field {}.{} of output type reference input type".format(name, f_name))

            if isinstance(type, InputObject):
                for f_name, inf in type.input_fields.items():
                    f_type = self.__resolve_type(inf.type)
                    if not isinstance(f_type, GqlInputType):
                        raise GqlSchemaError("Field {}.{} of input type reference output type".format(name, f_name))

    def __resolve_type(self, type: t.Union[GqlUnwrappedType, GqlWrappedType, Ref]) -> GqlUnwrappedType:
        if isinstance(type, GqlWrappedType):
            return type.unwrap()

        if isinstance(type, Ref):
            if type.ref_type is None:
                raise RuntimeError("This expected to run after refs resolving, but unresolved ref found")

            return self.__resolve_type(type.ref_type)

        return type
