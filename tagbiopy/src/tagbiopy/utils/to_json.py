def to_json(variable_object):
    """
    Use in json.dumps
    :param variable_object: dict
    :return: str
    """
    return variable_object.as_dict
