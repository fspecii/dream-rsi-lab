import urllib.parse

def query_values(query):
    if query.startswith('?'):
        query = query[1:]
    return dict(urllib.parse.parse_qsl(query, keep_blank_values=True, encoding='utf-8'))
