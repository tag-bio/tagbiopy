import logging


from .utils import now, create_temp_file


LOG_FORMAT = '{asctime} {name} {levelname} {module}.{funcName} {threadName}[{thread}] line {lineno}: {message}'
LOGGER_NAME = __package__


def create_log_file():
    prefix = f"{__package__}_{now('_')}_"
    return create_temp_file(prefix=prefix)


def initialize_logger(logger_name=LOGGER_NAME, level=logging.DEBUG, fmt=LOG_FORMAT):

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    formatter = logging.Formatter(fmt=fmt, style='{')

    log_file = create_log_file()

    handler = logging.FileHandler(log_file)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    print('Logger: "{}", log file: {}'.format(logger_name, log_file), flush=True)

    # Send warnings to the logger, as well
    logging.captureWarnings(True)

    return logger
