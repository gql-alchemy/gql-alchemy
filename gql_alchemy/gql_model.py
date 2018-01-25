from typing import Sequence, MutableMapping, Union, Optional, Mapping

from .utils import add_if_not_empty, add_if_not_none, PrimitiveType, PrimitiveSerializable


class GraphQlModelType(PrimitiveSerializable):
    def to_primitive(self) -> MutableMapping[str, PrimitiveType]:
        return {
            "type": type(self).__name__
        }


class Document(GraphQlModelType):
    operations: Sequence['Operation']
    fragments: Sequence['Fragment']

    def __init__(self, operations: Sequence['Operation'], fragments: Sequence['Fragment']):
        self.operations = operations
        self.fragments = fragments

    def to_primitive(self):
        p = super().to_primitive()
        add_if_not_empty(p, "operations", self.operations)
        add_if_not_empty(p, "fragments", self.fragments)
        return p


class Operation(GraphQlModelType):
    name: Optional[str]
    variables: Sequence['VariableDefinition']
    directives: Sequence['Directive']
    selections: Sequence['Selection']

    def __init__(self,
                 name,
                 variables: Sequence['VariableDefinition'],
                 directives: Sequence['Directive'],
                 selections: Sequence['Selection']):
        self.name = name
        self.variables = variables
        self.directives = directives
        self.selections = selections

    def to_primitive(self):
        p = super().to_primitive()
        add_if_not_none(p, "name", self.name)
        add_if_not_empty(p, "variables", self.variables)
        add_if_not_empty(p, "directives", self.directives)
        add_if_not_empty(p, "selections", self.selections)
        return p


class Query(Operation):
    pass


class Mutation(Operation):
    pass


class VariableDefinition(GraphQlModelType):
    name: str
    type: 'Type'
    default: 'ConstValue'

    def __init__(self, name: str, var_type: 'Type', default: 'ConstValue'):
        self.name = name
        self.type = var_type
        self.default = default

    def to_primitive(self):
        return [self.name, self.type.to_primitive(), None if self.default is None else self.default.to_primitive()]


class Type(GraphQlModelType):
    null: bool

    def __init__(self, null: bool):
        self.null = null


class NamedType(Type):
    name: str

    def __init__(self, name: str, null: bool):
        super().__init__(null)
        self.name = name

    def to_primitive(self):
        key = "@named"

        if not self.null:
            key += "!"

        return {key: self.name}


class ListType(Type):
    el_type: Type

    def __init__(self, el_type: Type, null: bool):
        super().__init__(null)
        self.el_type = el_type

    def to_primitive(self):
        key = "@list"

        if not self.null:
            key += "!"

        return {key: self.el_type.to_primitive()}


class Directive(GraphQlModelType):
    name: str
    arguments: Sequence['Argument']

    def __init__(self, name: str, arguments: Sequence['Argument']):
        self.name = name
        self.arguments = arguments

    def to_primitive(self):
        d = super().to_primitive()
        d["name"] = self.name
        add_if_not_empty(d, "arguments", self.arguments)
        return d


ConstValue = Union['IntValue', 'FloatValue', 'StrValue', 'BoolValue', 'NullValue', 'EnumValue', 'ConstListValue',
                   'ConstObjectValue']

Value = Union['Variable', 'IntValue', 'FloatValue', 'StrValue', 'BoolValue', 'NullValue', 'EnumValue', 'ListValue',
              'ObjectValue']


class Variable(GraphQlModelType):
    name: str

    def __init__(self, name: str):
        self.name = name

    def to_primitive(self):
        return {"@var": self.name}


class NullValue(GraphQlModelType):
    def to_primitive(self):
        return {"@null": None}


class EnumValue(GraphQlModelType):
    value: str

    def __init__(self, value: str):
        self.value = value

    def to_primitive(self):
        return {"@enum": self.value}


class IntValue(GraphQlModelType):
    value: int

    def __init__(self, value: int):
        self.value = value

    def to_primitive(self):
        return {"@int": self.value}


class FloatValue(GraphQlModelType):
    value: float

    def __init__(self, value: float):
        self.value = value

    def to_primitive(self):
        return {"@float": self.value}


class StrValue(GraphQlModelType):
    value: str

    def __init__(self, value: str):
        self.value = value

    def to_primitive(self):
        return {"@str": self.value}


class BoolValue(GraphQlModelType):
    value: bool

    def __init__(self, value: bool):
        self.value = value

    def to_primitive(self):
        return {"@bool": self.value}


class ConstListValue(GraphQlModelType):
    values: Sequence[ConstValue]

    def __init__(self, values: Sequence[ConstValue]):
        self.values = values

    def to_primitive(self):
        return {"@const-list": [v.to_primitive() for v in self.values]}


class ListValue(GraphQlModelType):
    values: Sequence[Value]

    def __init__(self, values: Sequence[Value]):
        self.values = values

    def to_primitive(self):
        return {"@list": [v.to_primitive() for v in self.values]}


class ConstObjectValue(GraphQlModelType):
    values: Mapping[str, ConstValue]

    def __init__(self, values: Mapping[str, ConstValue]):
        self.values = values

    def to_primitive(self):
        return {"@const-obj": dict(((k, v.to_primitive()) for k, v in self.values.items()))}


class ObjectValue(GraphQlModelType):
    values: Mapping[str, Value]

    def __init__(self, values: Mapping[str, Value]):
        self.values = values

    def to_primitive(self):
        return {"@obj": dict(((k, v.to_primitive()) for k, v in self.values.items()))}


class Argument(GraphQlModelType):
    name: str
    value: Value

    def __init__(self, name: str, value: Value):
        self.name = name
        self.value = value

    def to_primitive(self):
        return [self.name, self.value.to_primitive()]


class Fragment(GraphQlModelType):
    name: str
    on_type: NamedType
    directives: Sequence[Directive]
    selections: Sequence['Selection']

    def __init__(self, name: str, on_type: NamedType,
                 directives: Sequence[Directive], selections: Sequence['Selection']):
        self.name = name
        self.on_type = on_type
        self.directives = directives
        self.selections = selections

    def to_primitive(self):
        d = super().to_primitive()
        d["name"] = self.name
        d["on_type"] = self.on_type.to_primitive()
        add_if_not_empty(d, "directives", self.directives)
        add_if_not_empty(d, "selections", self.selections)
        return d


class Selection(GraphQlModelType):
    pass


class Field(Selection):
    alias: Optional[str]
    name: str
    arguments: Sequence[Argument]
    directives: Sequence[Directive]
    selections: Sequence[Selection]

    def __init__(self, alias: Optional[str],
                 name: str,
                 arguments: Sequence[Argument],
                 directives: Sequence[Directive],
                 selections: Sequence[Selection]):
        self.alias = alias
        self.name = name
        self.arguments = arguments
        self.directives = directives
        self.selections = selections

    def to_primitive(self):
        d = super().to_primitive()
        add_if_not_none(d, "alias", self.alias)
        d["name"] = self.name
        add_if_not_empty(d, "arguments", self.arguments)
        add_if_not_empty(d, "directives", self.directives)
        add_if_not_empty(d, "selections", self.selections)
        return d


class FragmentSpread(Selection):
    fragment_name: str
    directives: Sequence[Directive]

    def __init__(self, fragment_name: str, directives: Sequence[Directive]):
        self.fragment_name = fragment_name
        self.directives = directives

    def to_primitive(self):
        d = super().to_primitive()
        d["fragment_name"] = self.fragment_name
        add_if_not_empty(d, "directives", self.directives)
        return d


class InlineFragment(Selection):
    on_type: Optional[NamedType]
    directives: Sequence[Directive]
    selections: Sequence[Selection]

    def __init__(self,
                 on_type: Optional[NamedType],
                 directives: Sequence[Directive],
                 selections: Sequence[Selection]):
        self.on_type = on_type
        self.directives = directives
        self.selections = selections

    def to_primitive(self):
        d = super().to_primitive()
        add_if_not_none(d, "on_type", self.on_type)
        add_if_not_empty(d, "directives", self.directives)
        add_if_not_empty(d, "selections", self.selections)
        return d
