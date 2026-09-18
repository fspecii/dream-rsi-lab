# Split items into consecutive lists of at most size items.
# Includes any short final list. Empty items gives [].
# A nonpositive size gives []. Do not modify items.

from typing import List, Any


def batches(items: List[Any], size: int) -> List[List[Any]]:
    """
    Split a list of items into consecutive sublists of at most `size` elements.
    
    - Returns an empty list if `size` is 0 or negative (nonpositive).
    - Includes any resulting short final list.
    - Does not modify the original input list.
    """
    if size <= 0:
        return []
    
    result = []
    i = 0
    length = len(items)
    while i < length:
        # Calculate how many full chunks fit before reaching end of items
        max_index = i + size - 1
        if max_index >= length:
            break
        
        chunk = items[i:i+size]
        result.append(chunk)
        i += size
    
    return result