from typing import Union, Sequence, Mapping, MutableMapping, Optional

PrimitiveType = Union[None, bool, int, float, str, Sequence['PrimitiveType'], Mapping[str, 'PrimitiveType']]


class PrimitiveSerializable:
    def to_primitive(self) -> PrimitiveType:
        pass


def add_if_not_empty(mapping: MutableMapping[str, PrimitiveType],
                     name: str, values: Optional[Sequence[PrimitiveSerializable]]):
    if values is not None and len(values) > 0:
        mapping[name] = [i.to_primitive() for i in values]


def add_if_not_none(mapping: MutableMapping[str, PrimitiveType], name: str, value: PrimitiveType):
    if value is not None:
        mapping[name] = value
