import logging

import pandas as pd


logger = logging.getLogger(__name__)


def content_to_dataframe(content, index=None, **kwargs) -> pd.DataFrame:
    """Take the TagBioRequest POST content and turn it into a dataframe.
    Set dataframe index to default ('Unique ID'). If no 'Unique ID' column is found
    in the dataframe, return the dataframe with default index.

    There is no size limitation on content, limited by the amount of memory available.

    :param content: requests.post.content
    :param index: str,
    :param kwargs: dict, pd.DataFrame.read_csv parameters
    :return: pd.DataFrame
    """
    import io

    encoded_content = str(content, 'utf-8')
    logger.debug(f'Content encoded to utf-8, reading into a dataframe')
    _df = pd.read_csv(io.StringIO(encoded_content), **kwargs)
    logger.debug(f'Content turned into a {_df.shape} dataframe')

    # Use default index if index not specified
    if index is None:
        index = 'Unique ID'
    try:
        return _df.set_index(index)
    except KeyError as e:
        logger.error(e)
        logger.error(f'Index {index!r} not found among dataframe columns {_df.columns}')
    except AttributeError as e:
        # If we do not get back a pd.DataFrame, raise an exception
        logger.error(e)
        raise
    finally:
        return _df
