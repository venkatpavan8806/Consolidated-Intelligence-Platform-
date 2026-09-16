"""
Burner-SIM rotation detector: phone A is active with a substantial, stable
contact set, then goes silent; phone B activates within days with strong
contact-set overlap; A and B never call each other directly.

Uses a MINIMUM contact-set size and a MINIMUM absolute shared-contact count
(not just a Jaccard ratio) to avoid flagging coincidental overlap between
small, sparse clusters -- two low-degree unrelated phones can trivially hit
a high Jaccard ratio by sharing one contact out of two. Checked in BOTH
chronological directions: which phone is "earlier" is decided by comparing
actual activity timestamps, never by phone-number string/iteration order
(see gotcha #5).
"""
from datetime import datetime
from collections import defaultdict

from app.config import (
    BURNER_MIN_CONTACT_SET_SIZE, BURNER_MIN_SHARED_CONTACTS,
    BURNER_MIN_JACCARD, BURNER_MAX_GAP_DAYS,
)

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    return datetime.strptime(ts, FMT)


def _build_phone_activity(conn):
    contacts = defaultdict(set)
    activity = defaultdict(list)
    direct_pairs = set()
    for row in conn.execute("SELECT caller, callee, timestamp FROM cdr_records").fetchall():
        a, b, ts = row["caller"], row["callee"], row["timestamp"]
        contacts[a].add(b)
        contacts[b].add(a)
        activity[a].append(ts)
        activity[b].append(ts)
        direct_pairs.add((a, b))
        direct_pairs.add((b, a))
    return contacts, activity, direct_pairs


def detect_burner_rotation(conn):
    contacts, activity, direct_pairs = _build_phone_activity(conn)
    candidates = [p for p, c in contacts.items() if len(c) >= BURNER_MIN_CONTACT_SET_SIZE]

    results = []
    seen_pairs = set()
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a, b = candidates[i], candidates[j]
            if (a, b) in direct_pairs:
                continue  # A and B must never call each other directly
            pair_key = tuple(sorted((a, b)))
            if pair_key in seen_pairs:
                continue

            shared = contacts[a] & contacts[b]
            union = contacts[a] | contacts[b]
            jaccard = len(shared) / len(union) if union else 0.0
            if len(shared) < BURNER_MIN_SHARED_CONTACTS or jaccard < BURNER_MIN_JACCARD:
                continue

            a_times = sorted(_parse(t) for t in activity[a])
            b_times = sorted(_parse(t) for t in activity[b])
            a_min, a_max = a_times[0], a_times[-1]
            b_min, b_max = b_times[0], b_times[-1]

            # Explicitly check both chronological directions -- do not infer
            # order from phone-number sort order (gotcha #5).
            direction = None
            gap_days = None
            if a_max <= b_min:
                direction = "A_THEN_B"
                gap_days = (b_min - a_max).days
            elif b_max <= a_min:
                direction = "B_THEN_A"
                gap_days = (a_min - b_max).days
            else:
                continue  # overlapping activity windows: not a clean rotation

            if gap_days > BURNER_MAX_GAP_DAYS:
                continue

            seen_pairs.add(pair_key)
            earlier, later = (a, b) if direction == "A_THEN_B" else (b, a)
            results.append({
                "phone_earlier": earlier,
                "phone_later": later,
                "shared_contact_count": len(shared),
                "jaccard": round(jaccard, 3),
                "gap_days": gap_days,
                "earlier_last_active": (a_max if direction == "A_THEN_B" else b_max).strftime(FMT),
                "later_first_active": (b_min if direction == "A_THEN_B" else a_min).strftime(FMT),
                "shared_contacts": sorted(shared),
            })
    return results
