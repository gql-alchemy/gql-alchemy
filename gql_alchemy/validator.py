import json
import logging
import typing as t

import gql_alchemy.query_model as qm
import gql_alchemy.schema as s
import gql_alchemy.types as gt
from .errors import GqlValidationError
from .utils import PrimitiveType

logger = logging.getLogger("gql_alchemy")


class Env:
    def __init__(self, vars_definitions: t.Mapping[str, t.Union[gt.InputType, gt.WrapperType]],
                 vars_values: t.Optional[t.Mapping[str, PrimitiveType]]) -> None:
        self.vars_definitions = vars_definitions
        self.vars_values = vars_values


class Validator(qm.QueryVisitor):
    def __init__(self, type_registry: gt.TypeRegistry, query: gt.Object,
                 mutation: t.Optional[gt.Object]) -> None:
        self.__name = type(self).__name__
        self.type_registry = type_registry
        self.__query = query
        self.__mutation = mutation

        self._def_name = ""
        self._spreadables: t.List[gt.SpreadableType] = []
        self._location: gt.DirectiveLocation = gt.DirectiveLocations.QUERY

    def visit_query_begin(self, query: qm.Query) -> None:
        logger.debug("%s - visit query %s", self.__name, query.name)
        self._def_name = query.name if query.name is not None else "!"
        self._spreadables.append(self.__query)
        self._location = gt.DirectiveLocations.QUERY

    def visit_query_end(self, query: qm.Query) -> None:
        logger.debug("%s - finish query %s", self.__name, query.name)
        del self._spreadables[-1]

    def visit_mutation_begin(self, mutation: qm.Mutation) -> None:
        logger.debug("%s - visit mutation %s", self.__name, mutation.name)
        if self.__mutation is None:
            raise GqlValidationError("Mutations are not allowed by schema")

        self._def_name = mutation.name if mutation.name is not None else "!"
        self._spreadables.append(self.__mutation)
        self._location = gt.DirectiveLocations.MUTATION

    def visit_mutation_end(self, mutation: qm.Mutation) -> None:
        logger.debug("%s - finish mutation %s", self.__name, mutation.name)
        del self._spreadables[-1]

    def visit_fragment_begin(self, fragment: qm.NamedFragment) -> None:
        logger.debug("%s - visit fragment %s", self.__name, fragment.name)
        self._def_name = fragment.name

        on_type = self._resolve_type(fragment.on_type)
        spreadable = gt.is_spreadable(on_type)
        if spreadable is None:
            raise GqlValidationError(
                "Fragments can be defined only on spreadable types; problem with `{}` fragment".format(fragment.name)
            )
        self._spreadables.append(spreadable)

        self._location = gt.DirectiveLocations.FRAGMENT_DEFINITION

    def visit_fragment_end(self, fragment: qm.NamedFragment) -> None:
        logger.debug("%s - finish fragment %s", self.__name, fragment.name)
        del self._spreadables[-1]

    def visit_field_selection_begin(self, field_sel: qm.FieldSelection) -> None:
        logger.debug("%s - visit field %s", self.__name, field_sel.name)
        self._location = gt.DirectiveLocations.FIELD

        field_def = self.__get_field_def(field_sel)
        field_type = field_def.type(self.type_registry)

        if len(field_sel.selections) > 0:
            spreadable = gt.is_spreadable(self.type_registry.resolve_and_unwrap(field_type))
            if spreadable is None:
                raise GqlValidationError("Can not select from non spreadable type `{}`".format(field_type))
            self._spreadables.append(spreadable)
        else:
            spreadable = gt.is_spreadable(self.type_registry.resolve_and_unwrap(field_type))
            if spreadable is not None:
                raise GqlValidationError("Spreadable type `{}` must be selected with sub-selections".format(field_type))

    def visit_field_selection_end(self, field_sel: qm.FieldSelection) -> None:
        logger.debug("%s - finish field %s", self.__name, field_sel.name)
        if len(field_sel.selections) > 0:
            del self._spreadables[-1]

    def visit_fragment_spread_begin(self, spread: qm.FragmentSpread) -> None:
        logger.debug("%s - fragment spread %s", self.__name, spread.fragment_name)
        self._location = gt.DirectiveLocations.FRAGMENT_SPREAD

    def visit_inline_fragment_begin(self, fragment: qm.InlineFragment) -> None:
        logger.debug("%s - visit inline fragment", self.__name)
        self._location = gt.DirectiveLocations.INLINE_FRAGMENT

        if fragment.on_type is not None:
            on_type_name = fragment.on_type.name
            spreadable = self._spreadables[-1]
            if isinstance(spreadable, gt.Object):
                if on_type_name != str(spreadable):
                    raise GqlValidationError(
                        "Inline fragment on object field must be of the same type; `{}` expected, got `{}`".format(
                            spreadable, on_type_name
                        )
                    )
                self._spreadables.append(spreadable)
            elif isinstance(spreadable, gt.Union) or isinstance(spreadable, gt.Interface):
                of_objects = {str(o) for o in spreadable.of_objects(self.type_registry)}
                if on_type_name not in of_objects:
                    of_objects_list = list(of_objects)
                    of_objects_list.sort()
                    raise GqlValidationError("One of {} types expected, but got `{}`".format(
                        ", ".join(('`' + o + '`' for o in of_objects_list)),
                        on_type_name
                    ))
                self._spreadables.append(gt.assert_spreadable(self.type_registry.resolve_type(on_type_name)))
            else:
                raise RuntimeError("Spreadable must be Object, Interface or Union")
        else:
            if gt.is_selectable(self._spreadables[-1]) is None:
                raise GqlValidationError(
                    "Inline fragment without type possible only on selectable type, {} is not selectable".format(
                        self._spreadables[-1]
                    )
                )

    def visit_inline_fragment_end(self, fragment: qm.InlineFragment) -> None:
        logger.debug("%s - finish inline fragment", self.__name)
        if fragment.on_type is not None:
            del self._spreadables[-1]

    def _resolve_type(self, query_type: qm.Type) -> gt.GqlType:
        if isinstance(query_type, qm.NamedType):
            try:
                resolved_type = self.type_registry.resolve_type(query_type.name)
            except gt.TypeResolvingError as e:
                raise GqlValidationError("Unknown type `{}` used".format(query_type.name)) from e
            if query_type.null:
                return resolved_type
            return gt.NonNull(query_type.name)

        if isinstance(query_type, qm.ListType):
            element_type = self._resolve_type(query_type.el_type)

            inline = gt.is_inline(element_type)
            if inline is not None:
                list_type = gt.List(inline)
            else:
                list_type = gt.List(str(element_type))

            if query_type.null:
                return list_type

            return gt.NonNull(list_type)

        raise RuntimeError("One of named or list type expected here")

    def __get_field_def(self, field_sel: qm.FieldSelection) -> gt.Field:
        selectable = gt.is_selectable(self._spreadables[-1])
        if selectable is None:
            raise GqlValidationError("Can not select `{}` from non selectable `{}` type".format(
                field_sel.name, str(self._spreadables[-1])
            ))

        fields_defs = selectable.fields(self.type_registry)
        if field_sel.name not in fields_defs:
            raise GqlValidationError("`{}` type does not define `{}` field".format(str(selectable), field_sel.name))
        return fields_defs[field_sel.name]

    def _path(self) -> str:
        path_parts = [self._def_name]

        for sp in self._spreadables:
            path_parts.append(str(sp))

        return "/".join(path_parts)


class PassOne(Validator):
    def __init__(self, type_registry: gt.TypeRegistry, query: gt.Object, mutation: t.Optional[gt.Object]) -> None:
        super().__init__(type_registry, query, mutation)
        self.fragments: t.Dict[str, gt.SpreadableType] = {}

    def visit_fragment_begin(self, fragment: qm.NamedFragment) -> None:
        super().visit_fragment_begin(fragment)
        on_type = self._resolve_type(fragment.on_type)
        spreadable = gt.is_spreadable(on_type)
        if spreadable is None:
            raise GqlValidationError(
                "Fragment must be defined on spreadable type, `{}` is not spreadable".format(on_type)
            )
        self.fragments[fragment.name] = spreadable


class PassTwo(Validator):
    def __init__(self, fragments: t.Dict[str, gt.SpreadableType],
                 type_registry: gt.TypeRegistry, query: gt.Object, mutation: t.Optional[gt.Object],
                 vars_values: t.Mapping[str, PrimitiveType],
                 op_to_run: t.Optional[str]) -> None:
        super().__init__(type_registry, query, mutation)
        self.__fragments = fragments
        self.__vars_values = vars_values
        self.__op_to_run = op_to_run

        self.__root: t.Optional[t.Union[qm.Operation, qm.NamedFragment]] = None
        self.fragment_calls: t.Dict[str, t.List[t.Union[qm.Operation, qm.NamedFragment]]] = {}
        self.environments: t.Dict[str, Env] = {}

    def visit_query_begin(self, query: qm.Query) -> None:
        super().visit_query_begin(query)
        self.__root = query
        self.__save_env(query)

    def visit_mutation_begin(self, mutation: qm.Mutation) -> None:
        super().visit_mutation_begin(mutation)
        self.__root = mutation
        self.__save_env(mutation)

    def visit_fragment_begin(self, fragment: qm.NamedFragment) -> None:
        super().visit_fragment_begin(fragment)
        self.__root = fragment

    def visit_fragment_spread_begin(self, spread: qm.FragmentSpread) -> None:
        super().visit_fragment_spread_begin(spread)

        if self.__root is None:
            raise RuntimeError("Root object always expected here")

        if spread.fragment_name not in self.__fragments:
            raise GqlValidationError("Undefined fragment `{}` called".format(spread.fragment_name))

        called_on_type = self._spreadables[-1]
        defined_on_type = self.__fragments[spread.fragment_name]

        if str(called_on_type) != str(defined_on_type):
            if isinstance(called_on_type, gt.Interface) or isinstance(called_on_type, gt.Union):
                if str(defined_on_type) not in {str(o) for o in called_on_type.of_objects(self.type_registry)}:
                    raise GqlValidationError(
                        "Fragment `{}` can not be called on `{}` type".format(spread.fragment_name, called_on_type)
                    )
            else:
                raise GqlValidationError(
                    "Fragment `{}` can not be called on `{}` type".format(spread.fragment_name, called_on_type)
                )

        if spread.fragment_name not in self.fragment_calls:
            self.fragment_calls[spread.fragment_name] = []
        self.fragment_calls[spread.fragment_name].append(self.__root)

    def __save_env(self, op: qm.Operation) -> None:
        vars_definitions: t.Dict[str, t.Union[gt.InputType, gt.WrapperType]] = {}
        vars_defaults: t.Dict[str, t.Optional[qm.ConstValue]] = {}

        for var in op.variables:
            var_type = self._resolve_type(var.type)
            var_type_input_or_wrapper: t.Union[gt.InputType, gt.WrapperType, None] = gt.is_input(var_type)
            if var_type_input_or_wrapper is None:
                var_type_input_or_wrapper = gt.is_wrapper(var_type)
                if var_type_input_or_wrapper is None:
                    raise GqlValidationError(
                        "Only input types and their wrappers can be used as var types; "
                        "var `{}` of `{}` operation is not input type".format(var.name, op.name)
                    )
                var_type_input = gt.is_input(self.type_registry.resolve_and_unwrap(var_type_input_or_wrapper))
                if var_type_input is None:
                    raise GqlValidationError(
                        "Only input types and their wrappers can be used as var types; "
                        "var `{}` of `{}` operation is not input type".format(var.name, op.name)
                    )
                vars_definitions[var.name] = var_type_input_or_wrapper
            else:
                vars_definitions[var.name] = var_type_input_or_wrapper

            if var.default is not None:
                if not var_type_input_or_wrapper.validate_input(var.default, None, {}, self.type_registry):
                    raise GqlValidationError("Non compatible default value for `{}` variable of `{}` operation".format(
                        var.name, op.name
                    ))

            vars_defaults[var.name] = var.default

        if self.__is_running(op):
            vars_values = dict(self.__vars_values)
            for var_name, default in vars_defaults.items():
                if default is not None:
                    vars_values.setdefault(var_name, default.to_py_value({}))
            env = Env(vars_definitions, vars_values)
        else:
            env = Env(vars_definitions, None)

        for var_name, var_type in env.vars_definitions.items():
            default = vars_defaults[var_name]
            if default is not None:
                if not var_type.validate_input(default, None, {}, self.type_registry):
                    raise GqlValidationError(
                        "Variable can not be assigned to its default; "
                        "problem with `{}` variable in `{}` operation".format(var_name, op.name)
                    )
            if env.vars_values is not None:
                if var_name in env.vars_values:
                    if not var_type.is_assignable(env.vars_values[var_name], self.type_registry):
                        raise GqlValidationError(
                            "Wrong value {} provided for `{}` variable of `{}` operation".format(
                                json.dumps(env.vars_values[var_name]), var_name, op.name
                            )
                        )
                elif vars_defaults[var_name] is None:
                    raise GqlValidationError(
                        "Variable `{}` is required in `{}` operation".format(var_name, op.name)
                    )

        self.environments[op.name if op.name is not None else "!"] = env

    def __is_running(self, op: qm.Operation) -> bool:
        if self.__op_to_run is None:
            return True

        return op.name == self.__op_to_run


class PassThree(Validator):
    """Verify operations and collect environments for fragments used in query"""

    def __init__(self,
                 environments: t.Mapping[str, Env],
                 fragment_calls: t.Mapping[str, t.Sequence[t.Union[qm.Operation, qm.NamedFragment]]],
                 type_registry: gt.TypeRegistry,
                 query: gt.Object,
                 mutation: t.Optional[gt.Object]) -> None:
        Validator.__init__(self, type_registry, query, mutation)
        self.__environments = environments
        self.__fragment_calls = fragment_calls

        self.__current_envs: t.Sequence[Env] = []
        self.__args_defs: t.Mapping[str, gt.Argument] = {}

    def visit_query_begin(self, query: qm.Query) -> None:
        super().visit_query_begin(query)
        self.__current_envs = [self.__environments[self._def_name]]

    def visit_mutation_begin(self, mutation: qm.Mutation) -> None:
        super().visit_mutation_begin(mutation)
        self.__current_envs = [self.__environments[self._def_name]]

    def visit_fragment_begin(self, fragment: qm.NamedFragment) -> None:
        super().visit_fragment_begin(fragment)
        self.__current_envs = self.__resolve_fragment_envs(fragment)

    def visit_field_selection_begin(self, field_sel: qm.FieldSelection) -> None:
        super().visit_field_selection_begin(field_sel)

        if len(field_sel.selections) > 0:
            parent_spreadable = self._spreadables[-2]
        else:
            parent_spreadable = self._spreadables[-1]

        parent_selectable = gt.assert_selectable(parent_spreadable)
        field_def = parent_selectable.fields(self.type_registry)[field_sel.name]

        self.__validate_args(field_sel.arguments, field_def.args)
        self.__args_defs = field_def.args

    def visit_directive_begin(self, directive: qm.Directive) -> None:
        super().visit_directive_begin(directive)

        dir_def = self.__resolve_directive(directive.name)
        if self._location not in dir_def.locations:
            raise GqlValidationError("Can not use `{}` in `{}` location".format(directive.name, self._location))

        self.__validate_args(directive.arguments, dir_def.args)
        self.__args_defs = dir_def.args

    def visit_argument(self, argument: qm.Argument) -> None:
        super().visit_argument(argument)

        if argument.name not in self.__args_defs:
            raise GqlValidationError("Unsupported argument `{}`".format(argument.name))

        arg_def = self.__args_defs[argument.name]

        for env in self.__current_envs:
            try:
                if not arg_def.validate_input(argument.value, env.vars_values, env.vars_definitions,
                                              self.type_registry):
                    raise GqlValidationError("Can not use `{}` as `{}` argument".format(
                        json.dumps(argument.value.to_primitive()),
                        argument.name
                    ))
            except gt.UndefinedVariableError as e:
                raise GqlValidationError("{}; ??".format(
                    str(e)
                )) from e
            except gt.NonCompatibleVariableType as e:
                raise GqlValidationError("{}; ??".format(
                    str(e)
                )) from e

    def __validate_args(self, args_provided: t.Sequence[qm.Argument], args_defs: t.Mapping[str, gt.Argument]) -> None:
        args_defined_names = {a for a in args_defs.keys()}
        args_required_names = {
            name for name, arg in args_defs.items()
            if arg.default is None and isinstance(arg.type(self.type_registry), gt.NonNull)
        }
        args_provided_names = {arg.name for arg in args_provided}

        unsupported_args = list(args_provided_names.difference(args_defined_names))
        if len(unsupported_args) > 0:
            if len(unsupported_args) == 1:
                raise GqlValidationError("Argument `{}` is not supported".format(
                    next(iter(unsupported_args))
                ))
            else:
                unsupported_args.sort()
                raise GqlValidationError("Arguments {} are not supported".format(
                    ', '.join(("`" + arg_name + "`" for arg_name in unsupported_args))
                ))

        unfilled_args = list(args_required_names.difference(args_provided_names))
        if len(unfilled_args) > 0:
            if len(unfilled_args) == 1:
                raise GqlValidationError("Argument `{}` is required".format(
                    next(iter(unfilled_args))
                ))
            else:
                unfilled_args.sort()
                raise GqlValidationError("Arguments {} are required".format(
                    ', '.join(("`" + arg_name + "`" for arg_name in unfilled_args))
                ))

    def __resolve_directive(self, name: str) -> gt.Directive:
        try:
            return self.type_registry.directive(name)
        except gt.TypeResolvingError as e:
            raise GqlValidationError("Unknown directive `{}` used".format(name)) from e

    def __resolve_fragment_envs(self, fragment: qm.NamedFragment) -> t.Sequence[Env]:
        if fragment.name not in self.__fragment_calls:
            raise GqlValidationError("Unused fragment `{}`".format(fragment.name))

        envs = []

        for called_from in self.__fragment_calls[fragment.name]:
            if isinstance(called_from, qm.NamedFragment):
                for env in self.__resolve_fragment_envs(called_from):
                    envs.append(env)
            else:
                envs.append(self.__environments[called_from.name if called_from.name is not None else "!"])

        return envs


def validate(query: qm.Document, schema: s.Schema,
             vars_values: t.Mapping[str, PrimitiveType], op_to_run: t.Optional[str] = None) -> None:
    if op_to_run is None and len(query.operations) > 1:
        raise GqlValidationError("You must specify query to run for queries with many operations")

    if op_to_run is not None and op_to_run not in {op.name for op in query.operations}:
        raise GqlValidationError("Operation requested to run is not defined in the query")

    type_registry = schema.type_registry

    query_obj = type_registry.resolve_type(schema.query_object_name)
    if not isinstance(query_obj, gt.Object):
        raise RuntimeError("Query must be an object")

    mutation_obj = None
    if schema.mutation_object_name is not None:
        mutation_obj = type_registry.resolve_type(schema.mutation_object_name)
    if mutation_obj is not None and not isinstance(mutation_obj, gt.Object):
        raise RuntimeError("Mutation must be an object")

    pass_one = PassOne(type_registry, query_obj, mutation_obj)
    query.visit(pass_one)

    pass_two = PassTwo(pass_one.fragments, type_registry, query_obj, mutation_obj, vars_values, op_to_run)
    query.visit(pass_two)

    pass_three = PassThree(pass_two.environments, pass_two.fragment_calls, type_registry, query_obj, mutation_obj)
    query.visit(pass_three)
