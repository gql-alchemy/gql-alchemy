import typing as t

import gql_alchemy.gql_query_model as qm
import gql_alchemy.gql_schema as s
from .gql_errors import GqlValidationError
from .utils import PrimitiveType


def validate(query: qm.Document, schema: s.Schema,
             variables: t.Mapping[str, PrimitiveType], op_to_run: t.Optional[str] = None) -> None:
    if op_to_run is None and len(query.operations) > 1:
        raise GqlValidationError("You must specify query to run for queryes with many operations")

    if op_to_run is not None and op_to_run not in {op.name for op in query.operations}:
        raise GqlValidationError("Operation requested to run is not defined in the query")

    for op in query.operations:
        running = op_to_run is None or op_to_run == op.name
        validate_operation(op, query, schema, variables if running else None)


def validate_operation(op: qm.Operation, query: qm.Document, schema: s.Schema,
                       variables: t.Optional[t.Mapping[str, PrimitiveType]]) -> None:
    mutation = isinstance(op, qm.Mutation)

    query_object = schema.query

    if mutation:
        if schema.mutation is None:
            raise GqlValidationError("No mutation operations defined")

        query_object = schema.mutation

    for sel in op.selections:
        if isinstance(sel, qm.FieldSelection):
            validate_field_selection(sel, query_object)


def validate_field_selection(field_selection: qm.FieldSelection, from_type: s.GqlSelectableType) -> None:
    if field_selection.name not in from_type.fields:
        raise GqlValidationError(
            "Selecting undefined field `{}` from {} type".format(field_selection.name, from_type.name)
        )

    field_definition = from_type.fields[field_selection.name]

    validate_selection_args(field_selection.arguments, field_definition.args)

    field_type = from_type.field_type(field_selection.name)

    unwrapped_field_type = field_type

    if isinstance(field_type, s.GqlWrappedType):
        unwrapped_field_type = field_type.unwrap()

    if isinstance(unwrapped_field_type, s.GqlSpreadableType):
        if len(field_selection.selections) == 0:
            raise GqlValidationError("Spreadable type (interface, class, union) must be selected with fields")

        for sel in field_selection.selections:
            if isinstance(sel, qm.FieldSelection):
                if not isinstance(unwrapped_field_type, s.GqlSelectableType):
                    raise GqlValidationError(
                        "Direct field selection possible only on selectable type (interface, class), but not on union. "
                        "On union use inline spread with type or fragment selection."
                    )
                validate_field_selection(sel, unwrapped_field_type)
    else:
        if len(field_selection.selections) > 0:
            raise GqlValidationError("Selecting fields for type without fields")


def validate_selection_args(selection_args: t.Sequence[qm.Argument],
                            args_definition: t.Optional[t.Mapping[str, s.InputValue]]):
    if args_definition is None:
        if len(selection_args) > 0:
            raise GqlValidationError("Field does not support args")
        return

    required_args = set()
    for arg_name, arg_def in args_definition.items():
        if arg_def.default_value is None:
            required_args.add(arg_name)
    for sel_arg in selection_args:
        required_args.remove(sel_arg.name)
    if len(required_args) > 0:
        raise GqlValidationError("Selection miss required arguments: {}".format(", ".join(required_args)))

    for sel_arg in selection_args:
        if sel_arg.name not in args_definition:
            raise GqlValidationError("Undefined argument: {}".format(sel_arg.name))
