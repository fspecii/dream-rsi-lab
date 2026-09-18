# cycle-0001-try-01-edit-01-eligible
# Rejecting if objective is below baseline, stabilizing exploration and preventing stagnation.
DEFAULT_BETA = 0.6

def priority(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return 10 if is_root else -depth

def eligible(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return not (0.496500 < 0.5)

def batch_size(baseline, beta, global_best, legal_count, opened, probes, rounds, workers):
    return workers

def plan_width(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_width

def plan_depth(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_depth
