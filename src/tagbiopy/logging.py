import logging

from .utils import create_temp_file, now


LOG_FORMAT = '{asctime} {levelname} {name} {module}.{funcName}, line {lineno}: {message}'
LOGGER_NAME = __package__


__all__ = ['initialize_logger', 'LOGGER_NAME']


def _create_log_file():
    prefix = f"{__package__}_{now('_')}_"
    return create_temp_file(prefix=prefix)


def initialize_logger(name=LOGGER_NAME, level=logging.INFO, fmt=LOG_FORMAT):

    logger = logging.getLogger(name)
    logger.setLevel(level)
    formatter = logging.Formatter(fmt=fmt, style='{')

    log_file = _create_log_file()

    handler = logging.FileHandler(log_file)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    print(f'Logger: {name!r}, log file: {log_file}', flush=True)

    # Send warnings to the logger, as well
    logging.captureWarnings(True)

    return logger
