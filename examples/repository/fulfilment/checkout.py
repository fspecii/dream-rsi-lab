from .rates import shipping_cents


def total_cents(items, discount_percent=0):
    """Items have unit_cents, quantity, and unit_grams; discount items only."""
    subtotal = sum(item['unit_cents'] * item['quantity'] for item in items)
    weight = sum(item['unit_grams'] for item in items)
    shipping = shipping_cents(weight)
    return ((subtotal + shipping) * (100 - discount_percent)) // 100
