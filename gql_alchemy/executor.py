import typing as t

import gql_alchemy.query_model as qm
import gql_alchemy.schema as s
import gql_alchemy.types as gt
from .errors import GqlExecutionQueryError, GqlExecutionResolverError
from .parser import parse_document
from .utils import PrimitiveType


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
            raise GqlExecutionQueryError("Operation name is needed for queries with multiple operations defined")

        operation: t.Optional[qm.Operation] = None
        if operation_name is None:
            operation = document.operations[0]
        else:
            for op in document.operations:
                if op.name == operation_name:
                    operation = op

        if operation is None:
            raise GqlExecutionQueryError("Operation `{}` is not found".format(operation_name))

        if isinstance(operation, qm.Query):
            root_object_name = self.query_object_name
        else:
            if self.mutation_object_name is None:
                raise GqlExecutionQueryError("Server does not support mutations")
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
        self.vars_defs: t.Dict[str, gt.GqlType] = {}

    def run_operation(self, root_object: gt.Object, operation: qm.Operation,
                      root_resolver: t.Any) -> t.Mapping[str, PrimitiveType]:
        for var in operation.variables:
            var_type = self.__resolve_type(self.__to_schema_type(var.type))

            self.vars_defs[var.name] = var_type

            if var.default is not None:
                var_type_wrapper = gt.is_wrapper(var_type)

                if var_type_wrapper is not None:
                    if not var_type_wrapper.validate_input(var.default, self.vars_values, self.vars_defs,
                                                           self.type_registry):
                        raise GqlExecutionQueryError("default is not assignable to type")
                else:
                    var_type_input = gt.assert_input(var_type)
                    if not var_type_input.validate_input(var.default, self.vars_values, self.vars_defs,
                                                         self.type_registry):
                        raise GqlExecutionQueryError("default is not assignable to type")

            if var.name not in self.vars_values:
                self.vars_values[var.name] = var.default.to_primitive() if var.default is not None else None

            if not var_type.is_assignable(self.vars_values[var.name], self.type_registry):
                raise GqlExecutionQueryError("Wrong value for variable type")
        # todo(rlz): apply directives
        return self.__select(operation.selections, root_object, root_resolver)

    def __select(self, selections: t.Sequence[qm.Selection], spreadable: gt.SpreadableType,
                 resolver: t.Any) -> t.Mapping[str, PrimitiveType]:
        result: t.Dict[str, PrimitiveType] = {}

        for sel in selections:
            if isinstance(sel, qm.FieldSelection):
                selectable = gt.is_selectable(spreadable)
                if selectable is None:
                    raise GqlExecutionQueryError("Can not select field from union, use fragment or inline spread")
                field = selectable.fields(self.type_registry).get(sel.name)
                if field is None:
                    raise GqlExecutionQueryError("Selecting not defined field")
                result[sel.alias if sel.alias is not None else sel.name] = self.__select_field(sel, field, resolver)
                continue
            if isinstance(sel, qm.FragmentSpread):
                raise NotImplementedError()
            if isinstance(sel, qm.InlineFragment):
                raise NotImplementedError()

        return result

    def __select_field(self, field_selection: qm.FieldSelection, field_definition: gt.Field,
                       resolver: t.Any) -> PrimitiveType:
        args = self.__validate_args(field_selection.arguments, field_definition.args)

        field_type = field_definition.type(self.type_registry)
        field_unwrapped_type = self.type_registry.resolve_and_unwrap(field_type)

        if gt.is_spreadable(field_unwrapped_type) is not None:
            if len(field_selection.selections) == 0:
                raise GqlExecutionQueryError()
            return self.__select_spreadable_field(field_type, field_selection.name, args, field_selection.selections,
                                                  resolver)
        else:
            return self.__select_plain_field(field_type, field_selection.name, args, resolver)

    def __select_spreadable_field(self, field_type: gt.GqlType, name: str, args: t.Mapping[str, PrimitiveType],
                                  selections: t.Sequence[qm.Selection],
                                  resolver: t.Any) -> PrimitiveType:
        try:
            subresolvers = getattr(resolver, name).__call__(args)
        except Exception as e:
            raise GqlExecutionResolverError("Resolver internal error") from e
        if not self.__resolver_compatible(field_type, subresolvers):
            raise GqlExecutionResolverError("Resolver returns non compatible sub-resolver")
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
        if isinstance(field_type, gt.List):
            if not isinstance(resolvers, list):
                return False
            for resolver in resolvers:
                if not self.__resolver_compatible(field_type.of_type(self.type_registry), resolver):
                    return False
            return True
        if isinstance(field_type, gt.Interface):
            possible_objects = self.type_registry.objects_by_interface(str(field_type))
            possible_objects_names = {str(o) for o in possible_objects}
            return getattr(resolvers, "type", None) in possible_objects_names
        if isinstance(field_type, gt.Union):
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

        return self.__select(selections, field_type, subresolvers)

    def __select_plain_field(self, field_type: gt.GqlType, name: str, args: t.Mapping[str, PrimitiveType],
                             resolver: t.Any) -> PrimitiveType:
        try:
            result = t.cast(PrimitiveType, getattr(resolver, name).__call__(args))
        except Exception as e:
            raise GqlExecutionResolverError("Resolver internal error") from e
        if not field_type.is_assignable(result, self.type_registry):
            raise GqlExecutionResolverError("Resolver returns wrong type")
        return result

    def __validate_args(self, sel_args: t.Sequence[qm.Argument],
                        def_args: t.Mapping[str, gt.Argument]) -> t.Mapping[str, PrimitiveType]:
        arguments: t.Dict[str, PrimitiveType] = {}

        sel_args_dict = dict(((a.name, a) for a in sel_args))
        sel_args_names = set(sel_args_dict.keys())
        if len(sel_args_names) < len(sel_args):
            # todo(rlz): move it to parsing errors
            raise GqlExecutionQueryError("Selection arguments are not unique")
        if len(sel_args_names.difference(def_args.keys())) > 0:
            raise GqlExecutionQueryError("Undefined argument in selection")

        for arg_name, arg_def in def_args.items():
            arg_sel = sel_args_dict.get(arg_name)

            if arg_sel is not None:
                arg_value = arg_sel.value
                if not arg_def.validate_input(arg_value, self.vars_values, self.vars_defs, self.type_registry):
                    raise GqlExecutionQueryError()
                arguments[arg_name] = arg_value.to_py_value(self.vars_values)

            elif arg_def.default is None:
                if not arg_def.validate_input(qm.NullValue(), self.vars_values, self.vars_defs, self.type_registry):
                    raise GqlExecutionQueryError()
                arguments[arg_name] = None

            else:
                arguments[arg_name] = arg_def.default

        return arguments

    def __to_schema_type(self, query_type: qm.Type) -> t.Union[gt.WrapperType, str]:
        if isinstance(query_type, qm.NamedType):
            if query_type.null:
                return query_type.name
            return gt.NonNull(query_type.name)
        query_type = t.cast(qm.ListType, query_type)
        if query_type.null:
            return gt.List(self.__to_schema_type(query_type.el_type))
        return gt.NonNull(gt.List(self.__to_schema_type(query_type.el_type)))

    def __resolve_type(self, schema_type: t.Union[gt.GqlType, str]) -> gt.GqlType:
        try:
            return self.type_registry.resolve_type(schema_type)
        except gt.TypeResolvingError as e:
            raise GqlExecutionQueryError(str(e)) from e

    def __resolve_and_unwrap(self, schema_type: t.Union[gt.GqlType, str]) -> gt.NonWrapperType:
        try:
            return self.type_registry.resolve_and_unwrap(schema_type)
        except gt.TypeResolvingError as e:
            raise GqlExecutionQueryError(str(e)) from e
