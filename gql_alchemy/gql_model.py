from typing import List, MutableMapping, Mapping, Union, Optional

from .utils import add_if_not_empty, add_if_not_none, PrimitiveType, PrimitiveSerializable


class GraphQlModelType(PrimitiveSerializable):
    def to_primitive(self) -> MutableMapping[str, PrimitiveType]:
        return {
            "type": type(self).__name__
        }


class Document(GraphQlModelType):
    operations: List['Operation']
    fragments: List['Fragment']
    selections: List['Selection']

    def __init__(self,
                 selections: List['Selection'],
                 operations: List['Operation'],
                 fragments: List['Fragment']):
        self.selections = selections
        self.operations = operations
        self.fragments = fragments

    def to_primitive(self):
        p = super().to_primitive()
        add_if_not_empty(p, "operations", self.operations)
        add_if_not_empty(p, "fragments", self.fragments)
        add_if_not_empty(p, "selections", self.selections)
        return p


class Operation(GraphQlModelType):
    name: Optional[str]
    variables: List['VariableDefinition']
    directives: List['Directive']
    selections: List['Selection']

    def __init__(self,
                 variables: List['Argument'],
                 directives: List['Directive'],
                 selections: List['Selection']):
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
    default: PrimitiveType

    def __init__(self, name: str, var_type: 'Type', default: PrimitiveType):
        self.name = name
        self.type = var_type
        self.default = default

    def to_primitive(self):
        return [self.name, self.type.to_primitive(), self.default]


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
        return [self.name, self.null]


class ArrayType(Type):
    item_type: Type

    def __init__(self, item_type: Type, null: bool):
        super().__init__(null)
        self.item_type = item_type

    def to_primitive(self):
        return [self.item_type.to_primitive(), self.null]


class Directive(GraphQlModelType):
    name: str
    arguments: List['Argument']

    def __init__(self, name: str, arguments: List['Argument']):
        self.name = name
        self.arguments = arguments

    def to_primitive(self):
        d = super().to_primitive()
        d["name"] = self.name
        add_if_not_empty(d, "arguments", self.arguments)
        return d


Value = Union[
    PrimitiveType, 'Variable', List[Union[PrimitiveType, 'Variable']],
    Mapping[str, Union[PrimitiveType, 'Variable']]
]


class Argument(GraphQlModelType):
    name: str
    value: Value

    def __init__(self, name: str, value: Value):
        self.name = name
        self.value = value

    def to_primitive(self):
        value = self.value
        if isinstance(value, Variable):
            value = value.to_primitive()

        return [self.name, value]


class Variable(GraphQlModelType):
    name: str

    def __init__(self, name: str):
        self.name = name

    def to_primitive(self):
        return {
            "var": self.name
        }


class Fragment(GraphQlModelType):
    name: str
    on_type: NamedType
    directives: List[Directive]
    selections: List['Selection']

    def __init__(self, name: str, on_type: NamedType, directives: List[Directive], selections: List['Selection']):
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
    arguments: List[Argument]
    directives: List[Directive]
    selections: List[Selection]

    def __init__(self, alias: Optional[str],
                 name: str,
                 arguments: List[Argument],
                 directives: List[Directive],
                 selections: List[Selection]):
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
    directives: List[Directive]

    def __init__(self, fragment_name: str, directives: List[Directive]):
        self.fragment_name = fragment_name
        self.directives = directives

    def to_primitive(self):
        d = super().to_primitive()
        d["fragment_name"] = self.fragment_name
        add_if_not_empty(d, "directives", self.directives)
        return d


class InlineFragment(Selection):
    on_type: Optional[NamedType]
    directives: List[Directive]
    selections: List[Selection]

    def __init__(self,
                 on_type: Optional[NamedType],
                 directives: List[Directive],
                 selections: List[Selection]):
        self.on_type = on_type
        self.directives = directives
        self.selections = selections

    def to_primitive(self):
        d = super().to_primitive()
        add_if_not_none(d, "on_type", self.on_type)
        add_if_not_empty(d, "directives", self.directives)
        add_if_not_empty(d, "selections", self.selections)
        return d
