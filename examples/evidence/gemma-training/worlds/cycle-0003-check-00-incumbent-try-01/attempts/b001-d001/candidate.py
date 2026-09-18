import math

def retry_delays(base, cap, attempts):
    if attempts <= 0:
        return []
    
    delays = []
    for i in range(attempts):
        delay = min(cap, base * (2**i))
        delays.append(delay)
    return delays
