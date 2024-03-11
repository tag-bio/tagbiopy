import logging
import os

from .config import initialize_dev_logger
from .core import FC


# Set up top-level logger. The default level is logging.WARN, which is
# above logging.INFO and logging.DEBUG.
# Dev handlers can be added using tagbiopy.config.logging.initialize_dev_logger.
# Without specifying the filename, logs will go to a tmp file.
logger = logging.getLogger(name=__name__)
print(__name__)

# If debugging dev, log to local tmp file
if os.getenv('TAGBIOPY_DEV_DEBUG') is not None:
    initialize_dev_logger(name=__name__)
