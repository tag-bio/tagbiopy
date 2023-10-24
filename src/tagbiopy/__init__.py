# -*- coding: utf-8 -*-
import importlib.metadata
from tagbiopy.logging import initialize_logger


logger = initialize_logger()
version_string = None

DEFAULT_HOST = 'http://localhost:8000'
DOMAIN = 'tag.bio'
KUNG = 'fc-svc'
KUNG_CAPACITORS = 'kung-services/db/capacitors'

try:
    # Change here if project is renamed and does not equal the package name
    dist_name = __name__
    version_string = importlib.metadata.distribution(dist_name).version
    msg = f'{dist_name}, version {version_string}'
    logger.info(msg)
except importlib.metadata.PackageNotFoundError:
    pass
