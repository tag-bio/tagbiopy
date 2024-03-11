import logging

from tagbiopy.utils import create_tmp_file

__all__ = ['create_dev_handler', 'initialize_dev_logger', 'update_dev_logger']


# Logging format
LOG_FORMAT = '{asctime} {levelname} {name} {funcName}, line {lineno}: {message}'
CUSTOM_FORMATTER = logging.Formatter(fmt=LOG_FORMAT, style='{')


# Handlers

def create_dev_handler(filename=None, level=logging.DEBUG):
    """
    Meant for dev logging. Use utils.create_tmp_file as filename and attach it to the
    __package__ logger.
    :param level: int, default logging.DEBUG
    :param filename: str, create utils.create_tmp_file() if None
    :return: logging.FileHandler
    """

    if filename is None:
        filename = create_tmp_file()

    # create file handler to log local dev messages
    handler = logging.FileHandler(filename)
    handler.setLevel(level)
    handler.setFormatter(CUSTOM_FORMATTER)
    return handler


def initialize_dev_logger(name, filename=None, handler_level=logging.DEBUG, logger_level=None, info=False):
    # When handler level is lower than the logger level, no logging is emitted. This fixes the problem
    if logger_level is None:
        logger_level = handler_level

    if handler_level < logger_level:
        logger_level = handler_level

    # create file handler to log local dev messages

    if filename is None:
        filename = create_tmp_file()

    handler = create_dev_handler(filename, level=handler_level)

    logger = logging.getLogger(name)
    # Default level is WARNING, which will suppress INFO and DEBUG messages
    logger.setLevel(level=logger_level)
    logger.addHandler(handler)

    # Send warnings to the logger, as well
    logging.captureWarnings(True)

    if info:
        print(f'Logger at level {logger_level!r}, handler at level {handler_level!r}, '
              f'writing to {filename!r}')


def update_dev_logger(name, new_level=logging.DEBUG):
    logger = logging.getLogger(name)
    if logger.level > new_level:
        logger.level = new_level

    for h in logger.handlers:
        if not isinstance(h, logging.FileHandler):
            continue
        old_level = h.level
        if new_level == old_level:
            logger.debug('No logging level change provided: {old_level!r}')
        else:
            h.setLevel(new_level)
            logger.debug(f'Updated logging level from {old_level} to {new_level}')
