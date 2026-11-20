"""Minimize simulated CI time across workers."""

from heapq import heapify, heapreplace

MAX_WORKERS = 8
WORKER_COST_MS = 2_000


def schedule(tests: list[dict]) -> list[list[int]]:
    """Balance each allowed worker count and retain the cheapest schedule."""
    if not tests:
        return []

    durations = [(round(test["seconds"] * 1_000), test["number"]) for test in tests]
    durations.sort(key=lambda test: test[0], reverse=True)
    total = sum(duration for duration, _ in durations)
    longest = durations[0][0]
    best_workers = []
    best_cost = total + MAX_WORKERS * WORKER_COST_MS + 1
    for worker_count in range(1, min(MAX_WORKERS, len(durations)) + 1):
        mean_ceiling = (total + worker_count - 1) // worker_count
        minimum_cost = max(longest, mean_ceiling) + worker_count * WORKER_COST_MS
        if minimum_cost >= best_cost:
            continue

        workers = [[number] for _, number in durations[:worker_count]]
        loads = [
            (duration, index)
            for index, (duration, _) in enumerate(durations[:worker_count])
        ]
        heapify(loads)
        for duration, number in durations[worker_count:]:
            load, index = loads[0]
            workers[index].append(number)
            heapreplace(loads, (load + duration, index))

        cost = max(load for load, _ in loads) + worker_count * WORKER_COST_MS
        if cost < best_cost:
            best_workers = workers
            best_cost = cost

    return best_workers
