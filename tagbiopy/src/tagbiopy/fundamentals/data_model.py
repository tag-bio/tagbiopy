import inspect
import json
import logging
import reprlib
import sys

from typing import Union

from tagbiopy.utils import check_arg_type, check_str_lst, list_attributes, to_json

logger = logging.getLogger(__name__)

__all__ = [
    'block_factory', 'collection_factory',
    'CategoricalBlock', 'CategoricalBatchBlock', 'CategoricalCompoundBlock', 'CategoricalMatrixBlock',
    'NumericBlock', 'NumericSliceBlock', 'NumericMatrixBlock',
    'ALL_BLOCKS', 'ALL_BLOCKS_STR',
    'COLLECTIONS', 'VARIABLES',
    'CategoricalCollection', 'CategoricalMatrixCollection',
    'NumericCollection', 'NumericMatrixCollection'
]

_CATEGORICAL = [
    'categorical', 'categorical-batch', 'categorical-compound', 'numeric-slice'
]


def _get_repr(instance):
    args = []
    for k in list_attributes(instance):
        v = getattr(instance, k)
        if v is None:
            continue
        args.append(f'{k}={v!r}')

    ret = f'{instance.__class__.__name__}('
    ret += ', '.join(args)
    ret += ')'

    return ret


class _VariableBlock:
    """
    Parent class for all block data structures.
    """
    type_ = None

    def __init__(self):
        self.data_function_type = self._set_type()
        self._as_dict = None

    def __repr__(self):
        return _get_repr(self)

    def __str__(self):
        return f'{self.__class__.__name__}: ' + str(self.as_dict)

    def __hash__(self):
        return hash(f'{self!r}')

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def _get_data(self):
        return json.dumps(self._get_dict(), indent=2, default=to_json)

    def _get_dict(self):
        ret = {}
        for k in list_attributes(self):
            v = getattr(self, k)
            if v is None:
                continue
            ret.update({k: v})

        return ret

    def _get_full_dict(self):
        return json.loads(self._get_data())

    def _set_type(self):
        if self.type_ is None:
            msg = f'Invalid data_function_type for {self!r}'
            raise ValueError(msg)
        return self.type_

    @property
    def as_dict(self):
        if self._as_dict is None:
            self._as_dict = self._get_full_dict()
        return self._as_dict

    @property
    def data(self):
        return json.dumps(self.as_dict, indent=2, default=to_json)

    @property
    def operators(self) -> tuple:
        """List all operators, if applicable. If not, raise AttributeError.
        :return: tuple of str
        """
        this_class = inspect.getmro(self.__class__)[0]
        try:
            ret = getattr(this_class, '_operators')
        except AttributeError as e:
            logger.error(f'{self.__class__.__name__!r} variable type does not require operators')
            raise e

        logger.debug(f'{self.__class__} operators: {ret}')

        return ret

    def _check(self, s):
        """Checks if passed operator is legit. If not, raise ValueError

        :param s: str, operator
        :return:
        """
        if s not in self.operators:
            msg = f'{self!r}: Invalid operator {s!r}. Choose from {self.operators!r}'
            raise ValueError(msg)
        logger.debug(f'{self!r}: operator {s!r} is valid')
        return s


class CategoricalBlock(_VariableBlock):
    type_ = 'categorical'

    def __init__(self, collection: str = None, variable: str = None):
        self.collection = check_arg_type(collection, str, allow_none=False)
        self.variable = check_arg_type(variable, str, allow_none=True)

        super().__init__()


class CategoricalBatchBlock(_VariableBlock):
    type_ = 'categorical-batch'
    _operators = ('AND', 'OR')

    def __init__(self, collection: str, variables: list, operator: str):
        self.collection = check_arg_type(collection, str, allow_none=False)
        self.variables = check_str_lst(variables)
        self.operator = self._check(operator)

        super().__init__()


class CategoricalCompoundBlock(_VariableBlock):
    type_ = 'categorical-compound'
    _operators = ('AND', 'OR')

    def __init__(self, criteria: list, operator: str):
        self.operator = self._check(operator)
        self.criteria = [CategoricalCompoundBlock._check_variable(v) for v in criteria]

        super().__init__()

    @staticmethod
    def _check_variable(v):
        logger.debug(f'Validate {v!r}')
        if isinstance(v, CategoricalBlock):
            if v.variable is None:
                raise ValueError(f'{v!r}: Variable cannot be None')
        elif isinstance(v, CategoricalBatchBlock):
            if len(v.variables) == 0:
                raise ValueError(f'{v!r}: Requires at least one variable')
        elif isinstance(v, CategoricalCompoundBlock):
            for c in v.criteria:
                CategoricalCompoundBlock._check_variable(c)
        elif isinstance(v, NumericSliceBlock):
            if v.criterion.variable is None:
                v.criterion.variable = v.criterion.collection
        else:
            raise ValueError(f'{v!r}, type {type(v)}: Invalid type, use {_CATEGORICAL}')
        return v


class NumericBlock(_VariableBlock):
    type_ = 'numeric'

    def __init__(self, collection: str = None, variable: str = None):
        self.collection = check_arg_type(collection, str, allow_none=False)
        self.variable = check_arg_type(variable, str, allow_none=True)
        super().__init__()


class NumericCompoundBlock(_VariableBlock):
    type_ = 'numeric-compound'
    _operators = ('+', '-', '/', '*', '^')

    def __init__(self, criteria: list, operator: str):
        self._check_list_length(criteria)
        self.operator = self._check(operator)
        self.criteria = [NumericCompoundBlock._check_variable(v) for v in criteria]

        super().__init__()

    def _check_list_length(self, lst: list):
        if isinstance(lst, list):
            if len(lst) == 2:
                return lst
            else:
                raise ValueError(f'{self!r}: criteria should contain two numeric variables. Passed {lst}')

    @staticmethod
    def _check_variable(v):
        logger.debug(f'Validate {v!r}')
        if isinstance(v, NumericBlock):
            if v.variable is None:
                raise ValueError(f'{v!r}: Variable cannot be None')
        else:
            raise ValueError(f'{v!r}, type {type(v)}: Invalid type, use {_CATEGORICAL}')
        return v


class NumericSliceBlock(_VariableBlock):
    type_ = 'numeric-slice'
    _operators = ('<', '<=', '=', '!=', '>=', '>')

    def __init__(self, criterion: NumericBlock, operator: str, value: float = None, percentile: int = None):
        self.operator = self._check(operator)
        self.criterion = NumericSliceBlock._check_variable(check_arg_type(criterion, NumericBlock))
        self.value, self.percentile = NumericSliceBlock._validate(value, percentile)

        super().__init__()

    @staticmethod
    def _check_variable(v):
        if isinstance(v, NumericBlock):
            if v.variable is None:
                v.variable = v.collection
        else:
            raise ValueError(f'{v!r}, type {type(v)}: Invalid type, use Numeric')

        return v

    @staticmethod
    def _validate(v, p):
        if v is None:
            if p is None:
                raise ValueError(f'Specify either value or percentile')
            else:
                p = int(p)
                if p < 0 or p > 100:
                    raise ValueError(f'Percentile value {p} invalid. Should be from [0, 100]')
        else:
            if p is None:
                v = float(v)
            else:
                raise ValueError(f'Specify either value or percentile, but not both')

        return v, p

    @staticmethod
    def _verify(v):
        if isinstance(v, NumericBlock):
            return v
        else:
            raise ValueError(f"Invalid criterion type {type(v).__name__!r}. Expected 'Numeric'")


class _MatrixBlock(_VariableBlock):

    def __init__(self, collection: str = None, variable: str = None, columns: list = None):
        self.collection = check_arg_type(collection, str, allow_none=False)
        self.variable = check_arg_type(variable, str, allow_none=True)
        if columns is None:
            self.columns = None
        else:
            if isinstance(columns, str):
                self.columns = check_str_lst([columns])
            elif isinstance(columns, list):
                self.columns = check_str_lst(columns)
            else:
                raise ValueError(f'{columns!r}: Invalid type, should be str or list')

        super().__init__()


class CategoricalMatrixBlock(_MatrixBlock):
    type_ = 'categorical-matrix'


class NumericMatrixBlock(_MatrixBlock):
    type_ = 'numeric-matrix'


ALL_BLOCKS = (
    CategoricalBlock, CategoricalBatchBlock, CategoricalCompoundBlock,
    NumericBlock, NumericSliceBlock,
    CategoricalMatrixBlock, NumericMatrixBlock
)

ALL_BLOCKS_STR = tuple([v.type_ for v in ALL_BLOCKS])


def block_factory(data_function_type: str) -> Union[ALL_BLOCKS_STR]:
    """
    Turns str to data_function_type object
        'categorical' to CategoricalBlock
        'categorical-matrix' to CategoricalMatrixBlock
        'numeric-matrix' to NumericMatrixBlock
        'numeric' to NumericBlock, etc

    :param data_function_type: str, one of
    :return: object of ALL_BLOCKS type
    """
    name = data_function_type.title().replace('-', '') + 'Block'
    try:
        return getattr(sys.modules[__name__], name)
    except AttributeError as e:
        logger.error(f'Invalid block type: {data_function_type!r}. Should be one of {ALL_BLOCKS_STR}')
        raise e


class _Collection(dict):
    type_ = None

    def __init__(self, **kwargs):
        super().__init__()
        self._kwargs = kwargs
        self.collection = kwargs.pop('collection')

        data_function_type = kwargs.pop('data_reference_type')
        self.data_function_type = self._validate_type(data_function_type)

        self.collection_size = kwargs.pop('collection-size')
        self._variable_block = block_factory(self.data_function_type)

    def __str__(self):
        n = len(self)
        ret = f'<{self.__class__.__name__} {self.collection!r} with {self.collection_size} declared and '
        ret += f'{n} parsed variable'

        if n == 0:
            ret += 's'
        elif n == 1:
            ret += f' {list(self)[0]!r}'
        else:
            ret += f's: {reprlib.repr(sorted(list(self)))}'

        ret += '>'

        return ret

    def __repr__(self):
        return _get_repr(self)

    def __call__(self, variable=None):
        if variable is None or variable in self:
            return self._variable_block(collection=self.collection, variable=variable)
        else:
            raise ValueError(f'Collection {self.collection}: Invalid variable {variable}')

    def _validate_type(self, data_function_type):
        if self.type_ is None:
            raise ValueError(f'{self}: data_function_type not defined')

        if data_function_type != self.type_:
            raise ValueError(f'{self}: Invalid data_function_type')

        return data_function_type

    @property
    def variables(self):
        """
        :return: generator of all variables
        """
        return (v for v in self)

    def add_variables(self, variable_obj):
        try:
            results = variable_obj['results']
        except KeyError as e:
            msg = f'{e}\nInvalid variable_obj, require "results" key: {variable_obj}'
            logger.error(msg, exc_info=True)
            raise

        for var_block in results:
            values = var_block['values']
            variable = values['variable']
            self.update({variable: variable_factory(**values)})

    def get_variable(self, variable: str):
        if variable is None:
            raise ValueError(f'{self!r}: requested variable None')

        try:
            return self[variable]
        except KeyError as e:
            logger.error(f'Invalid variable {variable!r} for {self!r}')
            raise e

    def validate_size(self):
        if self.collection_size != len(set(self)):
            raise RuntimeError(f'{self!r}: collection size {self.collection_size}, actual size {len(set(self))}')
        else:
            logger.debug(f'{self!r}: actual size equal to declared size {self.collection_size}')
            return True


class CategoricalCollection(_Collection):
    type_ = CategoricalBlock.type_

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.collection_entity_count = kwargs.pop('collection-entity-count')


class CategoricalMatrixCollection(_Collection):
    type_ = CategoricalMatrixBlock.type_


class NumericMatrixCollection(_Collection):
    type_ = NumericMatrixBlock.type_


class NumericCollection(_Collection):
    type_ = NumericBlock.type_


COLLECTIONS = (CategoricalCollection, CategoricalMatrixCollection, NumericMatrixCollection, NumericCollection)


class _Variable:
    type_ = None

    def __init__(self, **kwargs):
        self.data_function_type = kwargs.pop('data_reference_type')
        self.variable = kwargs.pop('variable')
        self.variable_size = kwargs.pop('variable-size')

    def __str__(self):
        return f'<{self.__class__.__name__} {self.variable!r}, variable-size {self.variable_size}>'

    def __repr__(self):
        return _get_repr(self)


class CategoricalVariable(_Variable):
    type_ = 'categorical'


class NumericVariable(_Variable):
    type_ = 'numeric'


class CategoricalMatrixVariable(_Variable):
    type_ = 'categorical-matrix'


class NumericMatrixVariable(_Variable):
    type_ = 'numeric-matrix'


VARIABLES = (CategoricalVariable, NumericVariable, CategoricalMatrixVariable, NumericMatrixVariable)


# Factory functions


def collection_factory(**kwargs):
    data_function_type = kwargs.get('data_reference_type')

    class_name = data_function_type.title().replace('-', '') + 'Collection'

    try:
        return getattr(sys.modules[__name__], class_name)(**kwargs)
    except AttributeError as e:
        logger.error(f'Invalid collection type: {data_function_type!r}. Should be one of {COLLECTIONS}')
        raise e


def variable_factory(**kwargs):
    data_function_type = kwargs.pop('data_reference_type')
    class_name = data_function_type.title().replace('-', '') + 'Variable'

    try:
        return getattr(sys.modules[__name__], class_name)(**kwargs)
    except AttributeError as e:
        logger.error(f'Invalid variable type: {data_function_type!r}. Should be one of {VARIABLES}')
        raise e
