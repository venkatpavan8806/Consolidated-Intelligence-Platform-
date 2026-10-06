"""
IMEI<->MSISDN device-continuity mapping, plus GSM-vs-IP call-type awareness
-- a mentor-requested feature, grounded directly in the research pass's own
DE-C findings for CDR/IPDR analysis:

  "IMEI from suspect's handset seen with a different SIM near the time ->
   SIM-swap-to-evade flag"
  "Same IMEI active with a new SIM after the missing-date -> device-
   continuity lead; cross-check against CEIR if device is reported lost"

A real Indian-TSP CDR carries an IMEI alongside the MSISDN precisely
because a handset (the physical device) and a SIM (the subscriber
identity) are two different things that investigators need to correlate:
the same person swapping SIMs to evade surveillance keeps using the same
physical handset, and that handset's IMEI is the thread that survives the
SIM swap. This is a stronger, device-level signal than
app.detectors.burner_sim's purely social (shared-contact-set) heuristic --
the two are complementary, not competing, which is why
detect_imei_corroborated_burner_rotation below cross-checks one against
the other rather than replacing it.

call_type (GSM_CALL vs IP_CALL) is carried through into every finding here
as an honesty signal, not a separate rule: an IP_CALL (an OTT/VoIP call
carried over data, captured -- if at all -- only in a separate IPDR, not a
voice CDR) does not produce the same reliable tower trail a GSM_CALL does,
so a device-continuity finding built mostly from IP_CALL rows is flagged
as weaker corroboration for that reason, never silently treated the same
as a GSM-voice-backed one.

Every finding here is a candidate for a human investigator to check
against the case file -- shared-handset usage is never itself an identity
claim, exactly like every other detector in this system.
"""
from collections import defaultdict
from datetime import datetime

from app.config import IMEI_MAPPING_MIN_DISTINCT_MSISDN

FMT = "%Y-%m-%dT%H:%M:%S"


def _parse(ts):
    return datetime.strptime(ts, FMT)


def detect_imei_msisdn_mapping(conn):
    """Groups CDR rows by IMEI (both caller- and callee-side, since either
    side of a merged multi-operator export may carry it) and returns every
    IMEI used by >= IMEI_MAPPING_MIN_DISTINCT_MSISDN distinct phone
    numbers, with full provenance (which MSISDN, which record, when, and
    whether that record was a GSM_CALL or an IP_CALL)."""
    by_imei = defaultdict(lambda: defaultdict(list))  # imei -> msisdn -> [occurrence,...]

    rows = conn.execute(
        "SELECT record_id, caller, callee, timestamp, caller_imei, callee_imei, call_type FROM cdr_records"
    ).fetchall()
    for r in rows:
        if r["caller_imei"]:
            by_imei[r["caller_imei"]][r["caller"]].append(
                {"record_id": r["record_id"], "timestamp": r["timestamp"], "call_type": r["call_type"]}
            )
        if r["callee_imei"]:
            by_imei[r["callee_imei"]][r["callee"]].append(
                {"record_id": r["record_id"], "timestamp": r["timestamp"], "call_type": r["call_type"]}
            )

    results = []
    for imei, msisdn_occurrences in by_imei.items():
        if len(msisdn_occurrences) < IMEI_MAPPING_MIN_DISTINCT_MSISDN:
            continue
        all_occurrences = [o for occs in msisdn_occurrences.values() for o in occs]
        gsm_count = sum(1 for o in all_occurrences if o["call_type"] == "GSM_CALL")
        ip_count = sum(1 for o in all_occurrences if o["call_type"] == "IP_CALL")
        msisdn_windows = {}
        for msisdn, occs in msisdn_occurrences.items():
            times = sorted(_parse(o["timestamp"]) for o in occs)
            msisdn_windows[msisdn] = {
                "first_seen": times[0].strftime(FMT), "last_seen": times[-1].strftime(FMT),
                "record_ids": sorted({o["record_id"] for o in occs}),
            }
        results.append({
            "imei": imei,
            "msisdns": sorted(msisdn_occurrences.keys()),
            "msisdn_windows": msisdn_windows,
            "gsm_call_count": gsm_count,
            "ip_call_count": ip_count,
            "tower_corroborated": gsm_count > 0,  # IP_CALL rows carry no reliable tower trail (see module docstring)
        })
    return results


def detect_imei_corroborated_burner_rotation(conn):
    """Cross-checks app.detectors.burner_sim.detect_burner_rotation's
    purely social (shared-contact-set) burner-SIM-rotation candidates
    against the device-level IMEI mapping above. A pair where the
    "earlier" and "later" phone also share an IMEI is the SIM-swap-to-evade
    pattern described verbatim in the research pass: the same physical
    handset, two different SIMs, used one after the other. This is
    reported as its own, higher-confidence finding -- never a silent
    upgrade of the underlying BURNER_ROTATION lead -- so an investigator
    can see exactly which corroboration (social, device, or both) backs
    a given pair."""
    from app.detectors.burner_sim import detect_burner_rotation

    imei_hits = detect_imei_msisdn_mapping(conn)
    msisdn_to_imeis = defaultdict(set)
    for hit in imei_hits:
        for msisdn in hit["msisdns"]:
            msisdn_to_imeis[msisdn].add(hit["imei"])

    results = []
    for rotation in detect_burner_rotation(conn):
        earlier, later = rotation["phone_earlier"], rotation["phone_later"]
        shared_imeis = msisdn_to_imeis[earlier] & msisdn_to_imeis[later]
        if not shared_imeis:
            continue
        results.append({**rotation, "shared_imeis": sorted(shared_imeis)})
    return results
