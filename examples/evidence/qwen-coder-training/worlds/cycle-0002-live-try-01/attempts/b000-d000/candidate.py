from functools import cmp_to_key


def merge_intervals(intervals):
    if not intervals:
        return []

    def compare(a, b):
        return a[0] - b[0]

    intervals.sort(key=cmp_to_key(compare))
    merged = [intervals[0]]

    for current in intervals[1:]:
        last_merged = merged[-1]
        if current[0] <= last_merged[1]:
            merged[-1] = [last_merged[0], max(last_merged[1], current[1])]
        else:
            merged.append(current)

    return merged
