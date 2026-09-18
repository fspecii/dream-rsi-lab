# cycle-0003-try-01-edit-02-eligible
# No improvement detected; maintaining roots and justified repairs.
DEFAULT_BETA = 0.6

def priority(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return 10 if is_root else -depth

def eligible(anchor, baseline, beta, depth, failures, gain, global_best, is_root, last_failed, latest, legal_count, opened, probes, remaining, rounds, stagnation, successes, workers):
    return is_root or stagnation < (1 + 2 * beta)

def batch_size(baseline, beta, global_best, legal_count, opened, probes, rounds, workers):
    return workers

def plan_width(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_width if history_count < 2 else max(1, int(hard_width * 0.5))

def plan_depth(beta, hard_depth, hard_width, history_count, last_gain, last_work, plateau_rounds, workers):
    return hard_depth
