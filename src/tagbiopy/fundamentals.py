import inspect
import json
import logging
import reprlib
import sys

from typing import List, Union

from .logging import LOGGER_NAME
from .utils import check_arg_type, check_list_arg_types, extract_data_reference_type, get_typename, list_attributes, log_exception

logger = logging.getLogger(LOGGER_NAME)

__all__ = ['to_json', 'Categorical', 'Numeric', 'DataFrameCategorical', 'NumericMatrix', 'CategoricalBatch',
           'CategoricalCompound'
           ]


def to_json(variable_object):
    return variable_object.as_dict


class VariableBlock:

    def __hash__(self):
        return hash(f'{self!r}')

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def _get_dict(self):
        ret = {}
        for k in list_attributes(self):
            v = getattr(self, k)
            if v is None:
                logger.debug(f'{self!r}: Drop attribute {k} due to None value')
                continue
            ret.update({k: v})

        return ret

    def _get_data(self):
        return json.dumps(self._get_dict(), indent=2, default=to_json)

    def _get_full_dict(self):
        return json.loads(self._get_data())

    @property
    def operators(self) -> tuple:
        """List all operators, if applicable. If not, raise AttributeError.
        :return: tuple of str
        """
        this_class = inspect.getmro(self.__class__)[0]
        try:
            ret = getattr(this_class, '_operators')
        except AttributeError as e:
            msg = f'{e}. {self.__class__.__name__!r} variable type does not require operators'
            logger.info(msg, exc_info=True)
            raise AttributeError(msg)

        logger.debug(f'{self.__class__} operators: {ret}')

        return ret

    def _check(self, s):
        """Checks if passed operator is legit. If not, raise ValueError

        :param s: str, operator
        :return:
        """
        if s not in self.operators:
            msg = f'Invalid operator {s!r}. Choose from {self.operators!r}'
            log_exception(ValueError, msg)
        logger.debug(f'{self.__class__}: operator {s!r} is valid')
        return s


class VariableBlockImpl(VariableBlock):
    type_ = None

    def __init__(self):
        self.variable_type = self._set_type()
        self._as_dict = None

    def __repr__(self):
        logger.debug(f'{get_typename(self)!r} repr:')
        signature = inspect.signature(self.__init__)
        args = []
        for k in signature.parameters:
            v = getattr(self, k)
            logger.debug(f'  attribute {k!r}, value {v!r}')
            if v is None:
                continue
            args.append(f'{k}={v!r}')

        ret = f'{get_typename(self)}('
        ret += ', '.join(args)
        ret += ')'

        return ret

    def __str__(self):
        return f'{get_typename(self)}: ' + str(self.as_dict)

    @property
    def as_dict(self):
        if self._as_dict is None:
            self._as_dict = self._get_full_dict()

        return self._as_dict

    @property
    def data(self):
        return json.dumps(self.as_dict, indent=2, default=to_json)

    def _set_type(self):
        if self.type_ is None:
            msg = f'{get_typename(self)}: variable_type not defined'
            log_exception(NotImplementedError, msg)

        return self.type_


class SetBlock(VariableBlock):
    pass


class NumericBlock(VariableBlock):
    pass


class Categorical(VariableBlockImpl, SetBlock):
    type_ = 'categorical'

    def __init__(self, collection: str = None, variable: str = None):
        self.collection, self.variable = self._validate(collection, variable)
        super().__init__()

    @staticmethod
    def _validate(c, v):
        """Check validity of passed collection and variable.

        If collection is None, but variable is not, raise an exception.

        :param c: str, collection name
        :param v: str, variable name
        :return:
        """
        if c is None and v is not None:
            msg = f'Variable {v!r} not assigned to a collection.'
            log_exception(ValueError, msg)

        return c, v


class CategoricalBatch(VariableBlockImpl, SetBlock):
    type_ = 'categorical-batch'
    _operators = ('AND', 'OR')

    def __init__(self, collection: str, variables: List[str], operator: str):
        self.collection = check_arg_type(collection, str, allow_none=False)
        self.variables = check_list_arg_types(variables, str, allow_none=False)
        super().__init__()
        self.operator = self._check(operator)


class CategoricalCompound(VariableBlockImpl, SetBlock):
    type_ = 'categorical-compound'
    _operators = ('AND', 'OR')

    def __init__(self, criteria: List[SetBlock], operator: str):
        super().__init__()

        self.operator = self._check(operator)
        self.criteria = [CategoricalCompound._check_variable(v) for v in criteria]

    @staticmethod
    def _check_variable(v):
        logger.debug(f'Validate {v!r}')
        if isinstance(v, Categorical):
            if v.variable is None:
                msg = f'{v!r}: Variable cannot be None'
                log_exception(exception_class=ValueError, message=msg)
        elif isinstance(v, CategoricalBatch):
            if len(v.variables) == 0:
                msg = f'{v!r}: Requires at least one variable'
                log_exception(exception_class=ValueError, message=msg)
        elif isinstance(v, CategoricalCompound):
            for c in v.criteria:
                CategoricalCompound._check_variable(c)
        elif isinstance(v, NumericSlice):
            if v.criterion.variable is None:
                v.criterion.variable = v.criterion.collection
        else:
            msg = f'{v!r}, type {type(v)}: Invalid type. Please use {CATEGORICAL_COLLECTION_VARIABLE_TYPES}'
            log_exception(exception_class=ValueError, message=msg)
        return v


class NumericSlice(VariableBlockImpl, SetBlock):
    type_ = 'numeric-slice'
    _operators = ('<', '<=', '=', '!=', '>=', '>')

    def __init__(self, criterion: NumericBlock, operator: str, value: float = None, percentile: int = None):
        super().__init__()

        self.operator = self._check(operator)
        self.criterion = NumericSlice._check_variable(check_arg_type(criterion, NumericBlock))
        self.value, self.percentile = NumericSlice._validate(value, percentile)

    @staticmethod
    def _check_variable(v):
        if isinstance(v, Numeric):
            if v.variable is None:
                v.variable = v.collection
        return v

    @staticmethod
    def _validate(v, p):
        if v is None and p is None:
            msg = 'Specify either value or percentile'
            log_exception(ValueError, msg)

        if v is not None and p is not None:
            msg = 'You need to specify either the value or the percentile, but not both'
            log_exception(ValueError, msg)

        if v is not None:
            try:
                v = float(v)
            except ValueError as e:
                logger.debug(e, exc_info=True)
                raise

        if p is not None:
            try:
                p = int(p)
            except ValueError as e:
                logger.debug(e, exc_info=True)
                raise
            if p < 0 or p > 100:
                msg = f'Percentile value {p} invalid. Should be from [0, 100]'
                log_exception(ValueError, msg)

        return v, p

    @staticmethod
    def _verify(v):
        if isinstance(v, NumericBlock):
            return v
        else:
            msg = f"Invalid criterion type {get_typename(v)!r}. Expected 'Numeric'"
            log_exception(ValueError, msg)


class DataFrameBlock(VariableBlock):
    pass


class DataFrameImpl(VariableBlockImpl):

    def __init__(self, collection: str = None, variable: str = None, columns: List[str] = None):
        super().__init__()
        self.collection = check_arg_type(collection, str)
        self.variable = check_arg_type(variable, str)
        self.columns = check_list_arg_types(columns, str)


class DataFrameCategoricalBlock(DataFrameBlock):
    pass


class DataFrameCategorical(DataFrameImpl, DataFrameCategoricalBlock):
    type_ = 'categorical-matrix'

    def __init__(self, collection=None, variable=None, columns=None):
        super().__init__(collection, variable, columns)


class NumericMatrixBlock(DataFrameBlock):
    pass


class NumericMatrix(DataFrameImpl, NumericMatrixBlock):
    type_ = 'numeric-matrix'

    def __init__(self, collection=None, variable=None, columns=None):
        super().__init__(collection, variable, columns)


class Numeric(VariableBlockImpl, NumericBlock):
    type_ = 'numeric'

    def __init__(self, collection: str = None, variable: str = None):
        self.collection, self.variable = self._validate(collection, variable)
        super().__init__()

    @staticmethod
    def _validate(c, v):
        if c is None and v is not None:
            logger.debug(f'Variable {v} not assigned to a collection. Set to None')
            v = None

        c = check_arg_type(c, str)
        v = check_arg_type(v, str)

        return c, v


class NumericCompound(VariableBlockImpl, NumericBlock):
    type_ = 'numeric-compound'
    _operators = ('+', '-', '/', '*', '^')

    def __init__(self, criteria: List[NumericBlock], operator: str):
        super().__init__()

        self._check_list_length(criteria)
        self.operator = self._check(operator)
        self.criteria = [NumericCompound._check_variable(v) for v in criteria]

    def _check_list_length(self, lst: list):
        if isinstance(lst, list):
            if len(lst) == 2:
                return lst
            else:
                msg = f'{self!r}: criteria should contain two numeric variables. Passed {lst}'
                log_exception(ValueError, msg)
        else:
            msg = f'{self!r}: criteria should be a list of length two. Passed {lst}'
            log_exception(ValueError, msg)

    @staticmethod
    def _check_variable(v):
        logger.debug(f'Validate {v!r}')
        if isinstance(v, Numeric):
            if v.variable is None:
                msg = f'{v!r}: Variable cannot be None'
                log_exception(exception_class=ValueError, message=msg)
        else:
            msg = f'{v!r}, type {type(v)}: Invalid type. Please use {CATEGORICAL_COLLECTION_VARIABLE_TYPES}'
            log_exception(exception_class=ValueError, message=msg)
        return v


CATEGORICAL_COLLECTION_VARIABLE_TYPES = (Categorical, CategoricalBatch, CategoricalCompound, NumericSlice)
DATAFRAME_COLLECTION_VARIABLE_TYPES = (DataFrameCategorical, NumericMatrix)
NUMERIC_COLLECTION_VARIABLE_TYPES = (Numeric,)

ALL_COLLECTION_VARIABLE_TYPES = (
    Categorical, Numeric, CategoricalBatch, CategoricalCompound, NumericSlice,
    DataFrameCategorical, NumericMatrix
)

COMMON_COLLECTION_VARIABLE_TYPES = (Categorical, Numeric, CategoricalBatch, CategoricalCompound, NumericSlice)
COLLECTION_VARIABLE_TYPES = (Categorical, DataFrameCategorical, NumericMatrix, Numeric)
STR_COLLECTION_VARIABLE_TYPES = tuple([v.type_ for v in COLLECTION_VARIABLE_TYPES])


def variable_block_factory(variable_type: str) -> Union[ALL_COLLECTION_VARIABLE_TYPES]:
    """
    Turns str to variable_type object
        'categorical' to Categorical
        'data-frame-categorical' to DataFrameCategorical
        'data-frame-numeric' to NumericMatrix
        'numeric' to Numeric

    :param variable_type: str, one of
    :return:
    """

    try:
        return getattr(sys.modules[__name__], variable_type.title().replace('-', ''))
    except AttributeError as e:
        msg = f'Invalid variable type: {variable_type}'
        log_exception(exception_class=ValueError, message=msg, cause=e)


def _get_representation(instance):
    ret = f'{get_typename(instance)}('
    args = []
    for k in vars(instance):
        if k.startswith('_'):
            continue
        v = getattr(instance, k)
        if v is None:
            continue
        args.append(f'{k}={v!r}')
    ret += ', '.join(args)
    ret += ')'
    return ret


class _Collection(dict):
    type_ = None

    def __init__(self, **kwargs):
        super().__init__()
        self._kwargs = kwargs
        self.collection = kwargs.pop('collection')

        variable_type = extract_data_reference_type(kwargs, use_pop=True)
        self.variable_type = self._validate_type(variable_type)

        self.collection_size = kwargs.pop('collection-size')
        self._variable_block = variable_block_factory(self.variable_type)

    def __str__(self):
        ret = f'<{get_typename(self)} {self.collection!r} with {self.collection_size} declared and '
        ret += f'{len(self)} parsed variable'

        if len(self) == 0:
            ret += 's'
        elif len(self) == 1:
            ret += f' {list(self)[0]!r}'
        else:
            ret += f's: {reprlib.repr(sorted(list(self)))}'

        ret += '>'

        return ret

    def __repr__(self):
        return _get_representation(self)

    def __call__(self, variable=None):
        if variable is None or variable in self:
            return self._variable_block(collection=self.collection, variable=variable)
        else:
            msg = f'Collection {self.collection}: Invalid variable {variable}'
            log_exception(ValueError, msg)

    def _validate_type(self, variable_type):
        if self.type_ is None:
            msg = f'{self}: variable_type not defined'
            log_exception(ValueError, msg)

        if variable_type != self.type_:
            msg = f'{self}: Invalid variable_type'
            log_exception(ValueError, msg)

        return variable_type

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
            msg = f'{self!r}: requested variable None'
            log_exception(ValueError, msg)

        try:
            return self[variable]
        except KeyError as e:
            msg = f'Invalid variable {variable!r} for {self!r}'
            log_exception(ValueError, msg, cause=e)

    def validate_size(self, terminate=True):
        if self.collection_size != len(set(self)):
            msg = f'{self!r}: collection size {self.collection_size}, actual size {len(set(self))}'
            log_exception(RuntimeError, msg, terminate)
            return False
        else:
            msg = f'{self!r}: actual size equal to declared size {self.collection_size}'
            logger.info(msg)
            return True


class CategoricalCollection(_Collection):
    type_ = Categorical.type_

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.collection_entity_count = kwargs.pop('collection-entity-count')


class DataFrameCategoricalCollection(_Collection):
    type_ = DataFrameCategorical.type_


class NumericMatrixCollection(_Collection):
    type_ = NumericMatrix.type_


class NumericCollection(_Collection):
    type_ = Numeric.type_


COLLECTION_TYPES = (
    CategoricalCollection,
    DataFrameCategoricalCollection,
    NumericMatrixCollection,
    NumericCollection
)


class _Variable:
    type_ = None

    def __init__(self, **kwargs):
        self.variable_type = extract_data_reference_type(kwargs, use_pop=True)
        self.variable = kwargs.pop('variable')
        self.variable_size = kwargs.pop('variable-size')

    def __str__(self):
        return f'<{get_typename(self)} {self.variable!r}, variable-size {self.variable_size}>'

    def __repr__(self):
        return _get_representation(self)


class CategoricalVariable(_Variable):
    type_ = 'categorical'


class NumericVariable(_Variable):
    type_ = 'numeric'


VARIABLE_TYPES = (CategoricalVariable, NumericVariable)
STR_VARIABLE_TYPES = tuple([v.type_ for v in VARIABLE_TYPES])


def collection_factory(**kwargs):
    variable_type = extract_data_reference_type(kwargs)

    class_name = variable_type.title().replace('-', '') + 'Collection'

    try:
        return getattr(sys.modules[__name__], class_name)(**kwargs)
    except AttributeError as e:
        msg = f'Invalid collection type: {variable_type}'
        log_exception(exception_class=ValueError, message=msg, cause=e)


def variable_factory(**kwargs):
    variable_type = extract_data_reference_type(kwargs)
    class_name = variable_type.title().replace('-', '') + 'Variable'

    try:
        return getattr(sys.modules[__name__], class_name)(**kwargs)
    except AttributeError as e:
        msg = f'Invalid variable_type: {variable_type}'
        log_exception(exception_class=ValueError, message=msg, cause=e)
