from typing import Union

from .data_model import block_factory, collection_factory
from .data_model import CategoricalBlock, CategoricalBatchBlock, CategoricalCompoundBlock, CategoricalMatrixBlock
from .data_model import NumericBlock, NumericSliceBlock, NumericMatrixBlock
from .data_model import ALL_BLOCKS, ALL_BLOCKS_STR, COLLECTIONS, VARIABLES
from .data_model import CategoricalCollection, CategoricalMatrixCollection, NumericCollection, NumericMatrixCollection


BlockTypes = Union[CategoricalBlock, NumericBlock, CategoricalMatrixBlock, NumericMatrixBlock]
CollectionTypes = Union[CategoricalCollection, NumericCollection, CategoricalMatrixCollection, NumericMatrixCollection]
MixedTypes = Union[BlockTypes, CollectionTypes]

__all__ = [
  'block_factory', 'collection_factory', 'CategoricalBlock', 
  'CategoricalBatchBlock', 'CategoricalCompoundBlock', 'CategoricalMatrixBlock',
  'NumericBlock', 'NumericSliceBlock', 'NumericMatrixBlock',
  'ALL_BLOCKS', 'ALL_BLOCKS_STR', 'COLLECTIONS',
  'VARIABLES', 'CategoricalCollection', 'CategoricalMatrixCollection', 
  'NumericCollection', 'NumericMatrixCollection', 'BlockTypes', 
  'CollectionTypes', 'MixedTypes'
]