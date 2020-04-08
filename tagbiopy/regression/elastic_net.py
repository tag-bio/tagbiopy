#!/usr/bin/env python

import os
import logging
import warnings
import pandas as pd


from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.linear_model import ElasticNetCV
from sklearn.exceptions import ConvergenceWarning


logging.captureWarnings(capture=True)

# Get logger for warnings
logger = logging.getLogger("py.warnings")

# StreamHandler outputs on sys.stderr by default
handler = logging.StreamHandler()
logger.addHandler(handler)

# Set rule to ignore warnings
logger.addFilter(lambda record: "ConvergenceWarning" not in record.getMessage())


def create_pipeline(impute_missing_values=True, **kwargs):
    params = elastic_net_cross_validation_params(**kwargs)

    estimator = ElasticNetCV(**params)

    if impute_missing_values:
        imputer = SimpleImputer(strategy='median')
        pipeline = Pipeline([('imputer', imputer), ('estimator', estimator)])
    else:
        pipeline = Pipeline([('estimator', estimator)])

    return pipeline


def elastic_net_cross_validation_params(**kwargs):
    import multiprocessing

    # Prescribed in the documentation
    # https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.ElasticNetCV.html
    l1_ratio = kwargs.get('l1_ratio', [.1, .5, .7, .9, .95, .99, 1])
    cv = LeaveOneOut()
    # The regressors X will be normalized before regression by subtracting the mean and dividing by the l2-norm.
    normalize = kwargs.get('normalize', True)
    n_jobs = kwargs.get('n_jobs', multiprocessing.cpu_count())
    max_iter = kwargs.get('max_iter', 100000)
    tol = kwargs.get('tol', 1e-6)
    random_state = kwargs.get('random_state', 12345)
    return {
        'l1_ratio': l1_ratio,
        'cv': cv,
        'normalize': normalize,
        'n_jobs': n_jobs,
        'max_iter': max_iter,
        'tol': tol,
        'random_state': random_state
    }


def elastic_net_cross_validation_worker(outcome, observations, verbose=0, **kwargs):
    params = elastic_net_cross_validation_params(**kwargs)

    gscv = create_pipeline(**params)

    # Desperate attemtp to remove warnings
    with warnings.catch_warnings():
        warnings.filterwarnings(
            action='ignore',
            message='Objective did not converge.',
            lineno=474,
            category=ConvergenceWarning)
        _data = cross_val_predict(estimator=gscv,
                                  X=observations,
                                  y=outcome,
                                  cv=LeaveOneOut(),
                                  n_jobs=params['n_jobs'],
                                  verbose=verbose)

    predicted_outcome = pd.Series(data=_data, index=outcome.index, name='Predicted {}'.format(outcome.name))

    return predicted_outcome, params


def set_plot_label(text, params, verbose=True):
    import decimal
    label = text
    if verbose:
        label += '\ntol: {:.1E}'.format(decimal.Decimal(params['tol']))
        label += ', max_iter: {:.1E}'.format(decimal.Decimal(params['max_iter']))

    return label


def set_outcome_and_observations(df, outcome_column):
    """

    :param df: pd.DataFrame, input dataframe
    :param outcome_column: str
    :return: 2-touple
        outcome (y): pd.Series
        observations (X): pd.DataFrame with used variables
    """
    _df = df.copy()
    # Remove all rows that don't have outcome data
    _df = _df.dropna(subset=[outcome_column])
    outcome = _df[outcome_column]
    observations = _df[[v for v in _df.columns if v != outcome_column]]

    return outcome, observations


def elastic_net_cross_validation(y, observations, **kwargs):
    """

    :param y: pd.Series, observed outcome
    :param observations: pd.DataFrame, predictors
    :param kwargs: dict, optional args to be passed to elastic_net_cross_validation_params function to
        tweak the elastic net default model params.
    :return: 2-touple
        y_hat: pd.Series, predicted values
        model_params: dict, what was used by elastic net cross validation
    """
    y_hat, model_params = elastic_net_cross_validation_worker(y, observations, **kwargs)

    return y_hat, model_params
