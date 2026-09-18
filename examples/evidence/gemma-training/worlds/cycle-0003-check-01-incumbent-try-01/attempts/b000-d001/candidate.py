import json

def deduplicate(events):
    seen_ids = set()
    result = []
    for event in events:
        if event.get("id") not in seen_ids:
            seen_ids.add(event.get("id"))
            result.append(event)
    return result

if __name__ == '__main__':
    events1 = [{"id": "a", "v": 1}, {\