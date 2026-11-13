=========
Changelog
=========

See the project's git history and release tags for the full change record
(the package version is tracked in ``src/tagbiopy/__init__.py``).

2026-11-13 (1.1.16)
===================

* ``connect_tagbio_py --worker`` runs the FC engine's warm plugin worker (``tagbiopy.worker``): one long-lived
  process that imports the SDK and its common libraries once and runs each plugin job in a fresh forked child
  (its own working directory, output files and random state). The engine starts it itself (``plugin_workers``
  server argument, default on); plugins need no change. Running ``connect_tagbio_py`` for a single plugin is
  unchanged.

2026-11-12 (1.1.15)
===================

* Python reports get the Tag.bio report page of R Markdown apps (``tagbio::tag_report``): the header with title,
  user, date, data date and app link, a numbered table of contents, Barlow fonts and the same styling, in one
  self-contained HTML file. ``ipynb_to_html()`` produces it by default (title = ``title`` or the notebook's first
  heading); ``plain=True`` gives the previous plain nbconvert page, which is also
  written if building the report page fails. ``.py`` plugins that write their own HTML can
  call ``tagbiopy.report.tag_report(body_html, title, output_file=tag_result.path)``, and
  ``tagbiopy.report.insert_banner()`` adds a notice at the top of a report's content.
* ``nbconvert`` is now a declared dependency, in ``environment.yml`` and ``setup.cfg`` (``ipynb_to_html`` imports it).

2026-10-30 (1.1.14)
===================

* ``data_dictionary()`` describes matrix collections: their variables (``CRP: <column>``, one column per header
  such as a time point), entity counts, and ``kind`` = ``number`` (numeric matrices, and categorical matrices,
  whose one-hot cells download as 1/0). ``variables=True`` lists a matrix's variables.

2026-10-29 (1.1.13)
===================

* ``FC.data_dictionary()`` describes a data product's data model as a DataFrame, one row per collection: its column
  name(s) in a pull, data type, kind (text, number, date or logical), single- or multi-valued, value and entity
  counts, the values of small categoricals, and its collection sets. ``variables=True`` lists one row per variable
  for named collections or a collection set. Only metadata is fetched. The product's name, title, entity names
  and entity count are in ``.attrs['data_product']``. It matches the FC's MCP ``fc://data-model`` resource.
  A numeric collection with more than ``max_levels`` (20) variables shows its column name pattern,
  e.g. ``Copy Number: <variable> (24,813 variables)``, instead of listing every column.
* ``list_collection_set_members()`` no longer fails on compound collection names.

2026-10-28 (1.1.12)
===================

* Logical collections (marked by the engine and written as native Parquet booleans) come back with pandas'
  nullable ``boolean`` dtype, with or without missing values.
* ``categories=True`` converts only text columns; date and logical columns keep their own types.

2026-10-20 (1.1.10)
===================

* The ``datetimes`` argument is retired: ``run()``, ``to_dataframe()``, ``get_df()`` and
  ``content_to_dataframe()`` no longer list it. Calls that still pass it keep working; it is ignored with a
  deprecation warning in the log. Remove it from your code: a future version will reject it.

2026-10-15 (1.1.9)
==================

* Dates are always dates: with engine 2.100.2, every date column from a datetime parser arrives as a UTC
  datetime from ``run()``, ``.df`` and ``get_df()``. The ``datetimes`` argument is accepted but ignored.
  Against older engines, those columns arrive as plain numbers / ``yyyy/MM/dd`` text.

2026-10-14 (1.1.8)
==================

* Plugins get dates by default: a plugin's ``.df`` and ``get_df()`` turn date columns into UTC
  datetimes (archives built on engine 2.99.37+). ``get_df(datetimes=False)`` keeps the raw values.
  ``FC.run()`` and queries are unchanged.

2026-10-13 (1.1.2)
==================

* ``run(datetimes=True)`` also converts day-level dates: ``timestamp-days`` numerics and
  ``year-month-day`` labels become datetimes (UTC midnight, so they compare directly with timestamp
  columns), using the date kinds the engine records (2.99.37+); it no longer makes an extra lookup
  when the export already carries them.
* ``select(("Collection", "Variable"))`` tuples now select a numeric variable (previously never matched).

2026-10-12 (1.1.1)
==================

* ``tagbiopy.list_data_products()``: the data products on a cluster (the same catalog the Tag.bio UI
  uses); a localhost host lists itself.
* ``FC.list_collection_sets()`` and the ``CollectionSet`` selector: list a product's collection sets
  and pull every collection in one with ``fc.df.select(CollectionSet("Labs")).run()``.
* ``.head(n, seed=1)`` on a query: a reproducible sample of ``n`` entities (matching the filters, or
  all entities).
* ``run(categories=True)``: single_valued categorical columns (from the parquet file metadata) as
  pandas ``category``; the default keeps plain strings.
* ``run(datetimes=True)``: numeric columns the FC flags ``is_timestamp`` as UTC datetimes, whatever the
  server's native_timestamps setting; the default keeps epoch milliseconds.

2026-08-11
==========

* Repository is now public. Contact address for the package is
  ``support@tag.bio``; the ``master`` branch only accepts changes
  through pull requests.
