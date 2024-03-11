def create_tmp_file(prefix=None, suffix='.log'):
    import tempfile

    if prefix is None:
        import datetime

        time_stamp = datetime.datetime.now().strftime('%F %X') \
            .replace(':', '-') \
            .replace(' ', '_')
        prefix = f"{__name__}_{time_stamp}_"

    _, tmp_file = tempfile.mkstemp(suffix=suffix, prefix=prefix)

    return tmp_file
