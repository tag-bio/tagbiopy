import json
import re

from typing import List, Union, Optional

import pandas as pd

from tagbiopy import logger
from tagbiopy import fundamentals
from tagbiopy.request import QRequest, PRequest, SRequest, HEADER_DELIMITER
from tagbiopy.utils import check_arg_type, content_to_dataframe, drop_retired_arguments, extract_data_reference_type, log_exception
from .where_clause import check_boolean, set_collection, update

# collection queries return at most 50,000 collections unless told otherwise
COLLECTION_LIMIT = 1000000000


def _flux_name(n):
    """Compound names ({"operator": " | ", "names": [...]}) display as their parts joined by the operator."""
    if isinstance(n, dict) and 'names' in n:
        return n.get('operator', '').join(_flux_name(x) for x in n['names'])
    return '' if n is None else str(n)

VariableBlockTypes = Union[fundamentals.VariableBlock, List[fundamentals.VariableBlock]]
CollectionDataFunctionTypes = Union[fundamentals.COLLECTION_DATA_FUNCTION_TYPES]
CollectionTypes = Union[fundamentals.COLLECTION_TYPES]
AllCollectionTypes = Union[CollectionDataFunctionTypes, CollectionTypes]


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
        logger.info(f'{self.__class__}: Initialize')
        super().__init__(fc_name, host, api_key, token)

        # Private, to handle API '/q' requests with methods: "collection",
        # "variable" and "download".
        self._p_request = None
        self._s_request = None
        self._t_request = None

        self._entity_collection = None
        self._summary = None

        # Used to build queries
        self.analysis_variables = None
        self.background = None

        # The following get populated through the collections property
        self.__collections = {}

        logger.info(f'{self!r}: Initialized')

    def _prepare(self, variables: VariableBlockTypes) -> list:
        """Prepare analysis variables by including the entity collection and sorting out
        situations if a single analysis variable was passed or a list of variables.

        param variables: VariableBlock or a list of VariableBlocks
        :return: dict
        """
        entity = self._entity_reference()
        ret = [entity.as_dict] if entity is not None else []
        if isinstance(variables, fundamentals.ALL_COLLECTION_DATA_FUNCTION_TYPES):
            ret.append(variables)
        elif isinstance(variables, list):
            ret.extend([check_arg_type(v, fundamentals.VariableBlock) for v in variables])
        else:
            msg = f'{self!r}: Illegal analysis_variables type {type(variables)}.'
            msg += f' Should be one of or a list of {fundamentals.ALL_COLLECTION_DATA_FUNCTION_TYPES}'
            log_exception(exception_class=ValueError, message=msg)

        return ret

    @property
    def _collections(self) -> dict:
        """Parse all variables and assign them to their collections

        :return: dict of collections, with keys variable types, and values Collection instances
        """

        # If the private variable dictionary self.__collections is empty, then do the
        # parsing. In any case, return the dictionary

        if not any(self.__collections[k] for k in self.__collections):
            logger.info(f'{self!r}: Initializing _collections: parsing')
            try:
                meta = self.q_collections['meta']
            except KeyError as e:
                logger.debug('Could not find "meta" attribute in collections')
                logger.info(e, exc_info=True)
                raise
            logger.debug(f'{self!r}: meta {meta}')

            try:
                entity_collection = meta['entity_collection']
            except KeyError as e:
                logger.debug('Could not identify "entity_collection" in collections "meta"')
                logger.info(e, exc_info=True)
                raise
            logger.info(f'Entity collection: {entity_collection!r}')
            self.__collections['entity'] = entity_collection
            logger.debug(f"{self!r}: entity {self.__collections['entity']!r}")

            results = self.q_collections['results']
            logger.info(f'{self!r}: {len(results)} collections obtained')
            count = 0
            for i, kw in enumerate(results):
                values = kw['values']
                msg_values = f'results[{i}]: {json.dumps(values, indent=2)}'

                collection = check_arg_type(values['collection'], str)

                data_function_type = extract_data_reference_type(values)
                data_function_type = check_arg_type(data_function_type, str)

                self.__collections.setdefault(data_function_type, {})

                try:
                    self.__collections[data_function_type].setdefault(
                        collection,
                        fundamentals.collection_factory(**values)
                    )
                except ValueError as e:
                    msg = f'{e}. {msg_values}'
                    logger.info(msg, exc_info=True)
                    continue
                count += 1

            logger.info(f'{self!r}: {count} collections parsed')

        return self.__collections

    @property
    def available_collection_types(self) -> set:
        return set(self._collections.keys()).intersection(fundamentals.STR_COLLECTION_DATA_FUNCTION_TYPES)

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
        self._head = None
        logger.debug(f'{self}: Initialized {self.analysis_variables = }, {self.background = }')
        return self

    @property
    def entity_collection(self) -> fundamentals.CategoricalCollection:
        if self._entity_collection is None:
            name = str(self._collections['entity'])
            self._entity_collection = self.get_collection(fundamentals.Categorical(name))

        return self._entity_collection

    def _entity_reference(self):
        """The entity-ID collection as a data function, or None when the FC's entity ID isn't one of its collections
        (downloads still carry the entity ID column)."""
        if str(self._collections['entity']) not in self._collections.get(fundamentals.Categorical.type_, {}):
            logger.info(f'{self!r}: entity ID is not a collection; downloading without it as a selected column')
            return None
        return self.entity_collection()

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
    def t_request(self):
        if self._t_request is None:
            from tagbiopy.run_protocol import TRequest
            self._t_request = TRequest(
                host=self.host,
                fc_name=self.fc_name,
                api_key=self.api_key,
                token=self.token
            )
        return self._t_request

    def get_protocol(self, protocol_name):
        """Return one protocol's full definition (argument sets, arg schema) via '/p'."""
        return self.p_request.get_protocol(protocol_name)

    def run_protocol(self, protocol_name, arguments=None, use_cache=True, download=False,
                     poll_interval=1.0, timeout=600, on_progress=None):
        """Run a named FC protocol to completion and return its analysis response.

        Discovery-driven: ``protocol_name`` is validated against '/p' (``list_protocols``)
        before anything is submitted, and argument names are checked against the
        protocol's argument definitions (unknown names raise, with the valid names in the
        message). Execution then follows the '/t' job flow the Tag.bio UI uses: submit,
        poll progress, fetch results.

        :param protocol_name: one of ``self.list_protocols()``
        :param arguments: dict of argument name -> value, as the protocol's argument
            definitions describe them (default: no arguments -- protocol defaults apply)
        :param use_cache: let the FC serve a cached identical run (default True)
        :param download: True for download-type protocols; returns raw ``bytes``
        :param poll_interval: seconds between progress polls (default 1.0)
        :param timeout: client-side ceiling in seconds (default 600); on expiry a
            :class:`tagbiopy.run_protocol.ProtocolRunTimeout` carries the job token so the
            run can be picked up or killed later. ``None`` waits forever.
        :param on_progress: optional callable receiving each progress dict
        :return: dict (the analysis response), or ``bytes`` when ``download=True`` or the
            protocol is a plugin (its rendered output: HTML, CSV, PNG, ...)
        """
        definition = self.get_protocol(protocol_name)  # raises ValueError on a bad name
        arguments = dict(arguments or {})

        known = set()
        for arg_set in (definition or {}).get('argument_sets', []):
            for arg in arg_set.get('arguments', []):
                name = (arg.get('argument_definition') or {}).get('name')
                if name:
                    known.add(name)
        unknown = set(arguments) - known
        if unknown and known:
            msg = (f'{self!r}: unknown argument(s) {sorted(unknown)} for protocol '
                   f'{protocol_name!r}. Valid names: {sorted(known)}')
            log_exception(ValueError, msg)

        protocol_instance = {'name': protocol_name, 'arguments': arguments}
        return self.t_request.run(
            protocol_instance,
            use_cache=use_cache,
            download=download,
            poll_interval=poll_interval,
            timeout=timeout,
            on_progress=on_progress,
        )

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
                for i, c_str in enumerate(self._collections[data_function_type]):
                    c_shell = fundamentals.variable_block_factory(data_function_type)(c_str)
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

    def count_nans(self, collection: AllCollectionTypes) -> Union[None, int, pd.DataFrame]:

        if isinstance(collection, fundamentals.COLLECTION_DATA_FUNCTION_TYPES):
            c_obj = self.get_collection(collection)
        elif isinstance(collection, fundamentals.COLLECTION_TYPES):
            c_obj = collection
        else:
            msg = f'{collection!r}: Invalid type. Should be either {fundamentals.COLLECTION_DATA_FUNCTION_TYPES}'
            msg += f' or {fundamentals.COLLECTION_TYPES}'
            log_exception(ValueError, msg)
            return None

        ret = None

        if isinstance(c_obj, fundamentals.CategoricalCollection):
            ret = self.number_of_entities - c_obj.collection_entity_count

        if isinstance(collection, fundamentals.Numeric):
            variables = self.list_variables(collection)
            data = []
            for variable in variables:
                var_obj = c_obj.get_variable(variable)
                nan_count = self.number_of_entities - var_obj.variable_size
                data.append([variable, nan_count])

            ret = pd.DataFrame(data=data, columns=['Variable', 'Entities without data'])
            ret.columns.name = f'Collection: {collection.collection!r}'

        return ret

    def get_collection(self, collection: fundamentals.COLLECTION_DATA_FUNCTION_TYPES) -> fundamentals.COLLECTION_TYPES:
        collection = check_arg_type(collection, fundamentals.COLLECTION_DATA_FUNCTION_TYPES)

        try:
            self._collections[collection.type_]
        except KeyError as e:
            msg = f'{collection!r}: No such {collection.data_function_type} collection'
            log_exception(TypeError, msg, cause=e)

        try:
            return self._collections[collection.type_][collection.collection]
        except KeyError as e:
            msg = f'{collection!r} not found among {collection.data_function_type} collections'
            log_exception(ValueError, msg, cause=e)

    def get_data_timestamp(self):
        return self.s_request.data_timestamp

    def get_start_time(self):
        return self.s_request.start_time

    def list_collections(self, data_function_type):
        try:
            ret = [v for v in self._collections[data_function_type]]
        except KeyError as e:
            msg = f'{data_function_type!r}: Invalid data_function_type. ' \
                  f'Please chose from {self.available_collection_types!r}'
            logger.debug(e, exc_info=True)
            logger.info(msg, exc_info=True)
            raise ValueError(msg)
        return ret

    def list_protocols(self):
        return self.p_request.protocols

    def list_variables(self, collection: Union[fundamentals.COLLECTION_DATA_FUNCTION_TYPES], as_generator=False):
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
            if isinstance(arg, (fundamentals.CollectionSet,) + fundamentals.COLLECTION_DATA_FUNCTION_TYPES):
                self.analysis_variables.append(arg)
            elif isinstance(arg, str):
                # Go over all data_types and break as soon as the arg is found among the first data_function_type.
                # For ties, no luck, get the first.
                for collection_type in self.available_collection_types:
                    if arg in self._collections[collection_type]:
                        self.analysis_variables.append(
                            fundamentals.variable_block_factory(data_function_type=collection_type)(arg)
                        )
                        break
                else:
                    msg = f'arg[{i}]: {arg!r} invalid data function type.'
                    msg += f' Not found among {fundamentals.COLLECTION_DATA_FUNCTION_TYPES}.'
                    log_exception(TypeError, msg)

            elif isinstance(arg, tuple):
                # Tuples only make sense for numeric collections. For categorical collections we
                # report the variable or NaN; for numeric collection variable we get a separate column.
                # So default behavior is that for categorical variables we keep just collection names,
                # for numeric variables we specify both collection and variables
                collection, variable = arg
                for collection_type in self.available_collection_types:
                    if collection in self._collections[collection_type]:
                        self.analysis_variables.append(
                            fundamentals.variable_block_factory(
                                data_function_type=collection_type)(collection, variable)
                        )
                        break
                else:
                    msg = f'{i}: arg {arg} collection {collection!r} invalid data function type.'
                    msg += f' Not found among {fundamentals.COLLECTION_DATA_FUNCTION_TYPES}.'
                    log_exception(TypeError, msg)
            else:
                msg = f'{i}: arg {arg!r} should be a string, a tuple or one of '
                msg += f'{[t.__name__ for t in fundamentals.COLLECTION_DATA_FUNCTION_TYPES]} (pass several as separate arguments).'
                log_exception(TypeError, msg)

        self.analysis_variables = list(set(self.analysis_variables)) or None

        return self

    def summarize_collection(self, collection: Union[fundamentals.COLLECTION_DATA_FUNCTION_TYPES]):

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
        if isinstance(collection, fundamentals.Numeric):
            nan_df = self.count_nans(collection)
            df = pd.concat([df, nan_df], axis=1)

        df.columns.name = collection.collection
        if isinstance(c_obj, fundamentals.CategoricalCollection):
            df.index.name = f'Number of entities: {c_obj.collection_entity_count}'

        # Clear variable for logging
        collection.variable = None
        logger.info(f'{collection!r}: variable summary shape: {df.shape}')

        # Column "Variable" may be duplicated due to the count_nans method
        return df.loc[:, ~df.columns.duplicated()]

    def to_dataframe(self,
                     analysis_variables: VariableBlockTypes,
                     background: Optional[fundamentals.SetBlock] = None,
                     include_background: bool = False,
                     output_type: Optional[str] = "parquet",
                     categories: bool = False,
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
        drop_retired_arguments(kwargs, 'to_dataframe')

        if background is None and include_background is True:
            msg = f'{self!r}: Invalid background selection: {background=}, {include_background=}'
            log_exception(ValueError, msg)

        logger.info(f'{self!r}: {analysis_variables = }')
        logger.info(f'{self!r}: {background = }')

        _analysis_variables = self._prepare(analysis_variables)

        if include_background:
            _analysis_variables.append(background)

        content = self.get_content(analysis_variables=_analysis_variables, background=background,
                                   output_type=output_type)

        ret = content_to_dataframe(content=content, categories=categories, **kwargs)
        logger.info(f'{self!r}: dataframe shape {ret.shape}')
        return ret

    def head(self, n: int = 6, seed: int = 1):
        """Keep a reproducible set of `n` entities: a seeded sample of the entities matching the filters so
        far (or of all entities). The same n and seed return the same entities; entities have no inherent
        order, so this is a reproducible subset, not "the first n". Used as
        self.df.select(...).where(...).head(10).run()
        """
        self._head = (int(n), int(seed))
        return self

    def list_collection_sets(self, pattern: str = None) -> list:
        """Names of the collection sets in this data product (needs an engine with the 'collection-set'
        query method). pattern: optional regular expression (case-insensitive) the names must match."""
        self.payload = {'method': 'collection-set'}
        names = [r['values']['collection-set-name'] for r in self.as_dict.get('results', [])]
        if pattern is not None:
            names = [n for n in names if re.search(pattern, n, flags=re.IGNORECASE)]
        return names

    def list_collection_set_members(self, collection_set: str, data_type: str = None) -> pd.DataFrame:
        """The collections in a collection set, without downloading their data: one row per collection with its
        data type, number of variables and number of entities with a value. data_type: optional
        'categorical' or 'numeric' to keep only that type."""
        payload = self.prepare_payload(method='collection',
                                       analysis_variables=[fundamentals.CollectionSet(collection_set)])
        payload['limit'] = COLLECTION_LIMIT
        self.payload = payload
        rows = []
        for r in self.as_dict.get('results', []):
            v = r['values']
            name = _flux_name(v['collection']['name'] if isinstance(v.get('collection'), dict) else v.get('collection'))
            rows.append({'collection': name,
                         'data_type': v.get('data_reference_type') or v.get('data_function_type'),
                         'variables': v.get('collection-size'),
                         'entities': v.get('collection-entity-count')})
        ret = pd.DataFrame(rows, columns=['collection', 'data_type', 'variables', 'entities'])
        # filtered here: the engine treats a set filtered down to nothing as "every collection"
        if data_type is not None:
            ret = ret[ret['data_type'] == data_type].reset_index(drop=True)
        return ret

    def data_dictionary(self, collections: list = None, collection_set: str = None, variables: bool = False,
                        max_levels: int = 20, max_sets: int = 500) -> pd.DataFrame:
        """Describe this data product's data model: one row per collection with how to select it, the column(s)
        it arrives as, its kind (text, logical, date, number), entity coverage, its collection sets and, for
        small categoricals, its values. The same model the FC's MCP endpoint serves as fc://data-model. Only
        metadata is fetched, never entity rows.

        collections: optional list of collection names; collection_set: optional set name.
        variables=True returns one row per variable (numeric variable or categorical value) instead, and needs
        collections or collection_set, since some data products have millions of variables.
        max_levels: categoricals with at most this many values list them in 'levels'; numerics with at most this
            many variables list their column names in 'column' (larger ones show the name pattern).
        max_sets: set membership is filled in when the product has at most this many sets.
        The product's name, title, entity names and entity count are in the result's .attrs['data_product']."""
        if variables and collections is None and collection_set is None:
            raise ValueError('variables=True needs collections or collection_set: some data products have '
                             'millions of variables.')
        if isinstance(collections, str):
            collections = [collections]
        info = self.info
        entity_count = pd.to_numeric(info.get('entity_count'), errors='coerce')
        product = {k: info.get(k) for k in ('name', 'title', 'entity_name_singular', 'entity_name_plural')}
        product['entity_count'] = entity_count

        def query(payload):
            self.payload = payload
            return self.as_dict.get('results', [])

        # ---- collections
        if collection_set is not None:
            payload = self.prepare_payload(method='collection',
                                           analysis_variables=[fundamentals.CollectionSet(collection_set)])
        else:
            payload = {'method': 'collection'}
        payload['limit'] = COLLECTION_LIMIT
        rows = []
        for r in query(payload):
            v = r['values']
            coll = v.get('collection') if isinstance(v.get('collection'), dict) else {'name': v.get('collection')}
            rows.append({'collection': _flux_name(coll.get('name')),
                         'data_type': v.get('data_reference_type') or v.get('data_function_type'),
                         'single_valued': bool(coll.get('single_valued')),
                         'logical': bool(coll.get('logical')),
                         'date_kind': coll.get('date_kind'),
                         'n_values': v.get('collection-size'),
                         'n_entities': v.get('collection-entity-count')})
        dd = pd.DataFrame(rows, columns=['collection', 'data_type', 'single_valued', 'logical', 'date_kind',
                                         'n_values', 'n_entities'])
        if collections is not None:
            missing = sorted(set(collections) - set(dd['collection']))
            if missing:
                logger.warning(f'No collection named: {", ".join(missing)}')
            dd = dd[dd['collection'].isin(collections)].reset_index(drop=True)

        # ---- variables of small collections (levels, numeric column names), or everything in scope when variables
        want = pd.Series(True, index=dd.index) if variables else \
            dd['data_type'].isin(['categorical', 'numeric']) & (dd['n_values'] <= max_levels)
        var_rows = []
        if want.any() and (variables or dd.loc[want, 'n_values'].sum() <= 100000):
            fns = [{'data_function_type': t, 'collection': c}
                   for c, t in zip(dd.loc[want, 'collection'], dd.loc[want, 'data_type'])]
            for r in query({'method': 'variable', 'variables': fns, 'limit': COLLECTION_LIMIT}):
                v = r['values']
                var_rows.append({'collection': _flux_name(v['collection']['name']),
                                 'variable': _flux_name(v['variable']['name']),
                                 'data_type': v.get('data_reference_type'),
                                 'n_entities': v.get('variable-size'),
                                 'date_kind': v['variable'].get('date_kind')})
        vars_df = pd.DataFrame(var_rows, columns=['collection', 'variable', 'data_type', 'n_entities', 'date_kind'])

        def column_name(collection, variable, data_type):
            return collection if data_type == 'categorical' or variable == collection else f'{collection}: {variable}'

        if variables:
            vars_df['column'] = [column_name(c, v, t) for c, v, t in
                                 zip(vars_df['collection'], vars_df['variable'], vars_df['data_type'])]
            out = vars_df[['collection', 'variable', 'column', 'data_type', 'n_entities', 'date_kind']] \
                .sort_values(['collection', 'n_entities'], ascending=[True, False]).reset_index(drop=True)
            out.attrs['data_product'] = product
            return out

        num = vars_df[vars_df['data_type'] == 'numeric']
        columns = {c: '; '.join(sorted(column_name(c, v, 'numeric') for v in g['variable']))
                   for c, g in num.groupby('collection')}
        numeric_dates = {c for c, g in num.groupby('collection') if g['date_kind'].notna().any()}
        cat = vars_df[vars_df['data_type'] == 'categorical']
        levels = {c: '; '.join(sorted(g['variable'])) for c, g in cat.groupby('collection')}

        # ---- collection set membership (one members query per set)
        try:
            set_names = self.list_collection_sets()
        except Exception:
            set_names = []
        sets = {c: None for c in dd['collection']}
        if set_names and len(set_names) <= max_sets:
            sets = {c: '' for c in dd['collection']}
            for s in set_names:
                for c in self.list_collection_set_members(s)['collection']:
                    if c in sets:
                        sets[c] = s if not sets[c] else f'{sets[c]}; {s}'
        elif len(set_names) > max_sets:
            logger.warning(f'This data product has {len(set_names)} collection sets (more than max_sets={max_sets}): '
                           'collection_sets left empty. Use collection_set= to describe one set.')

        def kind(row):
            if row['logical']:
                return 'logical'
            if isinstance(row['date_kind'], str) or row['collection'] in numeric_dates:
                return 'date'
            return 'text' if row['data_type'] == 'categorical' else 'number'

        out = pd.DataFrame({
            'collection': dd['collection'],
            'column': [c if t != 'numeric' else columns.get(c, f"{c}: <variable> ({n:,.0f} variable{'' if n == 1 else 's'})")
                       for c, t, n in zip(dd['collection'], dd['data_type'], dd['n_values'])],
            'data_type': dd['data_type'],
            'kind': dd.apply(kind, axis=1) if len(dd) else pd.Series(dtype=object),
            'single_valued': [sv if t == 'categorical' else None for sv, t in zip(dd['single_valued'], dd['data_type'])],
            'n_values': dd['n_values'],
            'n_entities': dd['n_entities'],
            'pct_entities': (100 * pd.to_numeric(dd['n_entities']) / entity_count).round(1),
            'levels': [levels.get(c) for c in dd['collection']],
            'collection_sets': [sets.get(c) for c in dd['collection']],
        }).sort_values('collection').reset_index(drop=True)
        out.attrs['data_product'] = product
        return out

    def run(self, categories: bool = False, **kwargs):
        """Download the query. categories=True turns single_valued categorical columns (listed in the
        parquet file's metadata) into pandas 'category' dtype. Date columns arrive as UTC datetimes."""
        drop_retired_arguments(kwargs, 'run')

        if not self.analysis_variables and not self.background:
            msg = f'{self}: Neither analysis_variables nor background specified'
            log_exception(RuntimeError, msg)

        # Drop duplicates, again. If lists empty, turn them to None to avoid triggering
        # HTTP 500 errors
        self.analysis_variables = list(set(self.analysis_variables)) or None
        self.background = self.background or None

        background = self.background
        if getattr(self, '_head', None):
            n, seed = self._head
            background = fundamentals.Sample(criterion=background or fundamentals.CategoricalAll(),
                                             size=n, seed=seed)

        analysis_variables = self.analysis_variables
        ret = self.to_dataframe(
            analysis_variables=analysis_variables,
            background=background,
            categories=categories,
            **kwargs
        )
        return ret

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
                msg = f'Passed even number of arguments'
                log_exception(RuntimeError, msg)
            if self.background:
                msg = f'Cannot add {args[0] = } to background without a boolean operator first'
                log_exception(RuntimeError, msg)

        elif isinstance(args[0], str):
            compound_operator = args[0]

            check_boolean(compound_operator)
            if not self.background:
                msg = f'Cannot specify boolean {compound_operator = } for undefined background'
                log_exception(RuntimeError, msg)

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
            self.background = fundamentals.CategoricalCompound(
                criteria=[self.background, background],
                operator=compound_operator
            )
        else:
            self.background = background

        return self


def list_data_products(host: str = None, api_key: str = None, token: str = None) -> pd.DataFrame:
    """The data products on a Tag.bio cluster: the same catalog the Tag.bio UI uses
    (kung-services/db/capacitors). A localhost host serves one data product, listed as 'localhost'.

    :return: pd.DataFrame with Name, Title, Description, Reference, url, Entity
    """
    from tagbiopy.request import Session, _is_localhost
    session = Session(host=host, api_key=api_key, token=token)
    if _is_localhost(session.host):
        return pd.DataFrame([{'Name': 'localhost', 'Title': 'localhost', 'Description': 'local data product',
                              'Reference': None, 'url': session.host, 'Entity': None}])
    return session.summary()
