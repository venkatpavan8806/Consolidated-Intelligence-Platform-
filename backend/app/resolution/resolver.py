"""
Entity resolution.

PHONE / ACCOUNT / VEHICLE identifiers are hard identifiers -- every observed
occurrence of the same value (whether in a structured CDR/transaction record
or extracted from FIR text) is the same entity by construction, no fuzzy
matching involved. LOCATION / ORGANIZATION mentions resolve by normalized
text.

PERSON is the hard case: two mentions are auto-merged ONLY when their names
are similar AND a hard identifier (phone/account/vehicle) mentioned in each
mention's own source record resolves to the same canonical entity. When two
name-similar mentions each carry their OWN distinct identifier, that is
positive evidence they are different people (confirmed distinct, e.g. the
planted "two Rajesh Kumars" case) -- no merge, no review needed. Only when at
least one side cannot be confirmed either way do the mentions go into a
single review-queue cluster per connected component (never one row per
pair -- see gotcha #2).
"""
import json
from app.db.schema import get_connection


def normalize_value(v: str) -> str:
    return v.strip()


def normalize_name(name: str):
    return [t.strip(".").lower() for t in name.split() if t.strip(".")]


def names_similar(a: str, b: str) -> bool:
    ta, tb = normalize_name(a), normalize_name(b)
    if not ta or not tb:
        return False
    if ta[0] != tb[0]:
        return False
    if len(ta) != len(tb):
        return False
    for x, y in zip(ta[1:], tb[1:]):
        if x == y:
            continue
        if len(x) == 1 and y.startswith(x):
            continue
        if len(y) == 1 and x.startswith(y):
            continue
        return False
    return True


class EntitySeq:
    def __init__(self):
        self.n = 0

    def next(self, prefix):
        self.n += 1
        return f"ENT_{prefix}_{self.n:06d}"


def _slug(value: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in value.strip().lower())


def run_resolution():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM entities")
    cur.execute("DELETE FROM mention_entity_map")
    cur.execute("DELETE FROM review_queue")

    mentions = [dict(r) for r in cur.execute("SELECT * FROM entity_mentions").fetchall()]
    cdrs = cur.execute("SELECT caller, callee FROM cdr_records").fetchall()
    txns = cur.execute("SELECT sender, receiver FROM transaction_records").fetchall()

    entities = {}  # entity_id -> row dict
    value_to_entity = {}  # (entity_type, normalized_value) -> entity_id
    mention_entity_pairs = []  # (mention_id, entity_id)

    def get_or_create_hard_entity(entity_type: str, raw_value: str) -> str:
        norm = normalize_value(raw_value)
        key = (entity_type, norm)
        if key in value_to_entity:
            return value_to_entity[key]
        eid = f"ENT_{entity_type}_{_slug(norm)}"
        value_to_entity[key] = eid
        entities[eid] = {
            "entity_id": eid, "entity_type": entity_type, "canonical_value": norm,
            "attributes_json": "{}", "is_official": 0, "is_utility": 0,
        }
        return eid

    # --- Hard identifiers observed directly in structured records ---
    for row in cdrs:
        get_or_create_hard_entity("PHONE", row["caller"])
        get_or_create_hard_entity("PHONE", row["callee"])
    for row in txns:
        get_or_create_hard_entity("ACCOUNT", row["sender"])
        get_or_create_hard_entity("ACCOUNT", row["receiver"])

    # --- Hard identifiers + simple-normalized entities extracted from FIR text ---
    person_mentions = []
    for m in mentions:
        if m["entity_type"] in ("PHONE", "ACCOUNT", "VEHICLE"):
            eid = get_or_create_hard_entity(m["entity_type"], m["text"])
            mention_entity_pairs.append((m["mention_id"], eid))
        elif m["entity_type"] in ("LOCATION", "ORGANIZATION"):
            eid = get_or_create_hard_entity(m["entity_type"], m["text"].strip().lower())
            if not entities[eid]["canonical_value"].strip():
                pass
            entities[eid]["canonical_value"] = m["text"].strip()
            mention_entity_pairs.append((m["mention_id"], eid))
        elif m["entity_type"] == "PERSON":
            person_mentions.append(m)

    # identifiers mentioned in the SAME FIR record as a given mention
    mentions_by_record = {}
    for m in mentions:
        mentions_by_record.setdefault(m["source_record_id"], []).append(m)

    def record_identifier_entities(record_id: str):
        ids = set()
        for m in mentions_by_record.get(record_id, []):
            if m["entity_type"] in ("PHONE", "ACCOUNT", "VEHICLE"):
                ids.add(value_to_entity[(m["entity_type"], normalize_value(m["text"]))])
        return ids

    from app.resolution.union_find import UnionFind

    person_ids = [m["mention_id"] for m in person_mentions]
    confirmed_uf = UnionFind(person_ids)
    ambiguous_uf = UnionFind(person_ids)
    ambiguous_pairs_exist = set()

    for i in range(len(person_mentions)):
        for j in range(i + 1, len(person_mentions)):
            mi, mj = person_mentions[i], person_mentions[j]
            if not names_similar(mi["text"], mj["text"]):
                continue
            ids_i = record_identifier_entities(mi["source_record_id"])
            ids_j = record_identifier_entities(mj["source_record_id"])
            if ids_i and ids_j:
                if ids_i & ids_j:
                    confirmed_uf.union(mi["mention_id"], mj["mention_id"])
                else:
                    continue  # confirmed distinct: positive evidence, no merge, no review
            else:
                ambiguous_uf.union(mi["mention_id"], mj["mention_id"])
                ambiguous_pairs_exist.add(mi["mention_id"])
                ambiguous_pairs_exist.add(mj["mention_id"])

    person_seq = EntitySeq()
    mention_to_person_entity = {}
    for group in confirmed_uf.groups():
        eid = person_seq.next("PERSON")
        names = [next(m["text"] for m in person_mentions if m["mention_id"] == mid) for mid in group]
        roles = [next(m["fir_role"] for m in person_mentions if m["mention_id"] == mid) for mid in group]
        entities[eid] = {
            "entity_id": eid, "entity_type": "PERSON",
            "canonical_value": max(names, key=len),
            "attributes_json": json.dumps({
                "all_name_variants": sorted(set(names)),
                "mention_count": len(group),
                "fir_roles": sorted(set(r for r in roles if r)),
            }),
            "is_official": 0, "is_utility": 0,
        }
        for mid in group:
            mention_to_person_entity[mid] = eid
            mention_entity_pairs.append((mid, eid))

    review_clusters = []
    review_seq = EntitySeq()
    seen_ambiguous_roots = set()
    for group in ambiguous_uf.groups():
        if len(group) < 2 or not any(g in ambiguous_pairs_exist for g in group):
            continue
        cluster_id = f"REVIEW_{len(review_clusters) + 1:04d}"
        distinct_entity_ids = sorted(set(mention_to_person_entity[mid] for mid in group))
        review_clusters.append({
            "cluster_id": cluster_id,
            "entity_type": "PERSON",
            "reason": "Name-similar mentions across records without a confirmable shared hard identifier",
            "mention_ids_json": json.dumps(group),
            "status": "PENDING",
        })

    conn2 = conn
    cur2 = conn2.cursor()
    cur2.executemany(
        """INSERT INTO entities (entity_id, entity_type, canonical_value, attributes_json, is_official, is_utility)
           VALUES (:entity_id, :entity_type, :canonical_value, :attributes_json, :is_official, :is_utility)""",
        list(entities.values()),
    )
    cur2.executemany(
        "INSERT OR IGNORE INTO mention_entity_map (mention_id, entity_id) VALUES (?, ?)",
        mention_entity_pairs,
    )
    cur2.executemany(
        """INSERT INTO review_queue (cluster_id, entity_type, reason, mention_ids_json, status)
           VALUES (:cluster_id, :entity_type, :reason, :mention_ids_json, :status)""",
        review_clusters,
    )
    conn2.commit()
    conn2.close()

    return {
        "entities_created": len(entities),
        "person_entities": sum(1 for e in entities.values() if e["entity_type"] == "PERSON"),
        "review_clusters": len(review_clusters),
    }


if __name__ == "__main__":
    print(json.dumps(run_resolution(), indent=2))
