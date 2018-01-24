def add_if_not_empty(dict, name, list):
    if len(list) > 0:
        dict[name] = [i.to_dict() for i in list]


def add_if_not_none(dict, name, value):
    if value is not None:
        dict[name] = value
