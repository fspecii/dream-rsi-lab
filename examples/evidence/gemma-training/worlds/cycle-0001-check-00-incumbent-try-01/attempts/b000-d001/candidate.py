import json

def deduplicate(events):
    seen_ids = set()
    result = []
    for event in events:
        if event.get("id") not in seen_ids:
            seen_ids.add(event.get("id"))  # Add the id to the set
            result.append(event)
    return result


if __name__ == '__main__':
    # Test case
    events = [{"id": "a", "v": 1}, {"id": "a", "v": 2}, {"id": "b", "v": 3}] 
    deduplicated_events = deduplicate(events)
    print(json.dumps(deduplicated_events))
