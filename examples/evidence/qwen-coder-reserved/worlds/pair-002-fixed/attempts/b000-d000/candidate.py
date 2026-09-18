def encode_runs(lst):
    if not lst:
        return []
    encoded = []
    current_value = lst[0]
    count = 1
    for value in lst[1:]:
        if value == current_value:
            count += 1
        else:
            encoded.append([current_value, count])
            current_value = value
            count = 1
    encoded.append([current_value, count])
    return encoded
