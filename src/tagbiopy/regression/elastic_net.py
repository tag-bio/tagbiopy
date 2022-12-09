#!/usr/bin/env python
import logging
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.linear_model import ElasticNetCV

from tagbiopy import logger


def create_pipeline(impute_missing_values=True, **kwargs) -> Pipeline:
    """
    Creates a Pipeline that always ends with ElasticNetCV estimator. The first step may be imputer.
    :param impute_missing_values: bool, default True
    :param kwargs: dict, if non-default elastic net cross validation parameters are desired
    :return: Pipeline
    """

    estimator = ElasticNetCV(**kwargs)

    if impute_missing_values:
        imputer = SimpleImputer(strategy='median')
        pipeline = Pipeline([('imputer', imputer), ('estimator', estimator)])
    else:
        pipeline = Pipeline([('estimator', estimator)])

    return pipeline


def elastic_net_cross_validation_params(**kwargs) -> dict:
    # l1_ratio: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.ElasticNetCV.html
    # The regressors X will be normalized before regression by subtracting the
    # mean and dividing by the l2-norm.

    import multiprocessing

    l1_ratio = kwargs.get('l1_ratio', [.1, .5, .7, .9, .95, .99, 1])
    cv = kwargs.get('cv', LeaveOneOut())
    normalize = kwargs.get('normalize', True)
    n_jobs = kwargs.get('n_jobs', multiprocessing.cpu_count())
    max_iter = kwargs.get('max_iter', 1000000)
    tol = kwargs.get('tol', 1e-7)
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


def elastic_net_cross_validation(outcome, observations, **kwargs) -> (pd.Series, dict):
    """

    :param outcome: pd.Series, observed outcome
    :param observations: pd.DataFrame, predictors
    :param kwargs: dict, optional args to be passed to elastic_net_cross_validation_params function to
        tweak the elastic net default model params.
    :return: 2-touple
        predicted_outcome: pd.Series, predicted values
        params: dict, what was used by elastic net cross validation
    """

    params = elastic_net_cross_validation_params(**kwargs)
    gscv = create_pipeline(**params)
    logger.debug('gscv: {}'.format(str(gscv)))

    logger.debug('Starting cross_val_predict')
    _data = cross_val_predict(estimator=gscv,
                              X=observations,
                              y=outcome,
                              cv=LeaveOneOut(),
                              n_jobs=params['n_jobs']
                              )
    logger.debug('Completed cross_val_predict')

    predicted_outcome = pd.Series(data=_data, index=outcome.index, name='Predicted {}'.format(outcome.name))

    return predicted_outcome, params


def set_outcome_and_observations(df: pd.DataFrame, outcome: tuple) -> (pd.Series, pd.DataFrame):
    """
    Separates the input dataframe into the outcome vector and a matrix of variables (predictors)
    :param df: pd.DataFrame, input dataframe
    :param outcome: tuple
    :return: 2-touple
        outcome (y): pd.Series
        observations (X): pd.DataFrame with used variables
    """
    logger.debug(f'{df.columns = }')
    _df = df.copy()
    # Remove all rows that don't have outcome data
    input_shape = _df.shape
    logger.debug('Input df shape: {}'.format(str(input_shape)))

    outcome_collection, outcome_variable = outcome
    outcome_column = [v for v in df.columns if
                      v.startswith(outcome_collection) and
                      v.endswith(outcome_variable)
                      ].pop()

    logger.debug(f'{outcome_column = }')
    _df = _df.dropna(subset=[outcome_column])
    final_shape = _df.shape
    if input_shape != final_shape:
        logger.debug("After removing NaN's from the outcome, we have new shape: {}".format(str(final_shape)))

    outcome = _df[outcome_column]
    outcome = outcome.rename(outcome_variable)
    observations = _df.drop(columns=[outcome_column])

    return outcome, observations


def set_plot_label(text, params, verbose=True) -> str:
    import decimal
    label = text
    if verbose:
        label += '\ntol: {:.1E}'.format(decimal.Decimal(params['tol']))
        label += ', max_iter: {:.1E}'.format(decimal.Decimal(params['max_iter']))

    return label
