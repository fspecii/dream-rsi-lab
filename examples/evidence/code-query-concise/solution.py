def query_values(query):
    result = {}
    if not query:
        return result
    if query.startswith('?'):
        query = query[1:]
    parts = query.split('&')
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            if key in result:
                result[key].append(value)
            else:
                result[key] = [value]
        elif part:
            if part in result:
                result[part].append('')
            else:
                result[part] = ['']
    return result