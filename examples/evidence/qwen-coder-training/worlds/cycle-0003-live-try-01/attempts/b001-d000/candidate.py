import operator

def merge_intervals(intervals):
    if not intervals:
        return []

    intervals.sort(key=operator.itemgetter(0))
    merged = [intervals[0]]

    for current in intervals[1:]:
        previous = merged[-1]
        if current[0] <= previous[1]:
            merged[-1] = [previous[0], max(previous[1], current[1])]
        else:
            merged.append(current)

    return merged