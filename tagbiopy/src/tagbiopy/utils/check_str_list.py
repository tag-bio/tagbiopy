
def check_str_lst(lst: list):
    """
    Check if every list element is a string.
    Raise ValueError if not.

    :param lst: list, presumably made of strings

    """

    for i, v in enumerate(lst):
        if isinstance(v, str):
            continue
        else:
            raise ValueError(f'[{i}]: {v!r} type {type(v)} invalid. Should be str')

    return lst
