import logging


from .utils import now, create_temp_file


LOG_FORMAT = '{asctime} {name} {levelname} {module}.{funcName} {threadName}[{thread}] line {lineno}: {message}'
LOGGER_NAME = __package__


class MultiprocessHandler(logging.Handler):
    """multiprocessing log handler

    This handler makes it possible for several processes to log to the same
    file by using a queue.

    Shamelessly stolen from https://mattgathu.github.io/multiprocessing-logging-in-python/
    """

    def __init__(self, log_file):
        import multiprocessing
        import threading

        super(MultiprocessHandler, self).__init__()

        self._handler = logging.FileHandler(log_file)
        self.queue = multiprocessing.Queue(-1)

        self._is_closed = False
        self._t = threading.Thread(target=self.receive)
        self._t.daemon = True
        self._t.start()

    def _format_record(self, record: logging.LogRecord):
        if record.args:
            record.msg = record.msg % record.args
            record.args = None
        if record.exc_info:
            _ = self.format(record)
            record.exc_info = None

        return record

    def close(self):
        if not self._is_closed:
            self._t.join(timeout=5.0)
            self._is_closed = True

            self._handler.close()
            super(MultiprocessHandler, self).close()

    def emit(self, record):
        try:
            s = self._format_record(record)
            self.send(s)
        except (KeyboardInterrupt, SystemExit):
            raise

    def setFormatter(self, fmt):
        logging.Handler.setFormatter(self, fmt)
        self._handler.setFormatter(fmt)

    def receive(self):
        while True:
            try:
                record = self.queue.get()
                self._handler.emit(record)
            except (KeyboardInterrupt, SystemExit):
                raise
            except EOFError:
                break

    def send(self, s):
        self.queue.put_nowait(s)


def initialize_logger(logger_name=LOGGER_NAME, level=logging.DEBUG):
    # We send all logs to a log file
    now_ts = now('_')
    prefix = f"tagbio_py_{now_ts}_"
    log_file = create_temp_file(prefix=prefix)
    print('Logger: "{}", log file: {}'.format(logger_name, log_file), flush=True)

    logger = logging.getLogger(logger_name)

    logger.setLevel(level)

    formatter = logging.Formatter(fmt=LOG_FORMAT, style='{')

    # All logging goes to a temp file
    # file_handler = logging.FileHandler(log_file)
    file_handler = MultiprocessHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # We send all errors to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Send warnings to the logger, as well
    logging.captureWarnings(True)

    return logger
