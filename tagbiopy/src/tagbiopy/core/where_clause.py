from tagbiopy.fundamentals import CategoricalBlock, CategoricalBatchBlock, CategoricalCompoundBlock
from tagbiopy.fundamentals import NumericBlock, NumericSliceBlock


BOOLEAN_OPERATORS = ('OR', 'AND')


def check_boolean(s):
    if s not in BOOLEAN_OPERATORS:
        raise ValueError(f'Operator {s!r} invalid. Please choose from {BOOLEAN_OPERATORS}')


def _set_categorical_block(collection: str, variable: str):
    return CategoricalBlock(collection, variable)


def _set_categorical_batch_block(collection: str, variables: list):
    return CategoricalBatchBlock(collection, variables, operator='OR')


def _set_numeric_block(collection: str, variable: str, operator: str, value: float):
    if not operator and not value:
        raise ValueError(f'{collection = }, {variable = } requires both operator and value.')

    return NumericSliceBlock(
        criterion=NumericBlock(collection, variable),
        operator=operator,
        value=value
    )


def set_collection(_tuple):
    if len(_tuple) == 2:
        collection, variable = _tuple
        if isinstance(variable, str):
            return _set_categorical_block(collection, variable)
        elif isinstance(variable, list):
            return _set_categorical_batch_block(collection, variable)
        else:
            raise ValueError(f'Invalid type for {variable!r}: {type(variable)}. Should be str or list')
    elif len(_tuple) == 4:
        return _set_numeric_block(*_tuple)


def update(background, operator, _tuple):
    if not background:
        raise ValueError(f'Background not set for {_tuple!r}, operator {operator!r}.')

    return CategoricalCompoundBlock(
        criteria=[
            background,
            set_collection(_tuple)
        ],
        operator=operator
    )

