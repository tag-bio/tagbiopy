from typing import Union


def check_arg_type(v, arg_type: Union[type, tuple], allow_none=True):
    """
    Check if v is of type arg_type.
    Raise ValueError if not.

    :param v: value
    :param arg_type: type or a tuple of types
    :param allow_none: bool
    :return: v if valid, otherwise raise ValueError
    """

    if allow_none:
        if v is None:
            return v
    else:
        if v is None:
            raise ValueError(f'arg {v!r} type {type(v)} invalid. Choose from {arg_type}')

    if isinstance(v, arg_type):
        return v
    else:
        raise ValueError(f'arg {v!r} type {type(v)} invalid. Choose from {arg_type}')
