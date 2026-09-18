# cycle-0001-try-01-edit-02-priority
# Adjust ranking to balance productive and underexplored directions by incorporating stagnation.
DEFAULT_BETA = 0.6

def priority(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return (anchor - baseline) + beta / (depth + 1) - stagnation

def eligible(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return True

def batch_size(baseline, beta, global_best, legal_count, opened, probes, rounds, workers):
    return workers

def plan_width(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_width

def plan_depth(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_depth
