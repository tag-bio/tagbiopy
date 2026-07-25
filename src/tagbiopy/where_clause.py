from tagbiopy import fundamentals
from tagbiopy.utils import log_exception

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


# Null test for a numeric column, as a 3-tuple: ('collection', 'variable', 'not null'). The engine's
# not-null test is a numeric-slice against the "NaN" sentinel (passed as a string through JSON); users
# write 'not null' and never see NaN. 'is null' (= NaN) is intentionally NOT offered: the FC engine
# hangs on a numeric = NaN test (not supported yet), so it's rejected rather than left to hang.
NULL_OPERATORS = {'not null': '!='}


def set_numeric_null(collection: str, variable: str, null_op: str):
    key = null_op.strip().lower() if isinstance(null_op, str) else null_op
    if key == 'is null':
        msg = ("'is null' is not supported by the FC engine yet (a numeric = NaN test hangs). "
               "Use 'not null'.")
        log_exception(NotImplementedError, msg)
    operator = NULL_OPERATORS.get(key)
    if operator is None:
        msg = (f'{null_op!r} invalid for a 3-tuple filter. Use {tuple(NULL_OPERATORS)}, '
               f"e.g. ('{collection}', '{variable}', 'not null').")
        log_exception(ValueError, msg)

    return fundamentals.NumericSlice(
        criterion=fundamentals.Numeric(collection, variable),
        operator=operator,
        value='NaN'
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
    elif len(_tuple) == 3:
        return set_numeric_null(*_tuple)
    elif len(_tuple) == 4:
        return set_numeric(*_tuple)
    else:
        msg = (f'{_tuple = }: filter tuple must have 2 (categorical), 3 (numeric null test), '
               f'or 4 (numeric comparison) elements.')
        log_exception(ValueError, msg)


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

