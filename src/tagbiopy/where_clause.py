from fcpy import fundamentals
from fcpy.utils import log_exception

BOOLEAN_OPERATORS = ('OR', 'AND')


def check_boolean(s):
    if s not in BOOLEAN_OPERATORS:
        msg = f'Operator {s!r} invalid. Please choose from {BOOLEAN_OPERATORS}'
        log_exception(RuntimeError, msg)


def set_categorical(collection: str, variable: str):
    return fundamentals.Categorical(collection, variable)


def set_categorical_batch(collection: str, variables: list):
    return fundamentals.CategoricalBatch(collection, variables, operator='OR')


def set_numeric(collection: str, variable: str, operator: str, value: float):
    if not operator and not value:
        msg = f'{collection = }, {variable = } requires both operator and value.'
        log_exception(ValueError, msg)

    return fundamentals.NumericSlice(
        criterion=fundamentals.Numeric(collection, variable),
        operator=operator,
        value=value
    )


def set_collection(_tuple):
    if len(_tuple) == 2:
        collection, variable = _tuple
        if isinstance(variable, str):
            return set_categorical(collection, variable)
        elif isinstance(variable, list):
            return set_categorical_batch(collection, variable)
        else:
            msg = f'{variable = } invalid type. Should be str or list'
            log_exception(TypeError, msg)
    elif len(_tuple) == 4:
        return set_numeric(*_tuple)


def update(background, operator, _tuple):
    if not background:
        msg = f'{operator = }, {_tuple = }: update requires background. Currently not set.'
        log_exception(RuntimeError, msg)

    return fundamentals.CategoricalCompound(
        criteria=[
            background,
            set_collection(_tuple)
        ],
        operator=operator
    )

