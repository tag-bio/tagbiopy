# -*- coding: utf-8 -*-
from pkg_resources import get_distribution, DistributionNotFound

from tagbiopy.logging import initialize_logger


logger = initialize_logger()

try:
    # Change here if project is renamed and does not equal the package name
    dist_name = __name__
    __version__ = get_distribution(dist_name).version
    msg = f'{dist_name}, version {__version__}'
    logger.info(msg)
except DistributionNotFound:
    __version__ = 'unknown'
finally:
    del get_distribution, DistributionNotFound
