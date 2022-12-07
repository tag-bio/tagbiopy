import json
import logging
import os
import re

import inflection

from tagbiopy import logger
from tagbiopy.utils import generate_repr, log_exception


DEFAULT_DIR = '/tagbio/fluxcapacitor/protocol/defaults/arguments'
ARGUMENT_SET_FILTER = os.path.join(DEFAULT_DIR, 'argument_sets/argument_set_filter.json')
ARGUMENT_REFERENCE_FILTER = os.path.join(DEFAULT_DIR, 'argument_references/argument_reference_filter.json')

COLLATERAL_SUBDIR = 'protocols/_auto'

ARGUMENT_SET_TYPES = [
    'hidden',
    'mandatory',
    'minimum-one',
    'optional'
]

ARGUMENT_TYPES = [
    'categorical-checkbox',
    'categorical-checkbox-filter',
    'categorical-paste',
    'categorical-radio-filter',
    'cohort',
    'numeric',
    'numeric-range',
    'static-categorical',
    'static-numeric',
    'static-numeric',
    'static-radio'
]


def _validate(arg, pool):
    if arg not in pool:
        msg = f'Invalid argument: {arg!r}. Choose from {pool}'
        raise ValueError(msg)
    return arg


def remove_auto_collateral(base_dir):
    import shutil
    path = os.path.join(base_dir, COLLATERAL_SUBDIR)
    shutil.rmtree(path)


class ArgumentExpander(object):
    _argument_types = ('categorical-checkbox-filter', 'categorical-paste', 'numeric-range')

    def __init__(self, base_dir, collection, data_function_type='categorical',
                 argument_type='categorical-checkbox-filter', variable=None, method=None, provide_path=True):

        self.base_dir = base_dir
        self.collection = collection
        # Set the default data_function_type
        self.data_function_type = data_function_type

        self.argument_type = _validate(argument_type, ArgumentExpander._argument_types)
        self.variable = variable
        self.method = method
        self.provide_path = provide_path

        self._argument_function = None
        self._collateral = None

    def __repr__(self):
        return generate_repr(self)

    @property
    def argument_function(self):
        if self._argument_function is None:
            path = set_path(collection=self.collection, argument_type=self.data_function_type, variable=self.variable)
            d = create_data_function(data_function_type=self.data_function_type,
                                     collection=self.collection,
                                     variable=self.variable)

            logger.debug(f'Argument function:\n{json.dumps(d, indent=2)}')
            full_path = os.path.join(self.base_dir, path)
            store_collateral(d, full_path)
            logger.info(f'Argument function: stored to {full_path!r}, provide relative path {path!r}')

            if self.provide_path:
                self._argument_function = path
            else:
                self._argument_function = d

            logger.debug(f'{self._argument_function = }')

        return self._argument_function

    @property
    def collateral(self):
        if self._collateral is None:
            self._collateral = {
                'argument_type': self.argument_type,
                'argument_function': self.argument_function
            }
            if self.method:
                self.collateral.update({'method': self.method})
        return self._collateral


class ArgumentSet(object):

    def __init__(self, base_dir, title, argument_set_type='optional', asset=None, arguments=None,
                 data_function_type='categorical', variables=None, ignore=None, cohorts=True,
                 server_filter=None, section=False):
        self.base_dir = base_dir
        self.argument_set_type = argument_set_type
        self.title = title
        self.asset = asset

        if arguments is None:
            self.arguments = []
        else:
            self.arguments = arguments

        self.data_function_type = data_function_type

        if variables is None:
            self.variables = []
        else:
            self.variables = variables

        if ignore is None:
            self.ignore = []
        else:
            self.ignore = ignore

        self.cohorts = cohorts

        # For cohort builder: method is always summary
        # For analysis_variables, method is always variable
        if self.cohorts:
            self.method = 'summary'
            self.destination = 'cohort'
            self.prefix = 'cohort'
        else:
            self.method = 'variable'
            self.destination = 'analysis_variables'
            self.prefix = None

        self.server_filter = server_filter

        self.name = underscore(self.title, self.prefix)

        self.section = section

        self._collateral = None
        self._reference_collateral = None

        self._argument_expanders = None

        self.reference_path = None
        self.full_reference_path = None

        # If I need a section header, do not worry about the references
        if self.section:
            self.path = set_path(self.title, argument_type='argument_set', header=True, destination=self.destination)
        else:
            if self.arguments:
                self.path = set_path(self.title, argument_type='argument_set', destination=self.destination)
                self.reference_path = set_path(self.title,
                                               argument_type='argument_set_reference',
                                               destination=self.destination
                                               )
                self.full_reference_path = os.path.join(self.base_dir, self.reference_path)
            else:
                msg = f'{self!r}: No arguments provided. That can be only done when creating sections'
                raise(ValueError, msg)

        self.full_path = os.path.join(self.base_dir, self.path)

    def __repr__(self):
        return generate_repr(self)

    @property
    def argument_expanders(self):
        if self._argument_expanders is None:
            self._argument_expanders = []
            for arg in self.arguments:
                if arg in self.ignore:
                    logger.debug(f'arg {arg!r} ignored')
                    continue
                if isinstance(arg, str):
                    kwargs = {
                        'collection': arg,
                        'data_function_type': self.data_function_type,
                        'method': self.method
                    }
                    if self.data_function_type == 'numeric':
                        if self.cohorts:
                            kwargs.update({'argument_type': 'numeric-range'})
                            if self.variables:
                                for variable in self.variables:
                                    kwargs.update({'variable': variable})
                                    arg_expander = ArgumentExpander(base_dir=self.base_dir, **kwargs)
                                    logger.debug(f'collection = {arg}, {variable = }: {arg_expander!r}')
                                    self._argument_expanders.append(arg_expander.collateral)
                        else:
                            arg_expander = ArgumentExpander(base_dir=self.base_dir, **kwargs)
                            self._argument_expanders.append(arg_expander.collateral)

                    else:
                        arg_expander = ArgumentExpander(base_dir=self.base_dir, **kwargs)
                        self._argument_expanders.append(arg_expander.collateral)

                elif isinstance(arg, dict):
                    # In cohort builder: numeric collections override the default ArgumentExpander argument_type
                    # as we have to use 'numeric-range' argument_type
                    logger.debug(arg)
                    kwargs = {
                        'collection': arg['collection'],
                        'data_function_type': arg.get('data_function_type', self.data_function_type),
                        'method': self.method
                    }
                    if arg['data_function_type'] == 'numeric':
                        if self.cohorts:
                            kwargs.setdefault('argument_type', 'numeric-range')

                            variables = arg.get('variables', self.variables)
                            logger.debug(f'{variables = }')

                            for variable in variables:
                                kwargs.update({'variable': variable})
                                logger.debug(kwargs)
                                arg_expander = ArgumentExpander(base_dir=self.base_dir, **kwargs)
                                logger.debug(f'{variable = }: {arg_expander!r}')
                                self._argument_expanders.append(arg_expander.collateral)
                        else:
                            arg_expander = ArgumentExpander(base_dir=self.base_dir, **kwargs)
                            self._argument_expanders.append(arg_expander.collateral)
                    else:
                        arg_expander = ArgumentExpander(base_dir=self.base_dir, **kwargs)
                        self._argument_expanders.append(arg_expander.collateral)
                else:
                    raise ValueError(f'{self!r}: argument {arg} invalid type. Should be str or dict')

        return self._argument_expanders

    @property
    def collateral(self):
        if self._collateral is None:
            self._collateral = {
                'argument_set_type': self.argument_set_type,
                'name': self.name,
                'title': self.title
            }

            if self.asset is not None:
                self._collateral.update({'asset': self.asset})

            if self.server_filter is not None:
                self._collateral.update({'server_filter': True})

            if self.argument_expanders:
                self._collateral.update({'argument_expanders': self.argument_expanders})

        return self._collateral

    @property
    def reference_collateral(self):
        if self._reference_collateral is None:
            self._reference_collateral = {
                'data_function_type': 'argument-reference',
                'argument_set': self.name
            }
        return self._reference_collateral

    def create(self):
        if self.section:
            store_collateral(self.collateral, self.full_path)
            msg = f'{self!r}: collateral stored to {self.full_path}'
            logger.info(msg)
            logger.debug(f'{json.dumps(self.collateral, indent=2)}')

            return self.path
        else:
            if self.argument_expanders:
                store_collateral(self.collateral, self.full_path)
                msg = f'{self!r}: collateral stored to {self.full_path}'
                logger.info(msg)
                logger.debug(f'{json.dumps(self.collateral, indent=2)}')

                store_collateral(self.reference_collateral, self.full_reference_path)
                msg = f'{self!r}: reference collateral stored to {self.full_reference_path}'
                logger.info(msg)
                logger.debug(f'{json.dumps(self.reference_collateral, indent=2)}')

                return self.path, self.reference_path
            else:
                return 'N/A'


def create_argument(collection, argument_type, data_reference_path, argument_protocol_path, use_filter=False):
    name = underscore(collection)

    ret = {
        'argument_definition': {
            'title': collection,
            'name': name,
            'argument_type': argument_type,
            'unfiltered_limit': 20,
            'filtered_limit': 80
        },
        'handlers': [
            {
                'handler': name,
                'handler_function': data_reference_path
            }
        ],
        'argument_protocol': argument_protocol_path
    }

    if use_filter:
        ret.update({'server_filter': True})

    return ret


def create_argument_protocol(collection, analysis_variables, method, use_filter=False):
    name = underscore(collection)

    d = {
        'protocol_definition': {
            'title': collection,
            'name': name,
        },
        'script': {
            'method': method,
            'analysis_variables': analysis_variables
        }
    }

    if use_filter:
        d['protocol_definition'].update({'argument_sets': ARGUMENT_SET_FILTER})

    return d


def create_argument_reference(collection):
    name = underscore(collection)
    data_function_type = 'argument-reference'

    return {
        'data_function_type': data_function_type,
        'argument': name,
        'handler': name
    }


def create_argument_reference_set(criteria):
    return {
        'data_function_type': 'set-operation',
        'operator': 'AND',
        'criteria': criteria
    }


def create_argument_set(name: str, argument_set_type: str, arguments=None, asset=None, repeat_script=None,
                        argument_type=None):
    name = inflection.titleize(name)
    # Handle the edge case
    name = name.replace('I Ds', 'IDs')

    ret = {
        'name': name,
        'argument_set_type': argument_set_type
    }

    if (arguments is None and repeat_script is None) or (arguments is not None and repeat_script is not None):
        msg = f'Either arguments or repeat_script have to be specified'
        msg += f'\n{arguments = }\n{repeat_script = }'
        log_exception(ValueError, msg)

    if arguments is not None:
        ret.update({'arguments': arguments})

    if repeat_script is not None:
        ret.update({'repeat_script': repeat_script})
        if argument_type is None:
            msg = f'{argument_type = }. Specify either "categorical" or "numeric"'
            log_exception(ValueError, msg)
        ret.update({'argument_type': argument_type})
        ret.update({'argument_name_prefix': 'rs_'})

    if asset is not None:
        ret.update(asset)

    return ret


def create_argument_set_section(name):
    return create_argument_set(name, argument_set_type='optional', arguments=[])


def create_cohort_protocol(argument_sets, criteria):
    return {
        'protocol_definition': {
            'name': 'cohort',
            'cohort': True,
            'argument_sets': argument_sets
        },
        'script': {
            'method': 'entity',
            'background': {
                'data_function_type': 'set-operation',
                'operator': 'AND',
                'criteria': criteria
            }
        }
    }


def create_data_function(data_function_type, collection, variable=None, use_filter=False):
    d = {
        'data_function_type': data_function_type,
        'collection': collection
    }

    if variable is not None:
        d.update({'variable': variable})

    if use_filter:
        d = {
            'data_function_type': 'filter',
            'criteria': d,
            'filters':
                {
                    'filter_type': 'categorical',
                    'operator': '_contains',
                    'required': False,
                    'value': ARGUMENT_REFERENCE_FILTER
                }
        }

    return d


def create_repeat_script(method, analysis_variables):
    return {
        'method': method,
        'analysis_variables': analysis_variables
    }


def merge_argument_set_scaffolds(*kwargs):
    import copy
    first = copy.deepcopy(kwargs[0])
    ret = {**first}

    for kw in kwargs[1:]:
        for k in kw:
            w = kw[k]
            if k not in ret:
                ret.update({k: w})
            else:
                if w is None:
                    continue
                ret[k].extend(w)

    return ret


def set_path(collection, argument_type, variable=None, use_filter=False, header=False, destination=None):
    collection = underscore(collection)

    subdir = COLLATERAL_SUBDIR

    if argument_type in ('categorical', 'numeric'):
        subdir = os.path.join(subdir, 'data_functions')
        argument_type = 'collection'
    elif argument_type in ('helper_protocol',):
        subdir = os.path.join(subdir, f'{argument_type}s')
    else:
        subdir = os.path.join(subdir, 'arguments', f'{argument_type}s')

    if destination is not None:
        subdir = os.path.join(subdir, destination)

    basename = f'{argument_type}_{collection}'

    if variable is not None:
        variable = underscore(variable)
        basename = f'{basename}_variable_{variable}'

    if use_filter:
        basename = f'{basename}_filter'

    if header:
        basename = f'section_header_{basename}'

    filename = os.path.join(subdir, f'{basename}.json')

    return filename


def store_collateral(d, filename):
    path = os.path.dirname(filename)
    os.makedirs(path, exist_ok=True)
    with open(filename, 'w') as fh:
        json.dump(d, fh, indent=2)


def underscore(s, prefix=None):
    if s is None:
        return s

    # Replace % with prcnt
    s = re.sub(r'%+', 'prcnt', s)
    # Replace <= with le
    s = re.sub(r'<=', ' le ', s)
    # Replace >= with ge
    s = re.sub(r'>=', ' ge ', s)
    # Replace < with lt
    s = re.sub(r'<', ' lt ', s)
    # Replace < with lt
    s = re.sub(r'>', ' gt ', s)
    # Replace / with ' per '
    s = re.sub(r'/', ' per ', s)
    # Replace multiple spaces with a single underscore
    s = re.sub(r'\s+', '_', s)
    # Remove all non-word and non-underscore characters
    s = re.sub(r'[^\w_]+', '', s)
    # Remove trailing underscore
    s = re.sub(r'_+$', '', s)
    # Remove all multiple underscores with a single underscore
    s = re.sub(r'_+', '_', s)
    # Just for fun

    if prefix is not None:
        s = f'{prefix}_{s}'
    return inflection.underscore(s)
