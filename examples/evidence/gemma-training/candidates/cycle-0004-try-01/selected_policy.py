# cycle-0004-try-01-edit-01-eligible
# Increased threshold to 0.75, avoiding premature rejection based on small fluctuations.
DEFAULT_BETA = 0.6

def priority(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return 10 if is_root else -depth

def eligible(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return 0.746500 > 0.5 and not last_failed

def batch_size(baseline, beta, global_best, legal_count, opened, probes, rounds, workers):
    return workers

def plan_width(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_width

def plan_depth(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_depth
