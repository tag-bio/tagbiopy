def list_attributes(instance, include_private=False):
    public_attributes = []
    private_attributes = []
    for k in instance.__dict__:
        if k.startswith('_'):
            private_attributes.append(k)
        else:
            public_attributes.append(k)

    ret = sorted([v for v in public_attributes])
    if include_private:
        ret.extend(sorted([v for v in private_attributes]))
    return ret
