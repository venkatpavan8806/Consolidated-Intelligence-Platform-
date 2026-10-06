"""
Populates common_identifier_index (see app/db/schema.py's original
comment: "populated incrementally as each case-type module is built" --
this is that backfill, tracked as its own pipeline stage per the schema
comment's own instruction, rather than folded silently into another
stage).

Sources indexed, each with real provenance (FIR number, police station,
date) rather than a bare value:
  - PHONE entities mentioned in an FIR -> MSISDN
  - ACCOUNT entities mentioned in an FIR -> ACCOUNT
  - VEHICLE entities mentioned in an FIR -> VEHICLE_REG
  - PERSON entities mentioned in an FIR with fir_role='ACCUSED' -> ACCUSED_ID
    (the canonical resolved entity_id, not the raw name text, so two
    spellings of the same accused already collapse to one identifier the
    same way entity resolution collapses them everywhere else)

This is deliberately FIR-mention-driven, not a redesign of entity
resolution -- it reuses exactly what extraction/resolution already
produced. IMEI/IMSI/VPA are listed in the research pass's own recommended
field set but have no source in this system yet (no seized-device or UPI
transaction records carry them), so they are honestly left unindexed
rather than backfilled from data that doesn't exist.
"""
import hashlib


_ENTITY_TYPE_TO_IDENTIFIER_TYPE = {"PHONE": "MSISDN", "ACCOUNT": "ACCOUNT", "VEHICLE": "VEHICLE_REG"}


def _identifier_id(identifier_type, value, fir_id):
    digest = hashlib.sha256(f"{identifier_type}:{value}:{fir_id}".encode()).hexdigest()[:16]
    return f"CII_{digest}"


def backfill_common_identifier_index(conn):
    """Rebuilds common_identifier_index from scratch from the current
    entity_mentions/entities/fir_records state -- safe to re-run any
    number of times (DELETE + re-insert), since it derives everything
    from already-persisted extraction/resolution output rather than
    accumulating its own state."""
    conn.execute("DELETE FROM common_identifier_index")

    rows = conn.execute(
        """SELECT em.entity_type, em.fir_role, mem.entity_id, e.canonical_value,
                  fr.case_id, fr.fir_id, fr.station, fr.date
           FROM entity_mentions em
           JOIN mention_entity_map mem ON em.mention_id = mem.mention_id
           JOIN entities e ON mem.entity_id = e.entity_id
           JOIN fir_records fr ON em.source_record_id = fr.fir_id AND em.source_type = 'FIR'
           WHERE em.entity_type IN ('PHONE', 'ACCOUNT', 'VEHICLE')
              OR (em.entity_type = 'PERSON' AND em.fir_role = 'ACCUSED')"""
    ).fetchall()

    seen = set()
    to_insert = []
    for r in rows:
        if r["entity_type"] == "PERSON":
            identifier_type, value = "ACCUSED_ID", r["entity_id"]
        else:
            identifier_type = _ENTITY_TYPE_TO_IDENTIFIER_TYPE[r["entity_type"]]
            value = r["canonical_value"]

        key = (identifier_type, value, r["fir_id"])
        if key in seen:
            continue
        seen.add(key)
        to_insert.append((
            _identifier_id(identifier_type, value, r["fir_id"]), identifier_type, value, r["case_id"],
            "FIR", r["fir_id"], r["fir_id"], r["station"], r["date"],
        ))

    conn.executemany(
        "INSERT INTO common_identifier_index (identifier_id, identifier_type, value, case_id, "
        "source_record_type, source_record_id, fir_no, police_station, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        to_insert,
    )
    conn.commit()
    return {"identifiers_indexed": len(to_insert)}
