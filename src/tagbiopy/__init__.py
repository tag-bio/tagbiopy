from tagbiopy.logging import initialize_logger


logger = initialize_logger()

# Single source of truth for the package version (read by setup.cfg via
# `version = attr: tagbiopy.__version__`). Bump this per change, like the R SDK's DESCRIPTION.
__version__ = "1.0.9"

DEFAULT_HOST = 'http://localhost:8000'
DOMAIN = 'tag.bio'
KUNG = 'fc-svc'
KUNG_CAPACITORS = 'kung-services/db/capacitors'

logger.info(f'tagbiopy version {__version__}')
