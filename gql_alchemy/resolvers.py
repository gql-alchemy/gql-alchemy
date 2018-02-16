import json
import typing as t

import gql_alchemy.schema as s
import gql_alchemy.types as gt


class Resolver:
    def __init__(self, for_type: t.Optional[str] = None) -> None:
        if for_type is not None:
            self.for_gql_type = for_type
        else:
            name = type(self).__name__
            if name.endswith("Resolver"):
                self.for_gql_type = name[:-8]
            else:
                self.for_gql_type = name


_scalar_types = {"Int", "Float", "String", "Boolean", "ID"}


class Introspection:
    def __init__(self, schema: s.Schema) -> None:
        self.__schema = schema
        self.__types_map = dict(((user_type.name, user_type) for user_type in schema.types))

        self.type_registry = schema.type_registry

    def types(self) -> t.Sequence[Resolver]:
        types: t.List[Resolver] = []

        for scalar_type in _scalar_types:
            resolver = self.search_type_resolver(scalar_type)

            if resolver is None:
                raise RuntimeError("Resolver expected here")

            types.append(resolver)

        for user_type in self.__types_map.values():
            resolver = self.search_type_resolver(user_type)

            if resolver is None:
                raise RuntimeError("Resolver expected here")

            types.append(resolver)

        return types

    def query_type(self) -> Resolver:
        res = self.search_type_resolver(self.__schema.query_object_name)

        if res is None:
            raise RuntimeError("Query must exists")

        return res

    def mutation_type(self) -> t.Optional[Resolver]:
        if self.__schema.mutation_object_name is None:
            return None

        res = self.search_type_resolver(self.__schema.mutation_object_name)

        if res is None:
            raise RuntimeError("Mutation object resolver expected here")

        return res

    def directives(self) -> t.Sequence[Resolver]:
        return [_DirectiveResolver(d, self) for d in self.__schema.directives]

    def get_type_resolver(self, type_ref: t.Union[str, gt.GqlType, s.TypeDefinition]) -> Resolver:
        resolver = self.search_type_resolver(type_ref)
        if resolver is None:
            raise RuntimeError("Can't resolve type", type_ref)
        return resolver

    def search_type_resolver(self, type_ref: t.Union[str, gt.GqlType, s.TypeDefinition]) -> t.Optional[Resolver]:
        if isinstance(type_ref, str):
            if type_ref in _scalar_types:
                return _ScalarTypeResolver(type_ref)
            if type_ref in self.__types_map:
                return _UserTypeResolver(self.__types_map[type_ref], self)
            return None
        if isinstance(type_ref, s.TypeDefinition):
            return _UserTypeResolver(type_ref, self)

        wrapper = gt.is_wrapper(type_ref)
        if wrapper is not None:
            return _WrapperTypeResolver(wrapper, self)

        return self.search_type_resolver(str(type_ref))

    def possible_types(self, interface: s.Interface) -> t.Sequence[Resolver]:
        possible_types = []

        for user_type in self.__schema.types:
            if isinstance(user_type, s.Object):
                if interface.name in user_type.interfaces:
                    resolver = self.get_type_resolver(user_type)
                    possible_types.append(resolver)

        return possible_types


class IntrospectionResolver(Resolver):
    def __init__(self, query_resolver: Resolver, introspection: Introspection) -> None:
        super().__init__(query_resolver.for_gql_type)
        self.__query_resolver = query_resolver
        self.__introspection = introspection

        self.f__schema = _SchemaResolver(introspection)

    def f__type(self, name: str) -> t.Optional[Resolver]:
        return self.__introspection.search_type_resolver(name)

    def __getattr__(self, item: str) -> t.Any:
        return getattr(self.__query_resolver, item)


class _SchemaResolver(Resolver):
    def __init__(self, introspection: Introspection) -> None:
        super().__init__("__Schema")
        self.__introspection = introspection

    def types(self) -> t.Sequence[Resolver]:
        return self.__introspection.types()

    def queryType(self) -> Resolver:
        return self.__introspection.query_type()

    def mutationType(self) -> t.Optional[Resolver]:
        return self.__introspection.mutation_type()

    def directives(self) -> t.Sequence[Resolver]:
        return self.__introspection.directives()


class _UserTypeResolver(Resolver):
    def __init__(self, schema_type: s.TypeDefinition, introspection: Introspection) -> None:
        super().__init__("__Type")
        self.__s_type = schema_type
        self.__introspection = introspection

        self.name = self.__s_type.name
        self.description = self.__s_type.description

    def kind(self) -> str:
        if isinstance(self.__s_type, s.Object):
            return "OBJECT"
        if isinstance(self.__s_type, s.Interface):
            return "INTERFACE"
        if isinstance(self.__s_type, s.Union):
            return "UNION"
        if isinstance(self.__s_type, s.Enum):
            return "ENUM"
        if isinstance(self.__s_type, s.InputObject):
            return "INPUT_OBJECT"
        raise RuntimeError("Object, Interface, Union, Enum or InputObject expected here")

    def fields(self, includeDeprecated: bool) -> t.Optional[t.Sequence[Resolver]]:
        if isinstance(self.__s_type, s.Interface):
            return [
                _FieldResolver(n, f, self.__introspection)
                for n, f in self.__s_type.fields.items()
                if not f.is_deprecated or includeDeprecated
            ]

        if isinstance(self.__s_type, s.Object):
            fields: t.List[Resolver] = []

            for int_name in self.__s_type.interfaces:
                int_resolver = t.cast(_UserTypeResolver, self.__introspection.search_type_resolver(int_name))
                int_fields = int_resolver.fields(includeDeprecated)
                if int_fields is None:
                    raise RuntimeError("Interface must have fields")
                for field in int_fields:
                    fields.append(field)

            for n, f in self.__s_type.fields.items():
                if not f.is_deprecated or includeDeprecated:
                    fields.append(_FieldResolver(n, f, self.__introspection))

            return fields

        return None

    def interfaces(self) -> t.Optional[t.Sequence[Resolver]]:
        if not isinstance(self.__s_type, s.Object):
            return None

        return [self.__introspection.get_type_resolver(name) for name in self.__s_type.interfaces]

    def possibleTypes(self) -> t.Optional[t.Sequence[Resolver]]:
        if isinstance(self.__s_type, s.Union):
            return [self.__introspection.get_type_resolver(t) for t in self.__s_type.possible_types]

        if isinstance(self.__s_type, s.Interface):
            self.__introspection.possible_types(self.__s_type)

        return None

    def enumValues(self, includeDeprecated: bool) -> t.Optional[t.Sequence[Resolver]]:
        if not isinstance(self.__s_type, s.Enum):
            return None

        return [_EnumValueResolver(v) for v in self.__s_type.values if not v.is_deprecated or includeDeprecated]

    def inputFields(self) -> t.Optional[t.Sequence[Resolver]]:
        if not isinstance(self.__s_type, s.InputObject):
            return None

        return [_InputFieldResolver(n, f, self.__introspection) for n, f in self.__s_type.input_fields.items()]

    def ofType(self) -> t.Optional[Resolver]:
        if not isinstance(self.__s_type, gt.List) or isinstance(self.__s_type, gt.NonNull):
            return None

        return self.__introspection.search_type_resolver(self.__s_type.of_type(self.__introspection.type_registry))


class _FieldResolver(Resolver):
    def __init__(self, name: str, field: s.Field, introspection: Introspection) -> None:
        super().__init__("__Field")

        self.__field = field
        self.__introspection = introspection

        self.name = name
        self.description = field.description
        self.isDeprecated = field.is_deprecated
        self.deprecationReason = field.deprecation_reason

    def args(self) -> t.List[Resolver]:
        return [_InputValueResolver(n, i, self.__introspection) for n, i in self.__field.args.items()]

    def type(self) -> Resolver:
        return self.__introspection.get_type_resolver(self.__field.type)


class _InputValueResolver(Resolver):
    def __init__(self, name: str, input_value: s.InputValue, introspection: Introspection) -> None:
        super().__init__("__InputValue")

        self.name = name
        self.description = input_value.description
        self.type = introspection.search_type_resolver(input_value.type)
        self.defaultValue = None if input_value.default_value is None else json.dumps(input_value.default_value)


class _InputFieldResolver(Resolver):
    def __init__(self, name: str, field: s.IoField, introspection: Introspection) -> None:
        super().__init__("__InputValue")

        self.name = name
        self.description = field.description
        self.type = introspection.search_type_resolver(field.type)
        self.defaultValue = None


class _ScalarTypeResolver(Resolver):
    def __init__(self, name: str) -> None:
        super().__init__("__Type")

        self.kind = "SCALAR"
        self.name = name
        self.description = "Standard type"
        self.interfaces = None
        self.possibleTypes = None
        self.inputFields = None
        self.ofType = None

    def fields(self, includeDeprecated: bool) -> None:
        return None

    def enumValues(self, includeDeprecated: bool) -> None:
        return None


class _WrapperTypeResolver(Resolver):
    def __init__(self, wrapper: gt.WrapperType, introspection: Introspection) -> None:
        super().__init__("__Type")

        self.__wrapper = wrapper
        self.__introspection = introspection

        self.kind = "LIST" if isinstance(wrapper, gt.List) else "NON_NULL"
        self.name = None
        self.description = None
        self.interfaces = None
        self.possibleTypes = None
        self.inputFields = None

    def fields(self, includeDeprecated: bool) -> None:
        return None

    def enumValues(self, includeDeprecated: bool) -> None:
        return None

    def ofType(self) -> Resolver:
        return self.__introspection.get_type_resolver(self.__wrapper.of_type(self.__introspection.type_registry))


class _EnumValueResolver(Resolver):
    def __init__(self, value: s.EnumValue) -> None:
        super().__init__("__EnumValue")
        self.name = value.name
        self.description = value.description
        self.isDeprecated = value.is_deprecated
        self.deprecationReason = value.deprecation_reason


class _DirectiveResolver(Resolver):
    def __init__(self, directive: s.Directive, introspection: Introspection) -> None:
        super().__init__("__Directive")
        self.__directive = directive
        self.__introspection = introspection

        self.name = directive.name
        self.description = directive.description
        self.locations = list(directive.locations)

    def args(self) -> t.Sequence[Resolver]:
        return [_InputValueResolver(n, v, self.__introspection) for n, v in self.__directive.args.items()]
