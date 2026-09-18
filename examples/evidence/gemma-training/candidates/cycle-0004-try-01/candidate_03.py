# cycle-0004-try-01-edit-03-batch_size
# Increased batch size to 4 to capture more parallel work, balancing exploration and efficiency.
DEFAULT_BETA = 0.6

def priority(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return 10 if is_root else -depth

def eligible(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return 0.746500 > 0.5 and not last_failed

def batch_size(baseline, beta, global_best, legal_count, opened, probes, rounds, workers):
    return int(min(workers, 4))

def plan_width(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_width

def plan_depth(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_depth
