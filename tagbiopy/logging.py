

import logging


from tagbiopy.utils import now


LOG_FORMAT = '{asctime} {name} {levelname} {module}.{funcName} line {lineno}: {message}'


def create_log_file(prefix, suffix='.log'):
    import tempfile

    fd, log_file = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    return fd, log_file


def fix_py_warnings_logger(level=logging.DEBUG):
    # Check https://docs.python.org/3.8/library/logging.html#logging.captureWarnings

    logging.captureWarnings(True)

    _, log_file = create_log_file(prefix='py_warnings_{}_'.format(now('_')))

    formatter = logging.Formatter(fmt=LOG_FORMAT, style='{')
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    # Add filehandle to python warning logger
    py_warn_logger = logging.Logger('py.warnings')
    py_warn_logger.addHandler(file_handler)

    # Also set py.warnings to the same file
    return log_file


def initialize_logger(name='connect_tagbio', level=logging.DEBUG):

    # We send all logs to a log file
    _, log_file = create_log_file(prefix='tb_{}_'.format(now('_')))
    print('Python log file: {}'.format(log_file), flush=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter = logging.Formatter(fmt=LOG_FORMAT, style='{')

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    # We send all errors to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Fix py.warnings logger - set its handler to a file
    py_warnings_log_file = fix_py_warnings_logger(level)
    logger.info('Python warnings log file: {}'.format(py_warnings_log_file))

    return logger
