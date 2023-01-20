import logging


LOG_FORMAT = '{asctime} {levelname} {name} {module}.{funcName}, line {lineno}: {message}'
LOGGER_NAME = __package__


__all__ = ['initialize_logger', 'LOGGER_NAME']


def _create_log_file():
    import datetime
    import tempfile

    time_stamp = datetime.datetime.now().strftime('%F %X').replace(':', '-').replace(' ', '_')
    prefix = f"{__package__}_{time_stamp}_"

    _, log_file = tempfile.mkstemp(prefix=prefix, suffix='.log')

    return log_file


def initialize_logger(name=LOGGER_NAME, level=logging.DEBUG, fmt=LOG_FORMAT, info=False):
    """
    Use to set logging to a temp file.
    :param name: str, default global
    :param level: str, default debug
    :param fmt: str, default global
    :param info: Bool, default false. If set to true, print the path to
    :return: logger handle
    """

    logger = logging.getLogger(name)
    logger.setLevel(level)
    formatter = logging.Formatter(fmt=fmt, style='{')

    log_file = _create_log_file()

    handler = logging.FileHandler(log_file)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if info:
        print(f'Logger: {name!r}, log file: {log_file}', flush=True)

    # Send warnings to the logger, as well
    logging.captureWarnings(True)

    return logger
