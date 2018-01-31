import typing as t

PrimitiveType = t.Union[None, bool, int, float, str, t.Sequence['PrimitiveType'], t.Mapping[str, 'PrimitiveType']]


class PrimitiveSerializable:
    def to_primitive(self) -> PrimitiveType:
        raise NotImplementedError()


def add_if_not_empty(mapping: t.MutableMapping[str, PrimitiveType],
                     name: str, values: t.Optional[t.Sequence[PrimitiveSerializable]]) -> None:
    if values is not None and len(values) > 0:
        mapping[name] = [i.to_primitive() for i in values]


def add_if_not_none(mapping: t.MutableMapping[str, PrimitiveType], name: str, value: PrimitiveType) -> None:
    if value is not None:
        mapping[name] = value


__all__ = ["PrimitiveType", "PrimitiveSerializable", "add_if_not_empty", "add_if_not_none"]
