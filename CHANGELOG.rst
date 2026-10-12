=========
Changelog
=========

See the project's git history and release tags for the full change record
(the package version is tracked in ``src/tagbiopy/__init__.py``).

2026-10-12 (1.0.12)
===================

* ``tagbiopy.list_data_products()``: the data products on a cluster (the same catalog the Tag.bio UI
  uses); a localhost host lists itself.
* ``FC.list_collection_sets()`` and the ``CollectionSet`` selector: list a product's collection sets
  and pull every collection in one with ``fc.df.select(CollectionSet("Labs")).run()``.
* ``.head(n, seed=1)`` on a query: a reproducible sample of ``n`` entities (matching the filters, or
  all entities).
* ``run(categories=True)``: single_valued categorical columns (from the parquet file metadata) as
  pandas ``category``; the default keeps plain strings.

2026-08-11
==========

* Repository is now public. Contact address for the package is
  ``support@tag.bio``; the ``master`` branch only accepts changes
  through pull requests.
