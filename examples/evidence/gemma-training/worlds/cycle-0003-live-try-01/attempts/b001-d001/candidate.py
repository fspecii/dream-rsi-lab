import heapq

def merge_intervals(intervals):
    if not intervals:
        return []

    heap = []
    for interval in intervals:
        heapq.heappush(heap, (interval[0], interval))

    merged = []
    while heap:
        start, interval = heapq.heappop(heap)
        if not merged or start > merged[-1][1]:
            merged.append(interval)
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], interval[1]))

    return merged
