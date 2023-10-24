from importlib.metadata import PackageNotFoundError, version
from tagbiopy.logging import initialize_logger


logger = initialize_logger()

DEFAULT_HOST = 'http://localhost:8000'
DOMAIN = 'tag.bio'
KUNG = 'fc-svc'
KUNG_CAPACITORS = 'kung-services/db/capacitors'


try:
    # Change here if project is renamed and does not equal the package name
    dist_name = __name__
    __version__ = version(dist_name)
    msg = f'{dist_name}, version {__version__}'
    logger.info(msg)
except PackageNotFoundError:
    __version__ = "unknown"
finally:
    del version, PackageNotFoundError
