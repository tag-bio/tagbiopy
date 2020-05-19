import logging
import multiprocessing as mp
from collections import deque

import numpy as np
import pandas as pd

from sklearn import preprocessing
from sklearn.metrics import f1_score, precision_score, recall_score, accuracy_score

from tagbiopy.utils import TagbioData, TagbioResult
from tagbiopy.logging import LOGGER_NAME

ID = 'Aircraft engine ID'
OUTCOME = 'RUL - Remaining useful life'
TIME_UNIT = 'Cycle'

TRAIN = 'Train data'
TEST = 'Test data'
WHATS = (TRAIN, TEST)

logger = logging.getLogger(LOGGER_NAME)


def prepare_data(df, what, fail_within, m, tau):
    pr = Preparer(df, what, fail_within, m, tau)
    logger.info(pr)

    # Group by ID
    _groupby = pr.effective_df.groupby(by=ID, sort=False)
    # Split effective dataframes per ID
    df = {k: _groupby.get_group(k) for k in pr.effective_df[ID]}
    logger.info(f'Split effective df into {len(df)} individual dataframes')

    # Just in case, remove association with Preparer instance
    ignore_columns = [v for v in pr.non_measured]
    kwargs = {k: v for k, v in pr.kwargs.items()}
    logger.debug(f'ignore_columns {ignore_columns}, kwargs {kwargs}')

    # Create argument generator for takenize
    args = ((df[k], ignore_columns, kwargs) for k in df.keys())

    n_cores = mp.cpu_count()
    logger.info(f'Starting mutliprocessing with {n_cores} cores')
    with mp.get_context('spawn').Pool(n_cores) as pool:
        results = pool.map(takenize, args)
        pool.close()
        pool.join()
    logger.info('Multiprocessing completed')

    ret = pd.concat(results)

    logger.info(f'Prepared df {ret.shape} in size')
    return ret


def quality_of_fit(y, y_hat):
    precision = precision_score(y, y_hat)
    recall = recall_score(y, y_hat)
    f1 = f1_score(y, y_hat)
    accuracy = accuracy_score(y, y_hat)
    return pd.Series(data=[precision, recall, f1, accuracy], index=['Precision', 'Recall', 'f1-score', 'Accuracy'])


def predictive_maintenance(tag_data: TagbioData, tag_result: TagbioResult):
    logger.debug(tag_data)
    logger.debug(tag_data.passthrough_arguments)

    fail_within = tag_data.passthrough_arguments.fail_within
    m = tag_data.passthrough_arguments.m_embedding_dimension
    tau = tag_data.passthrough_arguments.tau_delay

    tag_result.data = train_n_predict(tag_data.df, fail_within, m, tau, classifier_name='logit')


def set_classifier(classifier_name='logit', **kwargs):
    classifiers = ['logit', 'rf', 'mlp', 'sgd', 'decision tree']

    if classifier_name == 'logit':
        from sklearn.linear_model import LogisticRegression
        ret = LogisticRegression(solver='saga', multi_class='ovr', n_jobs=-1)
    elif classifier_name == 'rf':
        from sklearn.ensemble import RandomForestClassifier
        ret = RandomForestClassifier(n_jobs=-1, **kwargs)
    elif classifier_name == 'svc':
        from sklearn.svm import SVC
        ret = SVC(random_state=42)
    elif classifier_name == 'mlp':
        # Neural network multi-layer perceptron
        from sklearn.neural_network import MLPClassifier
        ret = MLPClassifier(solver='adam', random_state=42)
    elif classifier_name == 'decision tree':
        from sklearn.tree import DecisionTreeClassifier
        ret = DecisionTreeClassifier(random_state=42)
    elif classifier_name == 'sgd':
        # Stochastic gradient descent
        from sklearn.linear_model import SGDClassifier
        ret = SGDClassifier(n_jobs=-1)
    else:
        raise ValueError(f'No classifier specified. Choose from {classifiers}.')
    logger.info(f'Using "{classifier_name}" classifier, kwargs {kwargs}')
    return ret


def set_scaler():
    return preprocessing.MinMaxScaler()


def set_outcome(fail_within):
    return f'Fail within {fail_within} {TIME_UNIT}s'


def set_predicted_outcome(fail_within, classifier_name):
    return set_outcome(fail_within) + f' predicted by {classifier_name}'


def takenize(argtuple):
    df, ignore_columns, kwargs = argtuple
    logger.info(f'takenize {ID}: {df[ID].iloc[0]}')

    columns = (v[1] for v in df.iteritems() if v[0] not in ignore_columns)
    _m_std = [Takens(c).summarize(**kwargs) for c in columns]
    _m_std_df = pd.concat([item for sublist in _m_std for item in sublist], axis=1)
    return df[ignore_columns].join(_m_std_df, how='right')


def train_n_predict(_df, fail_within, m, tau, classifier_name, **kwargs):
    # Load Preparer on a small df, just to get all the parameters
    pr = Preparer(df=_df.head(), what=TRAIN, fail_within=fail_within, m=m, tau=tau)
    logger.debug(pr)

    # Split and prepare train and test data set
    working_df = {what: prepare_data(df=_df[_df['Data set'] == what],
                                     what=what,
                                     fail_within=fail_within,
                                     m=m,
                                     tau=tau)
                  for what in WHATS}

    # Prepare classifier and scaler
    classifier = set_classifier(classifier_name, **kwargs)
    scaler = set_scaler()

    # Column gymnastics
    ignore_columns = [v for v in pr.non_measured]
    outcome_column = set_outcome(fail_within)
    logger.info(f'ignore_columns {ignore_columns}')
    logger.info(f'outcome_column "{outcome_column}"')
    logger.debug(working_df[TRAIN].head().T)
    logger.debug(f'train columns:\n{working_df[TRAIN].columns}')

    y_hat = {}
    logger.debug('Rescaling predictors')
    # Rescale
    features = [v for v in working_df[TRAIN].columns if v not in ignore_columns]
    x_matrix = {what: scaler.fit_transform(working_df[what][features]) for what in WHATS}
    y = {what: working_df[what][outcome_column] for what in WHATS}
    # Train
    tx = classifier.fit(x_matrix[TRAIN], y[TRAIN])

    # Test on self
    y_hat[TRAIN] = tx.predict(x_matrix[TRAIN])
    # Test in test
    y_hat[TEST] = tx.predict(x_matrix[TEST])

    logger.info(f'Test completed')

    # Assess quality of predictions
    q_self = quality_of_fit(y[TRAIN], y_hat[TRAIN])
    q_self.name = f'Self: {outcome_column}, m={m}, tau={tau}, {classifier_name} classifier'
    logger.info(f'\n{q_self}')

    q = quality_of_fit(y[TEST], y_hat[TEST])
    q.name = f'{outcome_column}, m={m}, tau={tau}, {classifier_name} classifier'
    logger.info(f'\n{q}')

    return_df = pd.concat([working_df[what][ignore_columns] for what in WHATS])
    predicted_outcome = np.append(y_hat[TRAIN], y_hat[TEST])
    outcome_s = pd.Series(data=predicted_outcome, index=return_df.index)
    outcome_s.name = set_predicted_outcome(fail_within, classifier_name)

    return pd.concat([return_df, outcome_s], axis=1)


class Preparer:
    ignore_columns = (ID, TIME_UNIT, OUTCOME, 'Data set')
    train_factor = 2

    def __init__(self, df, what, fail_within, m, tau, time_unit=TIME_UNIT, reverse=True,
                 operational_settings=False):
        self.df = df
        self.what = what
        self.fail_within = fail_within
        self.operational_settings = operational_settings
        self.outcome_name = f'Fail within {self.fail_within} {TIME_UNIT}s'

        self._non_measured = None

        # Takens embed parameters
        self.m = m
        self.tau = tau
        self.time_unit = time_unit
        self.reverse = reverse

        self.kwargs = {
            'm': self.m,
            'tau': self.tau,
            'time_unit': self.time_unit,
            'reverse': self.reverse
        }

        self._binary_outcome = None
        self._counts = None
        self._effective_df = None
        self._prepared_df = None

    def __repr__(self):
        return f'{__name__}.{self.__class__.__name__}(df, what="{self.what}", ' \
               f'fail_within={self.fail_within}, m={self.m}, tau={self.tau})'

    @property
    def binary_outcome(self):
        if self._binary_outcome is None:
            self._binary_outcome = pd.Series(self.df[OUTCOME] < self.fail_within).astype(int)
            self._binary_outcome.name = f'Fail within {self.fail_within} {TIME_UNIT}s'
        return self._binary_outcome

    @property
    def counts(self):
        if self._counts is None:
            self._counts = self.df[[ID, TIME_UNIT]].groupby(ID, sort=False).count()
            self._counts.columns = [f'Remainig {TIME_UNIT}s']
        return self._counts

    @property
    def effective_df(self):
        if self._effective_df is None:
            _dfs = []
            for i, _df in self.df_with_outcome().groupby(ID, sort=False):
                chunk = self.fail_within
                if self.what == TRAIN:
                    chunk = int(Preparer.train_factor * chunk)
                start_from = _df.shape[0] - chunk - self.m * self.tau + 1
                if start_from < 0:
                    start_from = 0
                _tmp_df = _df.iloc[start_from:, :]
                logger.debug(f'{i:3d}: all {_df.shape[0]}, start_from {start_from:3d}, _tmp_df {_tmp_df.shape[0]}')
                _dfs.append(_tmp_df)
            self._effective_df = pd.concat(_dfs)

        return self._effective_df

    @property
    def non_measured(self):
        if self._non_measured is None:
            self._non_measured = [v for v in Preparer.ignore_columns]
            self._non_measured.append(self.outcome_name)
            if not self.operational_settings:
                self._non_measured.extend(
                    [v for v in self.effective_df.columns if v.startswith('Operational')]
                )
        return self._non_measured

    def df_with_outcome(self):
        return pd.concat([self.df, self.binary_outcome], axis=1)


class Takens:
    def __init__(self, pds: pd.Series):
        self.pds = pds
        self._df = None

    def __repr__(self):
        return f'{__name__}.{self.__class__.__name__}(pds={self.pds.name})'

    def df(self, new=False, **kwargs):
        if new:
            logger.debug(f'kwargs: {kwargs}')
            self._df = self.embed(**kwargs)
        return self._df

    def embed(self, m, tau, time_unit, reverse):
        n = self.pds.shape[0]

        if reverse:
            data = deque()
            index = self.pds.index[range(m * tau - 1, n)]

            for i in range(n - 1, tau * m - 2, -1):
                indices = [v for v in range(i, i - m * tau, -tau)]
                data.appendleft(self.pds.iloc[indices].to_list())

        else:
            data = []
            index = self.pds.index[range(n - tau * (m - 1))]
            for i in range(n - tau * (m - 1)):
                indices = [v for v in range(i, i + m * tau, tau)]
                data.append(self.pds.iloc[indices].to_list())

        logger.debug(f'index: {index}')

        ret = pd.DataFrame(data=data,
                           columns=self.set_columns(m, tau, time_unit, reverse),
                           index=index)
        logger.debug(f'{self.__class__.__name__} embeded matrix shape {ret.shape}')
        return ret

    def set_columns(self, m: int, tau: int, time_unit: str, reverse: bool):
        """
            m ... embed dimension
            tau ... delay
            reverse ... if True, start from the bottom of the data

        """
        ret = [self.pds.name]
        for j in range(1, m):
            n = j * tau
            label = f'{self.pds.name}'
            if reverse:
                label += ' -'
            else:
                label += ' +'
            label += f' {n} {time_unit}'
            if n > 1:
                label += 's'
            ret.append(label)
        logger.debug(f'columns: {ret}')
        return ret

    def summarize(self, **kwargs):
        # Create new matrix
        _ = self.df(new=True, **kwargs)
        return [self.transform(np.mean, **kwargs), self.transform(np.std, **kwargs)]

    def transform(self, func=None, **kwargs):
        if func is None:
            return self._df
        else:
            ret = self.df().copy().apply(func, axis=1)
            m = kwargs.get('m')
            time_unit = kwargs.get('time_unit')
            tau = kwargs.get('tau')
            ret.name = f'{func.__name__.title()} {self.df().columns[0]} over {m} {time_unit}s'
            if tau > 1:
                ret.name += ', delay {tau}'
            return ret
