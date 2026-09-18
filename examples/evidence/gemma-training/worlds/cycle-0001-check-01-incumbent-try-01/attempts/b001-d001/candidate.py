def inventory_delta(before, after):
    """Calculates the inventory delta between two objects, where keys are SKU strings and values are integer counts.
    Missing counts are treated as zero.
    Only nonzero differences are included in the result.
    """
    delta = {}
    for sku in before:
        if sku in after:
            delta[sku] = after[sku] - before[sku]
    return delta
