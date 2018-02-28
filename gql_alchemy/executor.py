import json
import typing as t

import gql_alchemy.query_model as qm
import gql_alchemy.schema as s
import gql_alchemy.types as gt
from .errors import GqlExecutionError
from .parser import parse_document
from .resolvers import Resolver, IntrospectionResolver, Introspection
from .utils import PrimitiveType
from .validator import validate

_py_reserved = {
    "False", "class", "finally", "is", "return",
    "None", "continue", "for", "lambda", "try",
    "True", "def", "from", "nonlocal", "while",
    "and", "del", "global", "not", "with",
    "as", "elif", "if", "or", "yield",
    "assert", "else", "import", "pass",
    "break", "except", "in", "raise"
}


SomeResolver = t.TypeVar('SomeResolver', bound=Resolver)


class Directive:
    def should_select_field(self, resolver: SomeResolver,
                            field_name: str) -> bool:
        return True

    def wrap_field(self, field: t.Any,
                   field_args: t.Mapping[str, PrimitiveType]) -> t.Any:
        return field


class _SkipDirective(Directive):
    def __init__(self, _if: bool) -> None:
        self.__if = _if

    def should_select_field(self, resolver: SomeResolver,
                            field_name: str) -> bool:
        return not self.__if


class _IncludeDirective(Directive):
    def __init__(self, _if: bool) -> None:
        self.__if = _if

    def should_select_field(self, resolver: SomeResolver,
                            field_name: str) -> bool:
        return self.__if


class _DirectivesEnv:
    def __init__(self, parent_directives: t.MutableSet[Directive],
                 own_directives: t.Sequence[qm.Directive],
                 directives_constructors: t.Mapping[str, t.Callable[..., Directive]],
                 vars_values: t.Mapping[str, PrimitiveType],
                 type_registry: gt.TypeRegistry) -> None:
        self.__parent_directives = parent_directives
        self.__own_directives = own_directives
        self.__type_registry = type_registry
        self.__directives_constructors = directives_constructors
        self.__vars_values = vars_values
        self.__added_directives: t.MutableSet[Directive] = set()

    def __enter__(self) -> None:
        for d in self.__own_directives:
            dir_c = self.__directives_constructors[d.name]
            d_def = self.__type_registry.directive(d.name)
            args = _prepare_args(d.arguments, self.__vars_values, d_def.args)
            directive = dir_c(**args)
            self.__parent_directives.add(directive)
            self.__added_directives.add(directive)

    def __exit__(self, exc_type: t.Any, exc_val: t.Any, exc_tb: t.Any) -> None:
        for d in self.__added_directives:
            self.__parent_directives.remove(d)


class Executor:
    def __init__(self, schema: s.Schema, query_resolver: SomeResolver,
                 mutation_resolver: t.Optional[SomeResolver] = None,
                 directives: t.Optional[t.Mapping[str, t.Callable[..., Directive]]] = None) -> None:
        self.schema = schema
        self.type_registry = schema.type_registry
        self.query_resolver = query_resolver
        self.mutation_resolver = mutation_resolver
        self.query_object_name = schema.query_object_name
        self.mutation_object_name = schema.mutation_object_name
        self.directives: t.Dict[str, t.Callable[..., Directive]] = dict(directives) if directives is not None else {}
        self.directives["skip"] = _SkipDirective
        self.directives["include"] = _IncludeDirective

        if self.mutation_object_name is not None and mutation_resolver is None:
            raise GqlExecutionError("Mutation resolver required with schema that supports mutations")

    def query(self, query: str, variables: t.Mapping[str, PrimitiveType],
              op_to_run: t.Optional[str] = None) -> PrimitiveType:
        document = parse_document(query)

        validate(document, self.schema, variables, op_to_run)

        if op_to_run is None and len(document.operations) > 1:
            raise GqlExecutionError("Operation name is needed for queries with multiple operations defined")

        operation: t.Optional[qm.Operation] = None
        if op_to_run is None:
            operation = document.operations[0]
        else:
            for op in document.operations:
                if op.name == op_to_run:
                    operation = op

        if operation is None:
            raise GqlExecutionError("Operation `{}` is not found".format(op_to_run))

        if isinstance(operation, qm.Query):
            root_object = self.type_registry.resolve_type(self.query_object_name)
            resolver: Resolver = IntrospectionResolver(self.query_resolver, Introspection(self.schema))
        else:
            if self.mutation_object_name is None or self.mutation_resolver is None:
                raise GqlExecutionError("Server does not support mutations")
            root_object = self.type_registry.resolve_type(self.mutation_object_name)
            resolver = self.mutation_resolver

        return _OperationRunner(self.type_registry, variables, document, self.directives).run_operation(
            t.cast(gt.Object, root_object),
            operation,
            resolver
        )


class _OperationRunner:
    def __init__(self, type_registry: gt.TypeRegistry,
                 vars_values: t.Mapping[str, PrimitiveType],
                 document: qm.Document,
                 directives: t.Mapping[str, t.Callable[..., Directive]]) -> None:
        self.type_registry = type_registry
        self.vars_values = dict(vars_values)
        self.fragments = dict(((f.name, f) for f in document.fragments))
        self.directives = directives

    def run_operation(self, root_object: gt.Object, operation: qm.Operation,
                      root_resolver: Resolver) -> t.Mapping[str, PrimitiveType]:
        for var in operation.variables:
            if var.default is not None:
                self.vars_values.setdefault(var.name, var.default.to_py_value({}))

        result: t.Dict[str, PrimitiveType] = {}
        directives: t.MutableSet[Directive] = set()

        with _DirectivesEnv(directives, operation.directives, self.directives, self.vars_values, self.type_registry):
            self.__select(directives, result, operation.selections, root_object, root_resolver)
        return result

    def __select(self, parent_directives: t.MutableSet[Directive], result: t.Dict[str, PrimitiveType],
                 selections: t.Sequence[qm.Selection],
                 from_selectable: gt.SpreadableType,
                 resolver: Resolver) -> None:
        for sel in selections:
            if isinstance(sel, qm.FieldSelection):
                selectable = gt.assert_selectable(from_selectable)
                field = selectable.fields(self.type_registry)[sel.name]
                self.__select_field(parent_directives, result, sel, field, resolver)
                continue
            if isinstance(sel, qm.FragmentSpread):
                with _DirectivesEnv(parent_directives, sel.directives, self.directives, self.vars_values,
                                    self.type_registry):
                    self.__select_fragment(parent_directives, result, self.fragments[sel.fragment_name],
                                           from_selectable,
                                           resolver)
            if isinstance(sel, qm.InlineFragment):
                self.__select_fragment(parent_directives, result, sel, from_selectable, resolver)

    def __select_fragment(self, parent_directives: t.MutableSet[Directive],
                          result: t.Dict[str, PrimitiveType], frg: qm.Fragment,
                          from_selectable: gt.SpreadableType,
                          resolver: SomeResolver) -> None:
        with _DirectivesEnv(parent_directives, frg.directives, self.directives, self.vars_values, self.type_registry):
            if frg.on_type is not None:
                on_type = gt.assert_spreadable(self.__resolve_type(frg.on_type.name))
                if isinstance(on_type, gt.Interface) or isinstance(on_type, gt.Union):
                    possible_objects = {str(o) for o in on_type.of_objects(self.type_registry)}
                else:
                    if not isinstance(on_type, gt.Object):
                        raise RuntimeError("Object expected here")
                    possible_objects = {str(on_type)}

                if resolver.for_gql_type not in possible_objects:
                    return

                resolver_type = gt.assert_selectable(self.__resolve_type(resolver.for_gql_type))

                self.__select(parent_directives, result, frg.selections, resolver_type, resolver)

            else:
                self.__select(parent_directives, result, frg.selections, from_selectable, resolver)

    def __select_field(self, parent_directives: t.MutableSet[Directive], result: t.Dict[str, PrimitiveType],
                       field_selection: qm.FieldSelection,
                       field_definition: gt.Field,
                       resolver: SomeResolver) -> None:
        with _DirectivesEnv(parent_directives, field_selection.directives, self.directives, self.vars_values,
                            self.type_registry):
            for d in parent_directives:
                if not d.should_select_field(resolver, field_selection.name):
                    return

            args = _prepare_args(field_selection.arguments, self.vars_values, field_definition.args)

            field_type = field_definition.type(self.type_registry)
            alias = field_selection.alias if field_selection.alias is not None else field_selection.name

            field_name = field_selection.name
            if field_name in _py_reserved:
                field_name = "_" + field_name
            elif field_name.startswith("__"):
                field_name = "f" + field_name

            if not hasattr(resolver, field_name):
                raise GqlExecutionError("Resolver `{}` for `{}` type does not have `{}` attribute".format(
                    type(resolver).__name__, resolver.for_gql_type, field_name
                ))

            attr = getattr(resolver, field_name)
            for d in parent_directives:
                attr = d.wrap_field(attr, args)

            if len(args) == 0 and not callable(attr):
                field_raw_value = attr
            else:
                try:
                    field_raw_value = attr(**args)
                except Exception as e:
                    raise GqlExecutionError("Resolver internal error") from e

            if len(field_selection.selections) > 0:
                result[alias] = self.__process_spreadable_field(
                    parent_directives, field_type, field_raw_value, field_selection.selections
                )
            else:
                result[alias] = self.__select_plain_field(resolver, field_name, field_type, field_raw_value)

    def __process_spreadable_field(self, parent_directives: t.MutableSet[Directive], field_type: gt.GqlType,
                                   field_raw_value: t.Any,
                                   selections: t.Sequence[qm.Selection]) -> PrimitiveType:

        if not self.__resolver_compatible(field_type, field_raw_value):
            raise GqlExecutionError("Resolver returns non compatible sub-resolver")

        return self.__resolve_subresolvers(
            parent_directives,
            selections,
            gt.assert_spreadable(self.__resolve_and_unwrap(field_type)),
            field_raw_value
        )

    def __resolver_compatible(self, field_type: gt.GqlType, field_raw_value: t.Any) -> bool:
        if isinstance(field_type, gt.NonNull):
            if field_raw_value is None:
                return False
            return self.__resolver_compatible(field_type.of_type(self.type_registry), field_raw_value)

        if field_raw_value is None:
            return True

        if isinstance(field_type, gt.List):
            if not isinstance(field_raw_value, list):
                return False
            for resolver in field_raw_value:
                if not self.__resolver_compatible(field_type.of_type(self.type_registry), resolver):
                    return False
            return True

        if isinstance(field_type, gt.Interface) or isinstance(field_type, gt.Union):
            possible_objects = field_type.of_objects(self.type_registry)
            possible_objects_names = {str(o) for o in possible_objects}
            return field_raw_value.for_gql_type in possible_objects_names

        if isinstance(field_type, gt.Object):
            resolver_type = t.cast(t.Optional[str], field_raw_value.for_gql_type)
            return str(field_type) == resolver_type

        raise RuntimeError("Wrapper or spreadable expected here, but got {}".format(type(field_type).__name__))

    def __resolve_subresolvers(self, parent_directives: t.MutableSet[Directive], selections: t.Sequence[qm.Selection],
                               field_type: gt.SpreadableType,
                               field_raw_value: t.Any) -> PrimitiveType:
        if field_raw_value is None:
            return None

        if isinstance(field_raw_value, list):
            result_arr: t.List[PrimitiveType] = []
            for item_raw_value in field_raw_value:
                result_arr.append(
                    self.__resolve_subresolvers(parent_directives, selections, field_type, item_raw_value)
                )
            return result_arr

        result_dict: t.Dict[str, PrimitiveType] = {}
        self.__select(parent_directives, result_dict, selections, field_type, field_raw_value)
        return result_dict

    def __select_plain_field(self, resolver: Resolver, field_name: str, field_type: gt.GqlType,
                             field_raw_value: t.Any) -> PrimitiveType:
        if not field_type.is_assignable(field_raw_value, self.type_registry):
            raise GqlExecutionError(
                "Resolver `{}` for type `{}` returns not assignable value '{}' for field `{}` of type `{}`".format(
                    type(resolver).__name__, resolver.for_gql_type, json.dumps(field_raw_value), field_name,
                    str(field_type)
                )
            )

        return t.cast(PrimitiveType, field_raw_value)

    def __resolve_type(self, schema_type: t.Union[gt.GqlType, str]) -> gt.GqlType:
        return self.type_registry.resolve_type(schema_type)

    def __resolve_and_unwrap(self, schema_type: t.Union[gt.GqlType, str]) -> gt.NonWrapperType:
        return self.type_registry.resolve_and_unwrap(schema_type)


def _prepare_args(arguments: t.Sequence[qm.Argument],
                  vars_values: t.Mapping[str, PrimitiveType],
                  args_def: t.Mapping[str, gt.Argument]) -> t.Mapping[str, PrimitiveType]:
    args_values = {}
    for arg in arguments:
        name = arg.name if arg.name not in _py_reserved else "_" + arg.name
        args_values[name] = arg.value.to_py_value(vars_values)

    for arg_name, arg_def in args_def.items():
        name = arg_name if arg_name not in _py_reserved else "_" + arg_name
        args_values.setdefault(name, arg_def.default)

    return args_values
