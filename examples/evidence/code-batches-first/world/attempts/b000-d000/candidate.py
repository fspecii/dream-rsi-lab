def batches(items, size):
    result = []
    i = 0
    while i < len(items) - (size if items else 0) + 1:
        if i >= len(items):
            break
        chunk = items[i:i+size]
        result.append(chunk)
        i += size
    return result