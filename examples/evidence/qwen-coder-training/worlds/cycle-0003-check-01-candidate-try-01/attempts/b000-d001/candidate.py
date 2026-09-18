import copy

def deduplicate(events):
    seen = set()
    result = []
    for event in events:
        if event['id'] not in seen:
            seen.add(event['id'])
            result.append(event)
    return result