def merge_intervals(intervals):
    if not intervals:
        return []

    intervals.sort(key=lambda x: x[0])  # Sort intervals based on start time

    merged_intervals = []
    current_interval = intervals[0]

    for interval in intervals[1:]:
        if interval[0] <= current_interval[1]:  # Overlapping or touching
            current_interval[1] = max(current_interval[1], interval[1])  # Merge
        else:
            merged_intervals.append(current_interval)
            current_interval = interval

    merged_intervals.append(current_interval)  # Add the last interval

    return merged_intervals
