=====================================
GraphQL implementation for Python 3.6
=====================================

GraphQL ia a query language created by Facebook. This package
supports `the latest <http://facebook.github.io/graphql/October2016/>`_
on the moment of writing specification of the language.

-----------------------
Defining GraphQl Schema
-----------------------

To define schema use classes from ``gql_alchemy.schema``:

.. code:: python

    import gql_alchemy.schema as s
    import gql_alchemy.schema as s from gql_alchemy import Executor, Resolver,\
        GqlExecutionError, GqlValidationError, GqlParsingError

    schema = s.Schema(
        [
            # Use s.Object, s.Interface, s.InputObject
            # and s.Union to define types
            s.Object("Foo", {
                # Use s.Int, s.String, etc for scalar types
                "foo": s.String
            })
        ],

        # query type is the second parameter
        s.Object("QueryRoot", {
            # You can refer user defined types by names
            # Use s.NonNull to define non nullable type
            "foo": s.NonNull("Foo")
        }),

        # optional mutation type
        s.Object("MutationRoot", {
            # Example of full field definition
            "bar": s.Field(
                # Field type
                # Scalar can be non-null either
                s.NonNull(s.Boolean),
                {
                    "arg1": s.Int,
                    # full specification works like this
                    "arg2": s.InputValue(
                        # argument type
                        s.NonNull(s.Float),
                        # argument default (can be None)
                        1.2,
                        # Field description (reported in
                        # introspection response)
                        "Some float argument"
                    )
                },
                # Field description
                "Mutate bar",
                # is deprecated?
                True,
                # deprecation reason
                "Some deprecation reason"
            )
        })
    )

Schema object can be used to print schema (for documentation):

.. code:: python

    print(schema.format())

This will print:

.. code:: python

    type Foo
      foo(): String
    }

    type MutationRoot
      # Mutate bar
      #
      # Deprecated!
      # Some deprecation reason
      #
      # arg1: undocumented
      # arg2:
      #   Some float argument
      bar(arg1: Int, arg2: Float! = 1.2): Boolean!
    }

    type QueryRoot
      foo(): Foo!
    }

-----------------
Writing resolvers
-----------------

Now we need to write resolvers. Resolver for Foo type can be
written like that:

.. code:: python

    # Resolver understands which type it resolves by type
    # name. If you want different class name or few
    # classes to implement the same Resolver pass type
    # name as the first parameter.
    class FooResolver(Resolver):
        def __init__(self):
            super().__init__()

            # You can resolve fields just by assigning
            # their values to resolver attributes
            self.foo = "Hello :)"

Same resolver can be written as

.. code:: python

    class FooResolver(Resolver):
        def foo():
            return "Hello :)"

Example of resolver class with different name:

.. code:: python

    class SomeClassName(Resolver):
        def __init__(self):
            super().__init__("Foo")

        def foo():
            return "Hello :)"

Resolvers for query and mutation:

.. code:: python

    class QueryRootResolver(Resolver):
        # field without arguments can be plain attribute
        # or method
        def foo(self):
            # When field is user defined type - return
            # resolver
            return FooResolver()

    class MutationRootResolver(Resolver):
        def bar(self, arg1, arg2):
            return arg1 + arg2 > 10


-----------------
Executing queries
-----------------

Now we ready to execute queries

.. code:: python

    executor = Executor(
        schema,
        QueryRootResolver(),
        MutationRootResolver()
    )

    # run simple query
    try:
        # this will print
        # {"foo": {"foo": "Hello :)"}}
        print(json.dumps(executor.query("{foo{foo}}", {})))
    except GqlParsingError as e:
        print("Wrong query syntax: " + str(e))
    except GqlValidationError as e:
        print("Invalid query: " + str(e))
    except GqlExecutionError as e:
        print("Error in resolvers: " + str(e))

    # run query with variables
    # prints
    # {"bar": true}
    print(json.dumps(executor.query(
        "mutation ($a: Int){bar(arg1: $a, arg2: 5.0)}",
        {"a": 11}
    )))
