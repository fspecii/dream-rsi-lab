import urllib.parse

def query_values(query):
    if query.startswith('?'):
        query = query[1:]
    return dict((k, [urllib.parse.unquote(v) for v in vs]) for k, vs in urllib.parse.parse_qs(query).items())