import os
import logging

logger = logging.getLogger(__name__)


def load_config(filename=None):
    print(f'filename = {filename}, endswith.json {filename.endswith("json")}')

    if filename is None:
        return {}
    else:
        if filename.endswith('.json'):
            import json
            with open(filename) as fh:
                s = json.load(fh)
            return s

        elif filename.endswith('.yaml') or filename.endswith('.yml'):
            import yaml

            with open(filename) as fh:
                s = yaml.safe_load(fh)

            return s

        else:
            raise ValueError(f'Invalid format, config file should be either json or yaml: {filename}')
