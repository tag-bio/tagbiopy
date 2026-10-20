from tagbiopy.logging import initialize_logger


logger = initialize_logger()

# Single source of truth for the package version (read by setup.cfg via
# `version = attr: tagbiopy.__version__`). Bump this per change, like the R SDK's DESCRIPTION.
__version__ = "1.1.10"

DEFAULT_HOST = 'http://localhost:8000'
DOMAIN = 'tag.bio'
KUNG = 'fc-svc'
KUNG_CAPACITORS = 'kung-services/db/capacitors'

logger.info(f'tagbiopy version {__version__}')


def list_data_products(host=None, api_key=None, token=None):
    """The data products on a Tag.bio cluster (see tagbiopy.fc.list_data_products)."""
    from tagbiopy.fc import list_data_products as _list_data_products
    return _list_data_products(host=host, api_key=api_key, token=token)
