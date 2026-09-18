def batches(items, size):
    if not items or size <= 0:
        return []

    batches_list = []
    for i in range(0, len(items), size):
        batches_list.append(items[i:i+size])

    return batches_list
