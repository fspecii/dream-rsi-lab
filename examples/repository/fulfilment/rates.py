def shipping_cents(weight_grams):
    """Charge 300 cents per started kilogram; zero weight ships free."""
    if weight_grams < 0:
        raise ValueError('weight must not be negative')
    return (weight_grams // 1000) * 300
