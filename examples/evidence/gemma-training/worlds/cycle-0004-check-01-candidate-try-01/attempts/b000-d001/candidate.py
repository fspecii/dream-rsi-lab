def retry_delays(base, cap, attempts):
    """Generates exponential backoff delays.

    Args:
        base: The base delay value.
        cap: The maximum delay value.
        attempts: The number of attempts.

    Returns:
        A list of delay values, or an empty list if attempts <= 0.
    """
    if attempts <= 0:
        return []

    delays = []
    for i in range(attempts):
        delay = min(cap, base * (2**i))
        delays.append(delay)
    return delays
