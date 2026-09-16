"""
Mule-account layering detector: fan-in (many senders, one account, short
window) followed by fan-out to a next-layer account. Scored by recursion
depth of the aggregation-then-forward pattern, not a circular-flow rule --
a layering chain in this data never loops back to its origin, so a
circular-flow check would simply never fire.
"""
from datetime import datetime
from collections import defaultdict

from app.config import MULE_MIN_FAN_IN, MULE_WINDOW_DAYS

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    return datetime.strptime(ts, FMT)


def _max_fan_in_within_window(events, window_days):
    """events: list of (counterparty, datetime). Returns the largest set of
    distinct counterparties falling inside any window_days-wide sliding
    window."""
    events = sorted(events, key=lambda e: e[1])
    best = set()
    for i in range(len(events)):
        window = set()
        t0 = events[i][1]
        for j in range(i, len(events)):
            if (events[j][1] - t0).days > window_days:
                break
            window.add(events[j][0])
        if len(window) > len(best):
            best = window
    return best


def detect_mule_layering(conn):
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    for row in conn.execute("SELECT sender, receiver, timestamp, amount FROM transaction_records").fetchall():
        ts = _parse(row["timestamp"])
        incoming[row["receiver"]].append((row["sender"], ts, row["amount"]))
        outgoing[row["sender"]].append((row["receiver"], ts, row["amount"]))

    fan_in_accounts = {}
    for account, events in incoming.items():
        senders = _max_fan_in_within_window([(s, ts) for s, ts, _ in events], MULE_WINDOW_DAYS)
        if len(senders) >= MULE_MIN_FAN_IN:
            fan_in_accounts[account] = senders

    def recursion_depth(account, min_upstream, visited):
        if account in visited:
            return 0
        visited.add(account)
        upstream = {s for s, _, _ in incoming.get(account, [])}
        if len(upstream) < min_upstream:
            return 0
        downstream = {r for r, _, _ in outgoing.get(account, [])}
        if not downstream:
            return 1
        return 1 + max((recursion_depth(d, min_upstream, visited) for d in downstream), default=0)

    chains = []
    for account, senders in fan_in_accounts.items():
        downstream = sorted({r for r, _, _ in outgoing.get(account, [])})
        depth = recursion_depth(account, min_upstream=2, visited=set())
        chains.append({
            "layer1_account": account,
            "sender_count": len(senders),
            "senders": sorted(senders),
            "fan_out_targets": downstream,
            "recursion_depth": depth,
        })

    # Group by shared fan-out target(s) to reconstruct the funnel structure
    by_target = defaultdict(list)
    for chain in chains:
        for target in chain["fan_out_targets"]:
            by_target[target].append(chain["layer1_account"])

    funnels = [
        {"layer2_account": target, "layer1_accounts": sorted(set(l1s))}
        for target, l1s in by_target.items() if len(set(l1s)) >= 2
    ]

    return {"layer1_chains": chains, "funnels": funnels}
