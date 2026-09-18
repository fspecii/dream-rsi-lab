import urllib.parse

def query_values(query):
    result = {}
    if not query:
        return result
    if query.startswith("?"):
        query = query[1:]
    parts = query.split("&")
    for part in parts:
        if="":
            continue
        try:
            key, value = part.split("=", 1)
            if key in result:
                result[key].append(value)
            else:
                result[key] = [value]
        except ValueError:
            # Handle cases where '=' is missing, or part is malformed
            pass
    return result
