import json

def flatten_config(obj, parent_key='', sep='.'):
    items = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f'{parent_key}{sep}{k}' if parent_key else k
            items.update(flatten_config(v, new_key, sep=sep))
    else:
        items[parent_key] = obj
    return items

flatten_config = flatten_config