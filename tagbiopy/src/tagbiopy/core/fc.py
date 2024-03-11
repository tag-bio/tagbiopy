import json
import logging

from typing import Union, Optional

import pandas as pd

from .api import QRequest, PRequest, SRequest
from .where_clause import check_boolean, set_collection, update
from ..utils import check_arg_type, content_to_dataframe
from ..fundamentals import block_factory, collection_factory
from ..fundamentals import (CategoricalBlock, NumericBlock, CategoricalCompoundBlock,
                            CategoricalMatrixBlock, NumericMatrixBlock)
from ..fundamentals import (CategoricalCollection, NumericCollection,
                            CategoricalMatrixCollection, NumericMatrixCollection)
from ..fundamentals import ALL_BLOCKS, ALL_BLOCKS_STR

BlockTypes = Union[CategoricalBlock, NumericBlock, CategoricalMatrixBlock, NumericMatrixBlock]
CollectionTypes = Union[CategoricalCollection, NumericCollection, CategoricalMatrixCollection, NumericMatrixCollection]
MixedTypes = Union[BlockTypes, CollectionTypes]

__all__ = ['FC']

logger = logging.getLogger(__name__)


class FC(QRequest):
    """Handles access to the back end and the data. Instantiated with the hostname.

    Properties:
        * _collections: private dictionary with keys "data_function_type" ("categorical",
          "numeric" or "data-frame-numeric") and variables dictionaries with key str collection
          name and value Collection instance
        * categorical_collections: _collections["categorical"]
        * summary: pd.DataFrame with three columns: name, variable type and number of variables
        * dataframe_numeric_collections: _collections["data-frame-numeric"]
        * entity_collection: Collection, with is_entity flag set to True
        * number_of_variables: int, number of variables, regardless of type
        * numeric_collections: _collections["numeric"

    Methods:
        * collections_to_dataframe: Take one or more collection and turn all their variables into a dataframe
        * get_collection: for a collection name and type, return Collection instance
        * variables_to_dataframe: for a particular collection, take variables and turn them into a dataframe

    Private methods:
        * _get_content: returns request.post.content
        * _prepare_analysis_variables: collateralizes analysis variables

    """

    def __init__(self, fc_name: str = None, host: str = None, api_key: str = None,
                 token: str = None) -> None:
        super().__init__(fc_name, host, api_key, token)

        # Private, to handle API '/q' requests with methods: "collection",
        # "variable" and "download".
        self._p_request = None
        self._s_request = None

        self._entity_collection = None
        self._summary = None

        # Used to build queries
        self.analysis_variables = None
        self.background = None

        # The following get populated through the collections property
        self.__collections = {}

        logger.debug(f'{self!r}: Initialized')

    def _prepare(self, variables: Union[BlockTypes, list[BlockTypes]]) -> list:
        """Prepare analysis variables by including the entity collection and sorting out
        situations if a single analysis variable was passed or a list of variables.

        param variables: VariableBlock or a list of VariableBlocks
        :return: dict
        """
        ret = [self.entity_collection().as_dict]
        if isinstance(variables, ALL_BLOCKS):
            ret.append(variables)
        elif isinstance(variables, list):
            ret.extend([check_arg_type(v, ALL_BLOCKS) for v in variables])
        else:
            msg = f'{self!r}: Illegal type {type(variables)} for analysis_variables.'
            msg += f' Should be one of or a list of {ALL_BLOCKS}'
            raise ValueError(msg)

        return ret

    @property
    def _collections(self) -> dict:
        """Parse all variables and assign them to their collections

        :return: dict of collections, with keys variable types, and values Collection instances
        """

        # If the private variable dictionary self.__collections is empty, then do the
        # parsing. In any case, return the dictionary

        if not any(self.__collections[k] for k in self.__collections):
            logger.debug(f'{self!r}: Initializing _collections: parsing')
            try:
                meta = self.q_collections['meta']
            except KeyError as e:
                logger.error('Could not find "meta" attribute in collections')
                raise e
            logger.debug(f'{self!r}: meta {meta}')

            try:
                entity_collection = meta['entity_collection']
            except KeyError as e:
                logger.debug('Could not identify "entity_collection" in collections "meta"')
                raise e
            logger.info(f'Entity collection: {entity_collection!r}')
            self.__collections['entity'] = entity_collection
            logger.debug(f"{self!r}: entity {self.__collections['entity']!r}")

            results = self.q_collections['results']
            logger.info(f'{self!r}: {len(results)} collections obtained')
            count = 0
            for i, kw in enumerate(results):
                values = kw['values']
                logger.debug(f'results[{i}]: {json.dumps(values, indent=2)}')

                collection = check_arg_type(values['collection'], str)

                data_function_type = values.get('data_reference_type')
                data_function_type = check_arg_type(data_function_type, str)

                self.__collections.setdefault(data_function_type, {})

                self.__collections[data_function_type].setdefault(
                    collection,
                    collection_factory(**values)
                )

                count += 1

            logger.info(f'{self!r}: {count} collections parsed')

        return self.__collections

    @property
    def available_collection_types(self) -> set:
        return set(self._collections.keys()).intersection(ALL_BLOCKS_STR)

    @property
    def df(self):
        """Used to initiate buildup of analysis variables and the background.

        Usage: self.df.select(*args).where(...) to prepare the query.
        Once the query is prepared, download is triggered by chaining with .run() which invokes
        self.to_dataframe method

        :return: self
        """
        self.analysis_variables = []
        self.background = {}
        logger.debug(f'{self}: Initialized analysis_variables and background')
        return self

    @property
    def entity_collection(self) -> CategoricalCollection:
        if self._entity_collection is None:
            name = str(self._collections['entity'])
            self._entity_collection = self.get_collection(CategoricalBlock(name))

        return self._entity_collection

    @property
    def info(self) -> dict:
        """Get provenance and version info for the FC.

        :return: dict of info returned from /s request
        """
        logger.info(f'{self!r}: get info')

        # perform the s query
        info = self.s_request.as_dict

        # replace time stamps
        info['data_timestamp'] = self.s_request.data_timestamp
        info['start_time'] = self.s_request.start_time

        return info

    @property
    def number_of_entities(self) -> int:
        return self.entity_collection.collection_size

    @property
    def p_request(self):
        if self._p_request is None:
            self._p_request = PRequest(
                host=self.host,
                fc_name=self.fc_name,
                api_key=self.api_key,
                token=self.token
            )
        return self._p_request

    @property
    def s_request(self):
        if self._s_request is None:
            self._s_request = SRequest(
                host=self.host,
                fc_name=self.fc_name,
                api_key=self.api_key,
                token=self.token
            )
        return self._s_request

    @property
    def summary(self) -> pd.DataFrame:
        """Summarizes the connected fc.

        The first row is guaranteed to be the entity collection, the rest are
        alphabetically ordered by type and then by name (in case of ties)

        :return: pd.DataFrame with three columns:
            collection name, collection type and the number of variables
        """
        logger.info(f'{self!r}: start summary')
        if self._summary is None:
            logger.info(f'{self!r}: No summary available, building')
            columns = ['Collection', 'Collection Type', 'Size', 'Entities without data']
            data = []
            logger.info(f'Available collection types: {self.available_collection_types}')
            for data_function_type in self.available_collection_types:
                logger.info(f'Work on {data_function_type!r} collections')
                for i, block in enumerate(self._collections[data_function_type]):
                    c_shell = block_factory(data_function_type)(block)
                    c_obj = self.get_collection(c_shell)

                    logger.debug(f'[{i}]: {c_obj!r}')
                    line = [
                        c_obj.collection,
                        c_obj.data_function_type,
                        c_obj.collection_size,
                        self.count_nans(c_obj)
                    ]
                    data.append(line)
                logger.info(f'  Parsed {len(self._collections[data_function_type])} {data_function_type} collections')

            _df = pd.DataFrame(columns=columns, data=data)

            entity_df = _df[_df['Collection'] == self.entity_collection.collection]
            rest_df = _df[_df['Collection'] != self.entity_collection.collection]
            rest_df = rest_df.sort_values(by=['Collection Type', 'Collection'])

            # Do not return the entity collection boolean column
            self._summary = pd.concat([entity_df, rest_df]).reset_index(drop=True)

            # Cast 'Entities without data' column to int
            self._summary['Entities without data'] = self._summary['Entities without data'].astype('Int64')

        logger.info(f'{self!r}: summary available, shape {self._summary.shape}')

        return self._summary

    def count_nans(self, collection: MixedTypes) -> Union[None, int, pd.DataFrame]:

        if isinstance(collection, BlockTypes):
            c_obj = self.get_collection(collection)
        elif isinstance(collection, CollectionTypes):
            c_obj = collection
        else:
            logger.debug(f'{collection!r}: Invalid type. Should be either {CategoricalBlock} or {NumericCollection}.')
            return

        if isinstance(c_obj, CategoricalCollection):
            return self.number_of_entities - c_obj.collection_entity_count

        if isinstance(collection, NumericBlock):
            variables = self.list_variables(collection)
            data = []
            for variable in variables:
                var_obj = c_obj.get_variable(variable)
                nan_count = self.number_of_entities - var_obj.variable_size
                data.append([variable, nan_count])

            _nan_df = pd.DataFrame(data=data, columns=['Variable', 'Entities without data'])
            _nan_df.columns.name = f'Collection: {collection.collection!r}'
            return _nan_df

        return

    def get_collection(self, collection: BlockTypes) -> CollectionTypes:
        collection = check_arg_type(collection, BlockTypes)

        try:
            self._collections[collection.type_]
        except KeyError as e:
            logger.error(f'{collection!r}: No such {collection.data_function_type} collection')
            raise e

        try:
            return self._collections[collection.type_][collection.collection]
        except KeyError as e:
            logger.error(f'{collection!r} not found among {collection.data_function_type} collections')
            raise e

    def get_data_timestamp(self):
        return self.s_request.data_timestamp

    def get_start_time(self):
        return self.s_request.start_time

    def list_collections(self, data_function_type):
        try:
            ret = [v for v in self._collections[data_function_type]]
        except KeyError as e:
            msg = f'Invalid data_function_type {data_function_type!r}.  ' \
                  f'Chose from {self.available_collection_types!r}'
            logger.error(msg)
            raise e
        return ret

    def list_protocols(self):
        return self.p_request.protocols

    def list_variables(self, collection: BlockTypes, as_generator=False):
        c = self.get_collection(collection)

        if len(c) == 0:
            logger.info(f'{c!r}: No variables assigned yet, parsing')
            variables_obj = self.get_variable_obj(analysis_variables=collection)
            c.add_variables(variables_obj)
        logger.info(f'{c!r}: {len(c)} variables available')

        if as_generator:
            return c.variables
        else:
            return sorted(c.variables)

    def select(self, *args: Union[str, tuple]):

        for i, arg in enumerate([v for v in args]):
            logger.debug(f'{i}: {arg}')
            if isinstance(arg, BlockTypes):
                self.analysis_variables.append(arg)
            elif isinstance(arg, str):
                # Go over all data_types and break as soon as the arg is found among the first data_function_type.
                # For ties, no luck, get the first.
                for collection_type in self.available_collection_types:
                    if arg in self._collections[collection_type]:
                        self.analysis_variables.append(
                            block_factory(data_function_type=collection_type)(arg)
                        )
                        break
                else:
                    raise ValueError(f'arg[{i}]: string arg {arg!r}, invalid data function type. Use {BlockTypes}.')

            elif isinstance(arg, tuple):
                # Tuples only make sense for numeric collections. For categorical collections we
                # report the variable or NaN; for numeric collection variable we get a separate column.
                # So default behavior is that for categorical variables we keep just collection names,
                # for numeric variables we specify both collection and variables
                collection, variable = arg
                for collection_type in self.available_collection_types:
                    if arg in self._collections[collection_type]:
                        self.analysis_variables.append(
                            block_factory(data_function_type=collection_type)(collection, variable)
                        )
                        break
                    else:
                        raise ValueError(f'arg[{i}]: tuple arg {arg!r}, invalid data function type. Use {BlockTypes}.')
            else:
                raise ValueError(f'arg[{i}]: arg {arg!r} should be a str, tuple or one of {BlockTypes}.')

        self.analysis_variables = list(set(self.analysis_variables)) or None

        return self

    def summarize_collection(self, collection: BlockTypes):

        logger.info(f'Summarize {collection!r}')
        c_obj = self.get_collection(collection)

        columns = ['Variable', 'Variable Type', 'Size']

        data = []
        j = None
        for i, variable_name in enumerate(self.list_variables(collection)):
            var_obj = c_obj.get_variable(variable_name)
            collection.variable = variable_name
            line = [variable_name, collection.data_function_type, var_obj.variable_size]
            data.append(line)
            if i % 1000000 == 0:
                logger.debug(f'  variable {i} completed')
            j = i
        else:
            logger.debug(f'  variable {j} completed, last variable')

        df = pd.DataFrame(columns=columns, data=data)
        if isinstance(collection, NumericBlock):
            nan_df = self.count_nans(collection)
            df = pd.concat([df, nan_df], axis=1)

        df.columns.name = collection.collection

        if isinstance(c_obj, CategoricalCollection):
            df.index.name = f'Number of entities: {c_obj.collection_entity_count}'

        # Clear variable for logging
        collection.variable = None
        logger.info(f'{collection!r}: variable summary shape: {df.shape}')

        # Column "Variable" may be duplicated due to the count_nans method
        return df.loc[:, ~df.columns.duplicated()]

    def to_dataframe(self,
                     analysis_variables: Union[BlockTypes, list[BlockTypes]],
                     background: Optional[Union[BlockTypes, list[BlockTypes]]] = None,
                     include_background: bool = False,
                     **kwargs) -> pd.DataFrame:
        """Takes categorical and numeric collections and turns them into a
        dataframe. The dataframe index is set to the entity_collection. The dataframe
        is then obtained with a single API '/q' call to method "download"

        :param analysis_variables: VariableBlock or a list of VariableBlocks
        :param background: None or a SetBlock
        :param include_background: bool, default False. If set to True, include the background as additional column
        :param kwargs: dict, to pass to pd.read_csv
        :return: pd.DataFrame, with collections as columns, and entity_collection set as index
        """
        logger.info(f'{self!r}: to_dataframe')

        if background is None and include_background is True:
            raise RuntimeError(f'{self!r}: Background should be included but is not.')

        logger.debug(f'{self!r}: analysis_variables {analysis_variables}')
        logger.debug(f'{self!r}: background {background}')

        _analysis_variables = self._prepare(analysis_variables)

        if include_background:
            _analysis_variables.append(background)

        content = self.get_content(analysis_variables=_analysis_variables, background=background)

        ret = content_to_dataframe(content=content, **kwargs)
        logger.info(f'{self!r}: dataframe shape {ret.shape}')
        return ret

    def run(self, **kwargs):

        if not self.analysis_variables and not self.background:
            raise RuntimeError(f'{self}: Neither analysis_variables nor background specified')

        # Drop duplicates, again. If lists empty, turn them to None to avoid triggering
        # HTTP 500 errors
        self.analysis_variables = list(set(self.analysis_variables)) or None
        self.background = self.background or None

        return self.to_dataframe(
            analysis_variables=self.analysis_variables,
            background=self.background,
            **kwargs
        )

    def where(self, *args):
        """
        Use to specify background. Used as self.df.select(Categorical, Numeric, etc.).where(*args).run()
        If starts with tuple, background needs to be empty.
        Example: if using a categorical collection, specify variable name as in
            self.df.select(Categorical('Cancer Type').where(
                ('Cancer Type', 'Endometrial Carcinoma'), 'OR',
                ('Cancer Type', 'Mature B-Cell Neoplasms'), 'OR',
                ('Cancer Type', 'Cholangiocarcinoma')
            )
            .where(('Cancer Type', 'Endometrial Carcinoma'), 'OR', ('Cancer Type', 'Mature B-Cell Neoplasms'))
        :param self:
        :param args: tuples and optional strings. Tuples represent categorical variables, strings can be 'OR' or 'AND'
        :return:
        """

        compound_operator = None
        first_index = 0
        # Check first argument:
        if isinstance(args[0], tuple):
            if len(args) % 2 == 0:
                raise RuntimeError('Passed even number of arguments')
            if self.background:
                raise RuntimeError(f'Cannot add first arg {args[0]!r} to background w/o a boolean operator first')

        elif isinstance(args[0], str):
            compound_operator = args[0]

            check_boolean(compound_operator)
            if not self.background:
                raise RuntimeError(f'Cannot specify boolean  operator {compound_operator!r} for undefined background')

            first_index = 1

        background = None
        operator_stack = []
        for i, arg in enumerate(args[first_index:]):
            if i == 0:
                background = set_collection(arg)
            else:
                if i % 2 == 0:
                    operator = operator_stack.pop()
                    background = update(background, operator, arg)
                else:
                    operator_stack.append(arg)

        if self.background:
            self.background = CategoricalCompoundBlock(
                criteria=[self.background, background],
                operator=compound_operator
            )
        else:
            self.background = background

        return self
