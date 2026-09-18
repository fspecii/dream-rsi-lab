import json

def deduplicate(events):
    seen_ids = set()
    result = []
    for event in events:
        if event["id"] not in seen_ids:
            seen_ids.add(event["id"])  # Add the id to the set
            result.append(event)
    return result


if __name__ == '__main__':
    # Test case
    events = [{