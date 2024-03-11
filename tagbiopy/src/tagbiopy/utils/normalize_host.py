from tagbiopy.config import DEFAULT_HOST, KUNG


def normalize_host(host=None, fc_name=None):
    if host is None:
        return DEFAULT_HOST
    if not host.startswith('https://'):
        host = f'https://{host}'

    if KUNG not in host:
        host = f'{host}/{KUNG}'

    if fc_name is not None:
        host = f'{host}/{fc_name}'

    return host

