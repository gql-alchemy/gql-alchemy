from typing import Sequence, Union, Optional, Mapping, Dict, Tuple

from .utils import add_if_not_empty, add_if_not_none, PrimitiveType, PrimitiveSerializable


class QueryVisitor:
    def visit_document_begin(self, document: 'Document') -> None:
        pass

    def visit_document_end(self, document: 'Document') -> None:
        pass

    def visit_query_begin(self, query: 'Query') -> None:
        pass

    def visit_query_end(self, query: 'Query') -> None:
        pass

    def visit_mutation_begin(self, mutation: 'Mutation') -> None:
        pass

    def visit_mutation_end(self, mutation: 'Mutation') -> None:
        pass

    def visit_variable_definition(self, var_def: 'VariableDefinition') -> None:
        pass

    def visit_directive_begin(self, directive: 'Directive') -> None:
        pass

    def visit_directive_end(self, directive: 'Directive') -> None:
        pass

    def visit_argument(self, argument: 'Argument') -> None:
        pass

    def visit_fragment_begin(self, fragment: 'NamedFragment') -> None:
        pass

    def visit_fragment_end(self, fragment: 'NamedFragment') -> None:
        pass

    def visit_field_selection_begin(self, field_sel: 'FieldSelection') -> None:
        pass

    def visit_field_selection_end(self, field_sel: 'FieldSelection') -> None:
        pass

    def visit_fragment_spread_begin(self, spread: 'FragmentSpread') -> None:
        pass

    def visit_fragment_spread_end(self, spread: 'FragmentSpread') -> None:
        pass

    def visit_inline_fragment_begin(self, fragment: 'InlineFragment') -> None:
        pass

    def visit_inline_fragment_end(self, fragment: 'InlineFragment') -> None:
        pass

    def visit_variable(self, var: 'Variable') -> None:
        pass

    def visit_null_value(self, val: 'NullValue') -> None:
        pass

    def visit_bool_value(self, val: 'BoolValue') -> None:
        pass

    def visit_int_value(self, val: 'IntValue') -> None:
        pass

    def visit_float_value(self, val: 'FloatValue') -> None:
        pass

    def visit_str_value(self, val: 'StrValue') -> None:
        pass

    def visit_enum_value(self, val: 'EnumValue') -> None:
        pass

    def visit_list_value_begin(self, val: Union['ListValue', 'ConstListValue']) -> None:
        pass

    def visit_list_value_end(self, val: Union['ListValue', 'ConstListValue']) -> None:
        pass

    def visit_object_value_begin(self, val: Union['ObjectValue', 'ConstObjectValue']) -> None:
        pass

    def visit_object_field(self, val: Tuple[str, Union['Value', 'ConstValue']]) -> None:
        pass

    def visit_object_value_end(self, val: Union['ObjectValue', 'ConstObjectValue']) -> None:
        pass


class GraphQlModelType(PrimitiveSerializable):
    def visit(self, visitor: QueryVisitor) -> None:
        raise NotImplementedError()

    def to_primitive(self) -> PrimitiveType:
        raise NotImplementedError()


class Document(GraphQlModelType):
    operations: Sequence['Operation']
    fragments: Sequence['NamedFragment']

    def __init__(self, operations: Sequence['Operation'], fragments: Sequence['NamedFragment']) -> None:
        self.operations = operations
        self.fragments = fragments

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_document_begin(self)

        for op in self.operations:
            op.visit(visitor)

        for fr in self.fragments:
            fr.visit(visitor)

        visitor.visit_document_end(self)

    def to_primitive(self) -> PrimitiveType:
        p: Dict[str, PrimitiveType] = {"@doc": None}
        add_if_not_empty(p, "operations", self.operations)
        add_if_not_empty(p, "fragments", self.fragments)
        return p


class Operation(GraphQlModelType):
    name: Optional[str]
    variables: Sequence['VariableDefinition']
    directives: Sequence['Directive']
    selections: Sequence['Selection']

    def __init__(self,
                 name: Optional[str],
                 variables: Sequence['VariableDefinition'],
                 directives: Sequence['Directive'],
                 selections: Sequence['Selection']) -> None:
        self.name = name
        self.variables = variables
        self.directives = directives
        self.selections = selections

    def to_primitive(self) -> PrimitiveType:
        p: Dict[str, PrimitiveType] = {"@m": self.name}

        if type(self).__name__ == "Query":
            p = {"@q": self.name}

        add_if_not_empty(p, "variables", self.variables)
        add_if_not_empty(p, "directives", self.directives)
        add_if_not_empty(p, "selections", self.selections)
        return p

    def visit(self, visitor: QueryVisitor) -> None:
        raise NotImplementedError()

    def _visit_internal(self, visitor: QueryVisitor) -> None:
        for v_def in self.variables:
            v_def.visit(visitor)

        for directive in self.directives:
            directive.visit(visitor)

        for sel in self.selections:
            sel.visit(visitor)


class Query(Operation):
    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_query_begin(self)

        self._visit_internal(visitor)

        visitor.visit_query_end(self)


class Mutation(Operation):
    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_mutation_begin(self)

        self._visit_internal(visitor)

        visitor.visit_mutation_end(self)


class VariableDefinition(GraphQlModelType):
    name: str
    type: 'Type'
    default: Optional['ConstValue']

    def __init__(self, name: str, var_type: 'Type', default: Optional['ConstValue']) -> None:
        self.name = name
        self.type = var_type
        self.default = default

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_variable_definition(self)

    def to_primitive(self) -> PrimitiveType:
        return [self.name, self.type.to_primitive(), None if self.default is None else self.default.to_primitive()]


class Type(GraphQlModelType):
    null: bool

    def __init__(self, null: bool) -> None:
        self.null = null

    def visit(self, visitor: QueryVisitor) -> None:
        raise RuntimeError("Type is not suppose to be visited")

    def to_primitive(self) -> PrimitiveType:
        raise NotImplementedError()


class NamedType(Type):
    name: str

    def __init__(self, name: str, null: bool) -> None:
        super().__init__(null)
        self.name = name

    def to_primitive(self) -> PrimitiveType:
        key = "@named"

        if not self.null:
            key += "!"

        return {key: self.name}


class ListType(Type):
    el_type: Type

    def __init__(self, el_type: Type, null: bool) -> None:
        super().__init__(null)
        self.el_type = el_type

    def to_primitive(self) -> PrimitiveType:
        key = "@list"

        if not self.null:
            key += "!"

        return {key: self.el_type.to_primitive()}


class Directive(GraphQlModelType):
    name: str
    arguments: Sequence['Argument']

    def __init__(self, name: str, arguments: Sequence['Argument']) -> None:
        self.name = name
        self.arguments = arguments

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_directive_begin(self)

        for arg in self.arguments:
            arg.visit(visitor)

        visitor.visit_directive_end(self)

    def to_primitive(self) -> PrimitiveType:
        d: Dict[str, PrimitiveType] = {"@dir": self.name}
        add_if_not_empty(d, "arguments", self.arguments)
        return d


ConstValue = Union['IntValue', 'FloatValue', 'StrValue', 'BoolValue', 'NullValue', 'EnumValue', 'ConstListValue',
                   'ConstObjectValue']

Value = Union['Variable', 'IntValue', 'FloatValue', 'StrValue', 'BoolValue', 'NullValue', 'EnumValue', 'ListValue',
              'ObjectValue']


class ValueModelType(GraphQlModelType):
    def visit(self, visitor: QueryVisitor) -> None:
        raise NotImplementedError()

    def to_primitive(self) -> PrimitiveType:
        raise NotImplementedError()

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        raise NotImplementedError()


class Variable(ValueModelType):
    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_variable(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@var": self.name}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return variables.get(self.name)


class NullValue(ValueModelType):
    def to_primitive(self) -> PrimitiveType:
        return {"@null": None}

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_null_value(self)

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return None


class EnumValue(ValueModelType):
    value: str

    def __init__(self, value: str) -> None:
        self.value = value

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_enum_value(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@enum": self.value}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return self.value


class IntValue(ValueModelType):
    value: int

    def __init__(self, value: int) -> None:
        self.value = value

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_int_value(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@int": self.value}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return self.value


class FloatValue(ValueModelType):
    value: float

    def __init__(self, value: float) -> None:
        self.value = value

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_float_value(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@float": self.value}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return self.value


class StrValue(ValueModelType):
    value: str

    def __init__(self, value: str) -> None:
        self.value = value

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_str_value(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@str": self.value}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return self.value


class BoolValue(ValueModelType):
    value: bool

    def __init__(self, value: bool) -> None:
        self.value = value

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_bool_value(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@bool": self.value}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return self.value


class ConstListValue(ValueModelType):
    values: Sequence[ConstValue]

    def __init__(self, values: Sequence[ConstValue]) -> None:
        self.values = values

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_list_value_begin(self)

        for val in self.values:
            val.visit(visitor)

        visitor.visit_list_value_end(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@const-list": [v.to_primitive() for v in self.values]}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return [value.to_py_value(variables) for value in self.values]


class ListValue(ValueModelType):
    values: Sequence[Value]

    def __init__(self, values: Sequence[Value]) -> None:
        self.values = values

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_list_value_begin(self)

        for val in self.values:
            val.visit(visitor)

        visitor.visit_list_value_end(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@list": [v.to_primitive() for v in self.values]}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return [value.to_py_value(variables) for value in self.values]


class ConstObjectValue(ValueModelType):
    values: Mapping[str, ConstValue]

    def __init__(self, values: Mapping[str, ConstValue]) -> None:
        self.values = values

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_object_value_begin(self)

        for field in self.values.items():
            visitor.visit_object_field(field)
            field[1].visit(visitor)

        visitor.visit_object_value_end(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@const-obj": dict(((k, v.to_primitive()) for k, v in self.values.items()))}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return dict(((name, value.to_py_value(variables)) for name, value in self.values.items()))


class ObjectValue(ValueModelType):
    values: Mapping[str, Value]

    def __init__(self, values: Mapping[str, Value]) -> None:
        self.values = values

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_object_value_begin(self)

        for field in self.values.items():
            visitor.visit_object_field(field)
            field[1].visit(visitor)

        visitor.visit_object_value_end(self)

    def to_primitive(self) -> PrimitiveType:
        return {"@obj": dict(((k, v.to_primitive()) for k, v in self.values.items()))}

    def to_py_value(self, variables: Mapping[str, PrimitiveType]) -> PrimitiveType:
        return dict(((name, value.to_py_value(variables)) for name, value in self.values.items()))


class Argument(GraphQlModelType):
    name: str
    value: Value

    def __init__(self, name: str, value: Value) -> None:
        self.name = name
        self.value = value

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_argument(self)
        self.value.visit(visitor)

    def to_primitive(self) -> PrimitiveType:
        return [self.name, self.value.to_primitive()]


class Fragment(GraphQlModelType):
    on_type: Optional[NamedType]
    directives: Sequence[Directive]
    selections: Sequence['Selection']

    def visit(self, visitor: QueryVisitor) -> None:
        raise NotImplementedError()

    def to_primitive(self) -> PrimitiveType:
        raise NotImplementedError()


class NamedFragment(Fragment):
    name: str
    on_type: NamedType
    directives: Sequence[Directive]
    selections: Sequence['Selection']

    def __init__(self, name: str, on_type: NamedType,
                 directives: Sequence[Directive], selections: Sequence['Selection']) -> None:
        self.name = name
        self.on_type = on_type
        self.directives = directives
        self.selections = selections

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_fragment_begin(self)

        for directive in self.directives:
            directive.visit(visitor)

        for sel in self.selections:
            sel.visit(visitor)

        visitor.visit_fragment_end(self)

    def to_primitive(self) -> PrimitiveType:
        d = {"@frg": self.name, "on_type": self.on_type.to_primitive()}

        add_if_not_empty(d, "directives", self.directives)
        add_if_not_empty(d, "selections", self.selections)
        return d


class Selection(GraphQlModelType):
    def visit(self, visitor: QueryVisitor) -> None:
        raise NotImplementedError()

    def to_primitive(self) -> PrimitiveType:
        raise NotImplementedError()


class FieldSelection(Selection):
    alias: Optional[str]
    name: str
    arguments: Sequence[Argument]
    directives: Sequence[Directive]
    selections: Sequence[Selection]

    def __init__(self, alias: Optional[str],
                 name: str,
                 arguments: Sequence[Argument],
                 directives: Sequence[Directive],
                 selections: Sequence[Selection]) -> None:
        self.alias = alias
        self.name = name
        self.arguments = arguments
        self.directives = directives
        self.selections = selections

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_field_selection_begin(self)

        for arg in self.arguments:
            arg.visit(visitor)

        for directive in self.directives:
            directive.visit(visitor)

        for sel in self.selections:
            sel.visit(visitor)

        visitor.visit_field_selection_end(self)

    def to_primitive(self) -> PrimitiveType:
        d: Dict[str, PrimitiveType] = {"@f": self.name}

        add_if_not_none(d, "alias", self.alias)
        add_if_not_empty(d, "arguments", self.arguments)
        add_if_not_empty(d, "directives", self.directives)
        add_if_not_empty(d, "selections", self.selections)
        return d


class FragmentSpread(Selection):
    fragment_name: str
    directives: Sequence[Directive]

    def __init__(self, fragment_name: str, directives: Sequence[Directive]) -> None:
        self.fragment_name = fragment_name
        self.directives = directives

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_fragment_spread_begin(self)

        for directive in self.directives:
            directive.visit(visitor)

        visitor.visit_fragment_spread_end(self)

    def to_primitive(self) -> PrimitiveType:
        d: Dict[str, PrimitiveType] = {"@frg-spread": self.fragment_name}
        add_if_not_empty(d, "directives", self.directives)
        return d


class InlineFragment(Selection, Fragment):
    on_type: Optional[NamedType]
    directives: Sequence[Directive]
    selections: Sequence[Selection]

    def __init__(self,
                 on_type: Optional[NamedType],
                 directives: Sequence[Directive],
                 selections: Sequence[Selection]) -> None:
        self.on_type = on_type
        self.directives = directives
        self.selections = selections

    def visit(self, visitor: QueryVisitor) -> None:
        visitor.visit_inline_fragment_begin(self)

        for directive in self.directives:
            directive.visit(visitor)

        for sel in self.selections:
            sel.visit(visitor)

        visitor.visit_inline_fragment_end(self)

    def to_primitive(self) -> PrimitiveType:
        d: Dict[str, PrimitiveType] = {"@frg-inline": None}

        if self.on_type is not None:
            d["on_type"] = self.on_type.to_primitive()

        add_if_not_empty(d, "directives", self.directives)
        add_if_not_empty(d, "selections", self.selections)
        return d


__all__ = ["GraphQlModelType", "Document", "Operation", "Query", "Mutation", "VariableDefinition",
           "Type", "NamedType", "ListType", "Directive", "ConstValue", "Value", "Variable",
           "NullValue", "EnumValue", "IntValue", "FloatValue", "StrValue", "BoolValue",
           "ConstListValue", "ConstObjectValue", "ObjectValue", "Argument", "Fragment", "NamedFragment",
           "Selection", "FieldSelection", "FragmentSpread", "InlineFragment", "QueryVisitor"]
