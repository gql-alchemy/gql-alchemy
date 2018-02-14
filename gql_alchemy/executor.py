import typing as t

import gql_alchemy.query_model as qm
import gql_alchemy.schema as s
import gql_alchemy.types as gt
from .errors import GqlExecutionError
from .parser import parse_document
from .utils import PrimitiveType
from .validator import validate


class Resolver:
    def __init__(self, for_type: t.Optional[str] = None) -> None:
        if for_type is not None:
            self.type = for_type
        else:
            name = type(self).__name__
            if name.endswith("Resolver"):
                self.type = name[:-8]
            else:
                self.type = name


SomeResolver = t.TypeVar('SomeResolver', bound=Resolver)


class Executor:
    def __init__(self, schema: s.Schema, query_resolver: SomeResolver,
                 mutation_resolver: t.Optional[SomeResolver] = None) -> None:
        self.schema = schema
        self.type_registry = schema.type_registry
        self.query_resolver = query_resolver
        self.mutation_resolver = mutation_resolver
        self.query_object_name = schema.query_object_name
        self.mutation_object_name = schema.mutation_object_name

        if self.mutation_object_name is not None and mutation_resolver is None:
            raise GqlExecutionError("Mutation resolver required with schema that supports mutations")

    def query(self, query: str, variables: t.Mapping[str, PrimitiveType],
              op_to_run: t.Optional[str] = None) -> PrimitiveType:
        document = parse_document(query)

        validate(document, self.schema, variables, op_to_run)

        if op_to_run is None and len(document.operations) > 1:
            raise RuntimeError("Operation name is needed for queries with multiple operations defined")

        operation: t.Optional[qm.Operation] = None
        if op_to_run is None:
            operation = document.operations[0]
        else:
            for op in document.operations:
                if op.name == op_to_run:
                    operation = op

        if operation is None:
            raise RuntimeError("Operation `{}` is not found".format(op_to_run))

        if isinstance(operation, qm.Query):
            root_object_name = self.query_object_name
            resolver = self.query_resolver
        else:
            if self.mutation_object_name is None or self.mutation_resolver is None:
                raise RuntimeError("Server does not support mutations")
            root_object_name = self.mutation_object_name
            resolver = self.mutation_resolver

        return _OperationRunner(self.type_registry, variables, document).run_operation(
            t.cast(gt.Object, self.type_registry.resolve_type(root_object_name)),
            operation,
            resolver
        )


class _OperationRunner:
    def __init__(self, type_registry: gt.TypeRegistry,
                 vars_values: t.Mapping[str, PrimitiveType],
                 document: qm.Document) -> None:
        self.type_registry = type_registry
        self.vars_values = dict(vars_values)
        self.fragments = dict(((f.name, f) for f in document.fragments))

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
                 from_selectable: gt.SpreadableType,
                 resolver: t.Any) -> None:
        for sel in selections:
            if isinstance(sel, qm.FieldSelection):
                selectable = gt.assert_selectable(from_selectable)
                field = selectable.fields(self.type_registry)[sel.name]
                result[sel.alias if sel.alias is not None else sel.name] = self.__select_field(sel, field, resolver)
                continue
            if isinstance(sel, qm.FragmentSpread):
                self.__select_fragment(result, self.fragments[sel.fragment_name], from_selectable, resolver)
            if isinstance(sel, qm.InlineFragment):
                self.__select_fragment(result, sel, from_selectable, resolver)

    def __select_fragment(self, result: t.Dict[str, PrimitiveType], frg: qm.Fragment,
                          from_selectable: gt.SpreadableType,
                          resolver: SomeResolver) -> None:
        if frg.on_type is not None:
            on_type = gt.assert_spreadable(self.__resolve_type(frg.on_type.name))
            if isinstance(on_type, gt.Interface) or isinstance(on_type, gt.Union):
                possible_objects = {str(o) for o in on_type.of_objects(self.type_registry)}
            else:
                if not isinstance(on_type, gt.Object):
                    raise RuntimeError("Object expected here")
                possible_objects = {str(on_type)}

            if resolver.type not in possible_objects:
                return

            resolver_type = gt.assert_selectable(self.__resolve_type(resolver.type))

            self.__select(result, frg.selections, resolver_type, resolver)

        else:
            self.__select(result, frg.selections, from_selectable, resolver)

    def __select_field(self, field_selection: qm.FieldSelection, field_definition: gt.Field,
                       resolver: SomeResolver) -> PrimitiveType:
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
            attr = getattr(resolver, name)
            if len(args) == 0 and not callable(attr):
                subresolvers = attr
            else:
                subresolvers = attr(**args)
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
            result_arr: t.List[PrimitiveType] = []
            for sr in subresolvers:
                result_arr.append(self.__resolve_subresolvers(selections, field_type, sr))
            return result_arr

        result_dict: t.Dict[str, PrimitiveType] = {}
        self.__select(result_dict, selections, field_type, subresolvers)
        return result_dict

    def __select_plain_field(self, field_type: gt.GqlType, name: str, args: t.Mapping[str, PrimitiveType],
                             resolver: SomeResolver) -> PrimitiveType:
        try:
            attr = getattr(resolver, name)
            if len(args) == 0 and not callable(attr):
                result = t.cast(PrimitiveType, attr)
            else:
                result = t.cast(PrimitiveType, attr(**args))
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
