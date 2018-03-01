from setuptools import setup, find_packages

setup(
    name="gql-alchemy",
    version="0.0.1",
    description="GraphQL implementation",
    long_description="Implementation for Facebook GraphQL based on http://facebook.github.io/graphql/October2016/ spec",
    url="https://github.com/gql-alchemy/gql-alchemy",
    author="Dmitry Maslennikov",
    author_email="maslennikovdm+gql-alchemy@gmail.com",
    license="MIT",
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 3.6',
    ],
    keywords="graphql",
    packages=find_packages(exclude=["tests"]),
    python_requires="~=3.6"
)
