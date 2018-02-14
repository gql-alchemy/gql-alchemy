import typing as t

import gql_alchemy.query_model as qm
import gql_alchemy.schema as s
import gql_alchemy.types as gt
from .errors import GqlExecutionError
from .parser import parse_document
from .utils import PrimitiveType


class Resolver:
    def __init__(self, type: str):
        self.type = type


class Executor:
    def __init__(self, schema: s.Schema, resolver: t.Any) -> None:
        self.type_registry = schema.type_registry
        self.resolver = resolver
        self.query_object_name = schema.query_object_name
        self.mutation_object_name = schema.mutation_object_name

    def query(self, query: str, variables: t.Mapping[str, PrimitiveType],
              operation_name: t.Optional[str] = None) -> PrimitiveType:
        document = parse_document(query)

        if operation_name is None and len(document.operations) > 1:
            raise RuntimeError("Operation name is needed for queries with multiple operations defined")

        operation: t.Optional[qm.Operation] = None
        if operation_name is None:
            operation = document.operations[0]
        else:
            for op in document.operations:
                if op.name == operation_name:
                    operation = op

        if operation is None:
            raise RuntimeError("Operation `{}` is not found".format(operation_name))

        if isinstance(operation, qm.Query):
            root_object_name = self.query_object_name
        else:
            if self.mutation_object_name is None:
                raise RuntimeError("Server does not support mutations")
            root_object_name = self.mutation_object_name

        return _OperationRunner(self.type_registry, variables).run_operation(
            t.cast(gt.Object, self.type_registry.resolve_type(root_object_name)),
            operation,
            self.resolver
        )


class _OperationRunner:
    def __init__(self, type_registry: gt.TypeRegistry,
                 vars_values: t.Mapping[str, PrimitiveType]) -> None:
        self.type_registry = type_registry
        self.vars_values = dict(vars_values)

    def run_operation(self, root_object: gt.Object, operation: qm.Operation,
                      root_resolver: t.Any) -> t.Mapping[str, PrimitiveType]:
        for var in operation.variables:
            if var.default is not None:
                self.vars_values.setdefault(var.name, var.default.to_py_value({}))

        # todo(rlz): apply directives
        result: t.Dict[str, PrimitiveType] = {}
        self.__select(result, operation.selections, root_object, root_resolver)
        return result

    def __select(self, result: t.Dict[str, PrimitiveType], selections: t.Sequence[qm.Selection],
                 spreadable: gt.SpreadableType,
                 resolver: t.Any) -> None:
        for sel in selections:
            if isinstance(sel, qm.FieldSelection):
                selectable = gt.assert_selectable(spreadable)
                field = selectable.fields(self.type_registry)[sel.name]
                result[sel.alias if sel.alias is not None else sel.name] = self.__select_field(sel, field, resolver)
                continue
            if isinstance(sel, qm.FragmentSpread):
                raise NotImplementedError()
            if isinstance(sel, qm.InlineFragment):
                self.__select(result, sel.selections, spreadable, resolver)

    def __select_field(self, field_selection: qm.FieldSelection, field_definition: gt.Field,
                       resolver: t.Any) -> PrimitiveType:
        args = self.__prepare_args(field_selection.arguments)

        field_type = field_definition.type(self.type_registry)

        if len(field_selection.selections) > 0:
            return self.__select_spreadable_field(field_type, field_selection.name, args, field_selection.selections,
                                                  resolver)
        else:
            return self.__select_plain_field(field_type, field_selection.name, args, resolver)

    def __select_spreadable_field(self, field_type: gt.GqlType, name: str, args: t.Mapping[str, PrimitiveType],
                                  selections: t.Sequence[qm.Selection],
                                  resolver: t.Any) -> PrimitiveType:
        try:
            subresolvers = getattr(resolver, name)(**args)
        except Exception as e:
            raise GqlExecutionError("Resolver internal error") from e
        if not self.__resolver_compatible(field_type, subresolvers):
            raise GqlExecutionError("Resolver returns non compatible sub-resolver")
        return self.__resolve_subresolvers(
            selections,
            gt.assert_spreadable(self.__resolve_and_unwrap(field_type)),
            subresolvers
        )

    def __resolver_compatible(self, field_type: gt.GqlType, resolvers: t.Any) -> bool:
        if isinstance(field_type, gt.NonNull):
            if resolvers is None:
                return False
            return self.__resolver_compatible(field_type.of_type(self.type_registry), resolvers)

        if resolvers is None:
            return True

        if isinstance(field_type, gt.List):
            if not isinstance(resolvers, list):
                return False
            for resolver in resolvers:
                if not self.__resolver_compatible(field_type.of_type(self.type_registry), resolver):
                    return False
            return True

        if isinstance(field_type, gt.Interface) or isinstance(field_type, gt.Union):
            possible_objects = field_type.of_objects(self.type_registry)
            possible_objects_names = {str(o) for o in possible_objects}
            return getattr(resolvers, "type", None) in possible_objects_names

        if isinstance(field_type, gt.Object):
            resolver_type = t.cast(t.Optional[str], getattr(resolvers, "type", None))
            return str(field_type) == resolver_type

        raise RuntimeError("Wrapper or spreadable expected here, but got {}".format(type(field_type).__name__))

    def __resolve_subresolvers(self, selections: t.Sequence[qm.Selection], field_type: gt.SpreadableType,
                               subresolvers: t.Any) -> PrimitiveType:
        if subresolvers is None:
            return None

        if isinstance(subresolvers, list):
            result = []
            for sr in subresolvers:
                result.append(self.__resolve_subresolvers(selections, field_type, sr))
            return result

        result = {}
        self.__select(result, selections, field_type, subresolvers)
        return result

    def __select_plain_field(self, field_type: gt.GqlType, name: str, args: t.Mapping[str, PrimitiveType],
                             resolver: t.Any) -> PrimitiveType:
        try:
            result = t.cast(PrimitiveType, getattr(resolver, name).__call__(**args))
        except Exception as e:
            raise GqlExecutionError("Resolver internal error") from e
        if not field_type.is_assignable(result, self.type_registry):
            raise GqlExecutionError("Resolver returns wrong type")
        return result

    def __prepare_args(self, arguments: t.Sequence[qm.Argument]) -> t.Mapping[str, PrimitiveType]:
        args_values = {}
        for arg in arguments:
            args_values[arg.name] = arg.value.to_py_value(self.vars_values)
        return args_values

    def __resolve_type(self, schema_type: t.Union[gt.GqlType, str]) -> gt.GqlType:
        return self.type_registry.resolve_type(schema_type)

    def __resolve_and_unwrap(self, schema_type: t.Union[gt.GqlType, str]) -> gt.NonWrapperType:
        return self.type_registry.resolve_and_unwrap(schema_type)
