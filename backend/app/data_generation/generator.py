"""
Synthetic data generator for the Consolidated Intelligence Platform.

Produces a SQLite database of FIR text records, surveillance/intelligence-
agency reports, CDR (call detail records) and transaction records, plus a
ground_truth.json checklist documenting every planted case so downstream
tests can assert the pipeline actually recovers each one. Nothing here is
real data -- all names, numbers and places are fabricated for the SIH26189
demo.

Data sources modeled, matching the problem statement's list: FIRs and police
reports, CDRs, financial transaction records, surveillance reports, and
intelligence agency reports. FIRs and the two intel-report categories are
all unstructured narrative text run through the identical NLP extraction
pipeline (see app/extraction) -- only the source table and provenance tag
differ. Criminal-history recurrence is implicit in the graph itself (a
PERSON appearing across multiple cases' FIRs already surfaces as multi-case
history via the entity's *_IN_CASE edges) rather than a separate table.
Social-media intelligence is deliberately NOT ingested via live scraping
(out of scope by design); an already-collected social-media-intel report
would slot into intel_records the same way surveillance reports do.

Deliberately NOT included: any hand-crafted "hidden edge" for missing-link
recovery testing. That capability is validated at evaluation time by masking
a random slice of the REAL generated edges (see app/recovery), never by
planting an edge meant to be invisible to ingestion.
"""
import json
import random
from datetime import datetime, timedelta

from app.config import GROUND_TRUTH_PATH
from app.db.schema import get_connection, init_db

RNG = random.Random(42)
BASE_DATE = datetime(2026, 1, 1)


def dt(days=0, hours=0, minutes=0):
    return (BASE_DATE + timedelta(days=days, hours=hours, minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


class IdSeq:
    def __init__(self, prefix):
        self.prefix = prefix
        self.n = 0

    def next(self):
        self.n += 1
        return f"{self.prefix}{self.n:05d}"


FIR_SEQ = IdSeq("FIR")
CDR_SEQ = IdSeq("CDR")
TXN_SEQ = IdSeq("TXN")
INTEL_SEQ = IdSeq("INT")

fir_rows = []
cdr_rows = []
txn_rows = []
intel_rows = []
ground_truth = {"cases": {}}


def add_fir(case_id, station, day, text):
    fid = FIR_SEQ.next()
    fir_rows.append((fid, case_id, station, dt(days=day), text))
    return fid


def add_intel(case_id, source_category, reporting_unit, day, text):
    """A surveillance report or an intelligence-agency report -- narrative
    text like an FIR, but sourced and provenance-tagged differently (per the
    PS's own list of source types: surveillance reports, intelligence
    agency reports, distinct from FIRs). Goes through the identical NLP
    extraction pipeline as fir_records; only the source table and tag
    differ."""
    rid = INTEL_SEQ.next()
    intel_rows.append((rid, case_id, source_category, reporting_unit, dt(days=day), text))
    return rid


def add_cdr(caller, callee, day, hour, minute, duration):
    cid = CDR_SEQ.next()
    cdr_rows.append((cid, caller, callee, dt(days=day, hours=hour, minutes=minute), duration))
    return cid


def add_txn(sender, receiver, amount, day, hour, minute):
    tid = TXN_SEQ.next()
    txn_rows.append((tid, sender, receiver, amount, dt(days=day, hours=hour, minutes=minute)))
    return tid


PROPERTY_SEQ = IdSeq("PROP")
ITEM_SEQ = IdSeq("ITEM")
EVENT_SEQ = IdSeq("EVT")
MEMO_SEQ = IdSeq("MEMO")
MO_SEQ = IdSeq("MO")

case_case_type_rows = []
case_property_rows = []
property_item_rows = []
custody_event_rows = []
ndps_sampling_rows = []
crime_mo_record_rows = []


def add_case_type(case_id, case_type, status="CONFIRMED", confidence=None, reason=None):
    case_case_type_rows.append((case_id, case_type, status, confidence, reason, None, None))


def add_case_property(case_id, case_type, form_type, day, place, officer, witnesses):
    pid = PROPERTY_SEQ.next()
    case_property_rows.append((
        pid, case_id, case_type, form_type, dt(days=day), place,
        json.dumps(officer), json.dumps(witnesses), None, None, None, dt(days=day),
    ))
    return pid


def add_property_item(property_id, description, quantity, unit, gross_weight, net_weight,
                       identifiers=None, exhibit_mark=None, seal_description=None, seal_count=None,
                       estimated_value=None):
    iid = ITEM_SEQ.next()
    property_item_rows.append((
        iid, property_id, description, quantity, unit, gross_weight, net_weight,
        json.dumps(identifiers or {}), exhibit_mark, seal_description, seal_count, estimated_value,
    ))
    return iid


def add_custody_event(property_id, event_type, day, **kwargs):
    eid = EVENT_SEQ.next()
    custody_event_rows.append((
        eid, property_id, event_type, dt(days=day),
        kwargs.get("register_no"), kwargs.get("road_certificate_no"),
        kwargs.get("from_location"), kwargs.get("to_location"), kwargs.get("countersigned_by"),
        kwargs.get("seals_intact_and_tallied"), kwargs.get("report_no"), kwargs.get("conclusion_category"),
        json.dumps(kwargs.get("attributes", {})),
    ))
    return eid


def add_ndps_sampling(property_id, **kwargs):
    mid = MEMO_SEQ.next()
    ndps_sampling_rows.append((
        mid, property_id,
        kwargs.get("crime_no"), kwargs["drug_description"], kwargs["net_weight_seized"],
        kwargs.get("lot_size"), kwargs.get("date_of_draw_of_sample"), kwargs.get("num_samples"),
        kwargs.get("sample_weight_each"), int(kwargs.get("prepared_in_triplicate", False)),
        kwargs.get("magistrate_certification_ts"), kwargs.get("net_weight_lab_received"),
        kwargs.get("lab_date_of_receipt"), kwargs.get("disposal_form7_ref"), kwargs.get("disposal_form10_ref"),
        kwargs.get("conveyance_chassis_no"), kwargs.get("conveyance_engine_no"),
    ))
    return mid


def add_crime_mo_record(case_id, fir_id, day, **kwargs):
    rid = MO_SEQ.next()
    crime_mo_record_rows.append((
        rid, case_id, fir_id, dt(days=day),
        kwargs.get("method_1"), kwargs.get("conveyance"), kwargs.get("character_assumed"),
        kwargs.get("place_type"), kwargs.get("property_type"), kwargs.get("time_of_day_band"),
        kwargs.get("language_dialect"),
        int(kwargs.get("operates_with_accomplices", False)), int(kwargs.get("is_recidivist", False)),
        int(kwargs.get("is_generally_armed", False)),
    ))
    return rid


PM_SEQ = IdSeq("PM")
INQUEST_SEQ = IdSeq("INQ")
MLC_SEQ = IdSeq("MLC")
FORENSIC_SEQ = IdSeq("FOR")
TOWER_SEQ = IdSeq("TWR")

post_mortem_report_rows = []
inquest_report_rows = []
mlc_record_rows = []
forensic_match_rows = []
tower_location_record_rows = []


def add_post_mortem_report(case_id, day, **kwargs):
    pid = PM_SEQ.next()
    post_mortem_report_rows.append((
        pid, case_id, kwargs.get("fir_id"), kwargs.get("deceased_name"),
        kwargs.get("date_of_death"), kwargs.get("date_of_postmortem"), kwargs.get("doctor_name"),
        kwargs.get("place"), kwargs.get("cause_of_death"),
        json.dumps(kwargs.get("injury_list", [])),
        kwargs.get("rectal_temperature"), kwargs.get("rigor_mortis_state"), kwargs.get("rigor_mortis_time_estimate"),
        kwargs.get("viscera_preserved"), kwargs.get("viscera_sent_to_fsl_ts"), dt(days=day),
    ))
    return pid


def add_inquest_report(case_id, day, **kwargs):
    iid = INQUEST_SEQ.next()
    inquest_report_rows.append((
        iid, case_id, kwargs.get("fir_id"), kwargs.get("deceased_name"), kwargs.get("inquest_date"),
        kwargs.get("place_of_occurrence"), kwargs.get("witness_count"),
        json.dumps(kwargs.get("witnesses", [])), json.dumps(kwargs.get("injury_list", [])),
        kwargs.get("conducting_officer"), int(kwargs.get("is_custodial_death", False)),
        kwargs.get("death_ts"), kwargs.get("intimation_ts"), kwargs.get("body_forwarded_ts"), dt(days=day),
    ))
    return iid


def add_mlc_record(case_id, day, **kwargs):
    mid = MLC_SEQ.next()
    mlc_record_rows.append((
        mid, case_id, kwargs.get("fir_id"), kwargs.get("patient_name"), kwargs.get("hospital"),
        kwargs.get("date_of_examination"), json.dumps(kwargs.get("injury_list", [])),
        kwargs.get("injury_classification"), kwargs.get("treating_doctor"), kwargs.get("follow_up_days"),
        dt(days=day),
    ))
    return mid


def add_forensic_match(match_type, case_id_a, case_id_b, exhibit_a, exhibit_b, **kwargs):
    fid = FORENSIC_SEQ.next()
    forensic_match_rows.append((
        fid, match_type, case_id_a, case_id_b, exhibit_a, exhibit_b,
        kwargs.get("match_confidence_numeric"), kwargs.get("match_confidence_category"),
        int(kwargs.get("examiner_asserted", False)), kwargs.get("examiner_name"),
        kwargs.get("fsl_report_no"), kwargs.get("report_date"), kwargs.get("identifier_value"),
        json.dumps(kwargs.get("attributes", {})),
    ))
    return fid


def add_tower_location_record(case_id, phone, day, hour, minute, **kwargs):
    tid = TOWER_SEQ.next()
    tower_location_record_rows.append((
        tid, case_id, phone, kwargs.get("cell_id"), kwargs.get("locality_name"),
        dt(days=day, hours=hour, minutes=minute),
        int(kwargs.get("is_certified_65b", False)), kwargs.get("certificate_ref"),
    ))
    return tid


MP_SEQ = IdSeq("MP")
UIDB_SEQ = IdSeq("UIDB")
DNA_SAMPLE_SEQ = IdSeq("DNA")

missing_person_report_rows = []
uidb_record_rows = []
dna_sample_record_rows = []


def add_missing_person_report(case_id, day, **kwargs):
    mpid = MP_SEQ.next()
    missing_person_report_rows.append((
        mpid, case_id, kwargs.get("fir_id"), kwargs.get("name"), kwargs.get("age"), kwargs.get("sex"),
        kwargs.get("height_cm"), kwargs.get("build"), kwargs.get("complexion"), kwargs.get("hair"),
        kwargs.get("clothing_description"), json.dumps(kwargs.get("dress_colour_tokens", [])),
        kwargs.get("distinguishing_marks"), kwargs.get("last_seen_date"), kwargs.get("last_seen_place"),
        kwargs.get("last_seen_circumstances"), kwargs.get("district"), kwargs.get("status", "OPEN"), dt(days=day),
    ))
    return mpid


def add_uidb_record(case_id, day, **kwargs):
    uid = UIDB_SEQ.next()
    uidb_record_rows.append((
        uid, case_id, kwargs.get("uidb_serial_no"), kwargs.get("state"), kwargs.get("district"),
        kwargs.get("police_station"), kwargs.get("age_from"), kwargs.get("age_to"), kwargs.get("sex"),
        kwargs.get("found_date"), kwargs.get("height_cm"), kwargs.get("religion"), kwargs.get("dd_number"),
        kwargs.get("dd_date"), kwargs.get("fir_no"), kwargs.get("found_place"), kwargs.get("parentage"),
        kwargs.get("address"), kwargs.get("build"), kwargs.get("complexion"), kwargs.get("face"),
        kwargs.get("hair"), kwargs.get("eyes"), kwargs.get("beard"), kwargs.get("mustaches"),
        kwargs.get("dress_upper"), kwargs.get("dress_upper_colour"), kwargs.get("dress_lower"),
        kwargs.get("dress_lower_colour"), kwargs.get("remarks"), kwargs.get("police_post"), kwargs.get("pm_id"),
        kwargs.get("reward_amount"), kwargs.get("notification_no"), kwargs.get("notification_date"),
        kwargs.get("matched_missing_serial_no"), kwargs.get("matching_date"), dt(days=day),
    ))
    return uid


def add_dna_sample_record(case_id, pm_id, day, **kwargs):
    sid = DNA_SAMPLE_SEQ.next()
    dna_sample_record_rows.append((
        sid, case_id, pm_id, kwargs.get("sample_source"), kwargs.get("collected_ts"), kwargs.get("dispatch_ts"),
        kwargs.get("dispatch_delay_reason"), kwargs.get("conclusion_category"),
        int(kwargs.get("expert_examined", False)), dt(days=day),
    ))
    return sid


CHARGE_SHEET_SEQ = IdSeq("CS")

charge_sheet_rows = []
# (charge_sheet_id, fir_id) pairs -- charge_sheet_accused can't be inserted
# at generation time because its entity_id is a resolved PERSON entity that
# doesn't exist until app.resolution.resolver has run. Recorded here and
# resolved by populate_charge_sheet_accused(conn), called from the pipeline
# right after run_resolution(), the same way _accused_entity_ids() resolves
# "the accused named in this FIR" everywhere else in the codebase (see
# app/detectors/robbery_theft_digital.py) -- reusing entity resolution
# output rather than inventing a second identity scheme for accused persons.
charge_sheet_accused_by_fir = []


def add_charge_sheet(case_id, fir_id, day, accused_fir_id=None, **kwargs):
    """Plants a charge_sheet row. accused_fir_id (defaults to fir_id) names
    the FIR whose ACCUSED-role PERSON mentions become this charge-sheet's
    accused once resolution has run -- lets a charge-sheet reuse an FIR
    already planted for another purpose (e.g. the MO-series FIRs) without
    duplicating narrative text."""
    csid = CHARGE_SHEET_SEQ.next()
    charge_sheet_rows.append((
        csid, case_id, fir_id, kwargs.get("cognizance_date"),
        int(kwargs.get("offence_cognizable", True)), kwargs.get("max_punishment_years"), dt(days=day),
    ))
    charge_sheet_accused_by_fir.append((csid, accused_fir_id or fir_id))
    return csid


def populate_charge_sheet_accused(conn):
    """Resolves charge_sheet_accused_by_fir into real charge_sheet_accused
    rows, using the exact same accused-entity-resolution query as
    _accused_entity_ids() in app/detectors/robbery_theft_digital.py. Must
    run after app.resolution.resolver.run_resolution() (entities must
    exist) and is idempotent (DELETE + re-insert) like
    backfill_common_identifier_index."""
    conn.execute("DELETE FROM charge_sheet_accused")
    to_insert = []
    seen = set()
    for charge_sheet_id, fir_id in charge_sheet_accused_by_fir:
        rows = conn.execute(
            """SELECT DISTINCT mem.entity_id FROM entity_mentions em
               JOIN mention_entity_map mem ON em.mention_id = mem.mention_id
               WHERE em.source_record_id = ? AND em.fir_role = 'ACCUSED'""",
            (fir_id,),
        ).fetchall()
        for r in rows:
            key = (charge_sheet_id, r["entity_id"])
            if key in seen:
                continue
            seen.add(key)
            to_insert.append(key)
    conn.executemany(
        "INSERT INTO charge_sheet_accused (charge_sheet_id, entity_id) VALUES (?, ?)",
        to_insert,
    )
    conn.commit()
    return {"charge_sheet_accused_rows": len(to_insert)}


# ---------------------------------------------------------------------------
# CASE 1: Fraud Ring Alpha
# ---------------------------------------------------------------------------
CASE_FRAUD = "C001"

add_case_type(CASE_FRAUD, "FINANCIAL_FRAUD", status="CONFIRMED",
              reason="seed data: legacy category 'financial_fraud' migrated on schema cutover")

# --- Planted case: two people, same name, must NOT merge ---
RK1_PHONE, RK1_ACC = "9810000001", "100000000001"
RK2_PHONE, RK2_ACC = "9810000002", "100000000002"

f1 = add_fir(CASE_FRAUD, "Sonepur Police Station", 2,
             "Accused Rajesh Kumar (phone 9810000001, account 100000000001) was found operating "
             "a fraudulent investment scheme from Sonepur Police Station jurisdiction.")
f2 = add_fir(CASE_FRAUD, "MG Road Police Station", 5,
             "Witness Rajesh Kumar (phone 9810000002, account 100000000002) stated he received a "
             "suspicious call unrelated to the investment scheme reported earlier.")

# --- Planted case: one person, two spellings, one shared phone -> must merge ---
SD_PHONE = "9810000003"
f3 = add_fir(CASE_FRAUD, "Sonepur Police Station", 3,
             "Accused Sunita Devi (phone 9810000003) transferred funds to multiple mule accounts "
             "over a two week period.")
f4 = add_fir(CASE_FRAUD, "Sonepur Police Station", 9,
             "Further inquiry found Sunita D. (contact 9810000003) had opened accounts under a "
             "second identity document.")

# --- Planted case: investigating officer must never top ranking ---
# The officer is also deliberately given real call-graph activity (moderate
# degree, comparable to the actual suspects) so that role-exclusion is tested
# end-to-end on live analytics, not just on a hand-built unit-test graph.
OFFICER_NAME = "Inspector Alok Sharma"
OFFICER_PHONE = "9810000090"
add_fir(CASE_FRAUD, "Sonepur Police Station", 1,
        f"Investigating Officer Inspector Alok Sharma (contact {OFFICER_PHONE}) recorded statement "
        f"number 1 regarding the ongoing financial fraud investigation and coordinated with field units.")
for i, day in enumerate([2, 3, 5, 7, 9, 11, 13, 15, 17, 20, 22, 24, 26, 28]):
    add_fir(CASE_FRAUD, "Sonepur Police Station", day,
            f"Investigating Officer Inspector Alok Sharma recorded statement number {i+2} regarding "
            f"the ongoing financial fraud investigation and forwarded the case diary for review.")
OFFICER_FIELD_CONTACTS = [f"9810000{80+i}" for i in range(1, 7)]
for i, c in enumerate(OFFICER_FIELD_CONTACTS):
    add_cdr(OFFICER_PHONE, c, day=1 + i, hour=10 + i, minute=(i * 6) % 60, duration=120 + i * 10)
add_cdr(OFFICER_FIELD_CONTACTS[0], OFFICER_PHONE, day=8, hour=15, minute=0, duration=200)

# --- Planted case: call ~20-30 min before a large transfer, same two people ---
PX_PHONE, PX_ACC = "9810000010", "100000000010"
PY_PHONE, PY_ACC = "9810000011", "100000000011"
add_fir(CASE_FRAUD, "MG Road Police Station", 10,
        "Complainant Deepak Verma (phone 9810000010, account 100000000010) alleged that Accused "
        "Farha Khan (phone 9810000011, account 100000000011) convinced him by phone to transfer a "
        "large sum shortly after their call.")
add_cdr(PX_PHONE, PY_PHONE, day=10, hour=11, minute=0, duration=180)
add_txn(PX_ACC, PY_ACC, amount=850000, day=10, hour=11, minute=25)

# --- Planted case: burner-SIM rotation ---
PHONE_A = "9810000020"
PHONE_B = "9810000021"
BURNER_CONTACTS = [f"981000010{i}" for i in range(0, 10)]  # 10 shared contacts pool
A_CONTACTS = BURNER_CONTACTS  # phone A talks to all 10
B_CONTACTS = BURNER_CONTACTS[:7]  # phone B overlaps with 7 of those 10 (70%)
# A active days 40-44, then silent. B activates days 46-50 (within days of A going silent).
for i, c in enumerate(A_CONTACTS):
    add_cdr(PHONE_A, c, day=40 + (i % 5), hour=9 + (i % 6), minute=(i * 7) % 60, duration=60 + i * 5)
for i, c in enumerate(B_CONTACTS):
    add_cdr(PHONE_B, c, day=46 + (i % 5), hour=9 + (i % 6), minute=(i * 11) % 60, duration=50 + i * 4)
add_intel(CASE_FRAUD, "SURVEILLANCE_REPORT", "Cyber Surveillance Cell", 47,
          "Field surveillance flagged phone 9810000020 as inactive since day 44, with a new "
          "number 9810000021 exhibiting a similar contact pattern shortly after.")

# --- Planted case: utility / customer-care number, high in-degree, never caller ---
UTILITY_NUMBER = "18001800001"
random_callers = [f"98200{str(i).zfill(5)}" for i in range(1, 60)]
for i, caller in enumerate(random_callers):
    add_cdr(caller, UTILITY_NUMBER, day=(i % 30), hour=8 + (i % 10), minute=(i * 3) % 60, duration=30 + (i % 200))

# --- Planted case: mule account layering (fan-in -> fan-out) ---
MULE_ENTRY_ACCOUNT = "100000099001"
SENDERS = [MULE_ENTRY_ACCOUNT] + [f"SND{str(i).zfill(3)}" for i in range(1, 40)]
LAYER1 = [f"L1_{str(i).zfill(2)}" for i in range(1, 7)]
LAYER2 = [f"L2_{str(i).zfill(2)}" for i in range(1, 3)]
add_fir(CASE_FRAUD, "Cyber Crime Cell", 61,
        f"Accused Vikram Oberoi (account {MULE_ENTRY_ACCOUNT}) was identified as one of the accounts "
        f"funnelling money into the intermediate layering structure under investigation.")
for i, sender in enumerate(SENDERS):
    l1 = LAYER1[i % len(LAYER1)]
    add_txn(sender, l1, amount=RNG.randint(8000, 15000), day=60 + (i % 4), hour=9 + (i % 8), minute=(i * 5) % 60)
for i, l1 in enumerate(LAYER1):
    l2 = LAYER2[i % len(LAYER2)]
    add_txn(l1, l2, amount=RNG.randint(60000, 90000), day=63 + (i % 3), hour=10 + i, minute=(i * 13) % 60)
add_intel(CASE_FRAUD, "INTELLIGENCE_AGENCY_REPORT", "Financial Intelligence Unit (FIU-IND)", 64,
          "Layering pattern observed: numerous small accounts funnelled funds into intermediate "
          "accounts before consolidation into two final accounts, consistent with mule-account "
          "structuring reported in prior advisories.")

# --- Planted case: two dense unrelated communities bridged by one lightweight broker ---
ALPHA = [f"FA_{str(i).zfill(2)}" for i in range(1, 9)]
BETA = [f"FB_{str(i).zfill(2)}" for i in range(1, 9)]
BROKER_ACC = "100000099002"
BROKER_PHONE = "9810000099"
for i in range(len(ALPHA)):
    for j in range(i + 1, len(ALPHA)):
        if RNG.random() < 0.55:
            add_txn(ALPHA[i], ALPHA[j], amount=RNG.randint(2000, 20000), day=70 + RNG.randint(0, 10),
                    hour=RNG.randint(8, 20), minute=RNG.randint(0, 59))
for i in range(len(BETA)):
    for j in range(i + 1, len(BETA)):
        if RNG.random() < 0.55:
            add_txn(BETA[i], BETA[j], amount=RNG.randint(2000, 20000), day=70 + RNG.randint(0, 10),
                    hour=RNG.randint(8, 20), minute=RNG.randint(0, 59))
add_txn(ALPHA[0], BROKER_ACC, amount=5000, day=75, hour=14, minute=10)
add_txn(BROKER_ACC, BETA[0], amount=4800, day=75, hour=14, minute=40)
add_cdr(BROKER_PHONE, "9810000501", day=75, hour=13, minute=0, duration=90)
add_fir(CASE_FRAUD, "Cyber Crime Cell", 76,
        f"Analysts noted that Witness Kavya Reddy (account {BROKER_ACC}) holds an account with very few "
        f"transactions that appears to move funds between two otherwise unconnected groups of accounts.")

ground_truth["cases"][CASE_FRAUD] = {
    "title": "Fraud Ring Alpha",
    "name_collision": {"person_a": RK1_PHONE, "person_b": RK2_PHONE, "must_not_merge": True},
    "alias_merge": {"phone": SD_PHONE, "spellings": ["Sunita Devi", "Sunita D."], "must_merge": True},
    "official": {"name": OFFICER_NAME, "phone": OFFICER_PHONE, "must_never_top_ranking": True},
    "utility_number": {"number": UTILITY_NUMBER, "must_never_top_ranking": True},
    "call_before_transfer": {"phones": [PX_PHONE, PY_PHONE], "accounts": [PX_ACC, PY_ACC]},
    "burner_rotation": {"phone_a": PHONE_A, "phone_b": PHONE_B, "shared_contacts": B_CONTACTS},
    "mule_layering": {"senders": SENDERS, "layer1": LAYER1, "layer2": LAYER2},
    "bridge_broker": {"account": BROKER_ACC, "phone": BROKER_PHONE, "community_a": ALPHA, "community_b": BETA},
}

# ---------------------------------------------------------------------------
# CASE 2: Missing Persons - Sonepur Corridor (Women Safety flagship)
# ---------------------------------------------------------------------------
CASE_TRAFFICKING = "C002"

add_case_type(CASE_TRAFFICKING, "TRAFFICKING_MISSING_PERSON", status="CONFIRMED",
              reason="seed data: legacy category 'women_safety' migrated on schema cutover "
                     "(HANDOFF.md Section 4: Women Safety is repositioned as this case type, not deleted)")

RECRUITER = "9820000001"
TRANSPORTER = "9820000002"
RECEIVER = "9820000003"
VICTIMS = ["9820000011", "9820000012", "9820000013", "9820000014"]
RECEIVER_CLUSTER = ["9820000021", "9820000022", "9820000023"]

LOCATION_NAME = "Sonepur Junction"
STATION_NAME = "Sonepur Police Station"

# Recruiter contacts each victim (fan-out), plus 1-2 edges between victims themselves
for i, v in enumerate(VICTIMS):
    add_cdr(RECRUITER, v, day=100 + i, hour=18 + (i % 4), minute=(i * 9) % 60, duration=200 + i * 20)
add_cdr(VICTIMS[0], VICTIMS[1], day=101, hour=20, minute=5, duration=90)
add_cdr(VICTIMS[1], VICTIMS[2], day=103, hour=21, minute=15, duration=60)

# Transporter: exactly one edge to recruiter, one edge to receiver side
add_cdr(TRANSPORTER, RECRUITER, day=105, hour=7, minute=30, duration=45)
add_cdr(TRANSPORTER, RECEIVER, day=106, hour=8, minute=0, duration=50)

# Receiver inside a small dense receiver cluster (a 4-node clique so the
# receiver's own degree is comparatively high -- the "denser cluster on the
# other side" the structural bridge-path method looks for)
add_cdr(RECEIVER, RECEIVER_CLUSTER[0], day=107, hour=9, minute=0, duration=120)
add_cdr(RECEIVER, RECEIVER_CLUSTER[1], day=107, hour=9, minute=40, duration=100)
add_cdr(RECEIVER, RECEIVER_CLUSTER[2], day=107, hour=10, minute=10, duration=90)
add_cdr(RECEIVER_CLUSTER[0], RECEIVER_CLUSTER[1], day=108, hour=10, minute=0, duration=80)
add_cdr(RECEIVER_CLUSTER[0], RECEIVER_CLUSTER[2], day=108, hour=10, minute=30, duration=70)
add_cdr(RECEIVER_CLUSTER[1], RECEIVER_CLUSTER[2], day=108, hour=11, minute=0, duration=60)

# Repeat-location signal: same real location named across >=3 independent records,
# tied to DIFFERENT entities in the trafficking sub-case.
add_fir(CASE_TRAFFICKING, STATION_NAME, 100,
        f"Missing person report: Victim last seen boarding a bus near {LOCATION_NAME} before contact "
        f"was lost with her family.")
add_intel(CASE_TRAFFICKING, "SURVEILLANCE_REPORT", "Field Surveillance Unit", 104,
          f"A recruiter matching phone 9820000001 was seen soliciting young women near "
          f"{LOCATION_NAME} on multiple evenings.")
TRANSPORTER_VEHICLE = "KA05MN1234"
add_fir(CASE_TRAFFICKING, "Cyber Crime Cell", 106,
        f"Separate case file: a vehicle bearing registration {TRANSPORTER_VEHICLE}, believed linked "
        f"to phone 9820000002, was captured on camera near {LOCATION_NAME} on the transport route.")
add_intel(CASE_TRAFFICKING, "INTELLIGENCE_AGENCY_REPORT", "State Intelligence Wing", 108,
          f"Corridor-level advisory: recurring trafficking-linked movement has been reported near "
          f"{LOCATION_NAME} over the past quarter, corroborating local complaints from this case.")

# Mundane repeat: the filing station name itself recurs across many unrelated FIRs (expected, not flagged)
for day in [1, 3, 6, 8, 12, 100, 104]:
    pass  # station already set as the `station` metadata field on the FIRs above; no extra action needed

# A few more FIRs filed at the same station for unrelated matters, to stress-test that the
# station name recurring as *filing station* is not treated the same as a narrative location mention.
for i, day in enumerate([12, 33, 55, 90]):
    add_fir(CASE_FRAUD if i % 2 == 0 else CASE_TRAFFICKING, STATION_NAME, day,
            f"Routine complaint number {i+1} regarding a minor property dispute was filed and closed.")

# --- UIDB (Unidentified Dead Body) <-> missing-person Physical-evidence
# vertical slice (Sept 2026 pivot, module 4), joined into the SAME case as
# the live-trafficking Digital signals above, per the research pass's own
# recommendation that the two be modeled together, not as unrelated tables.
#
# MP_A / UIDB_A: an unmatched candidate pair -- demographics/dress/date/
# district all line up, but ZIPNET's matched_missing_serial_no is still
# empty. Its post-mortem has NO DNA sample at all.
MP_A = add_missing_person_report(
    CASE_TRAFFICKING, day=140, name="Priya Sharma", age=22, sex="FEMALE", height_cm=160.0,
    build="Slim", complexion="Fair", hair="Black, long", clothing_description="Red kurta and blue jeans",
    dress_colour_tokens=["red", "blue"], distinguishing_marks="Mole on left cheek",
    last_seen_date=dt(days=140), last_seen_place="Sonepur Junction",
    last_seen_circumstances="Last seen boarding a bus", district="Sonepur", status="OPEN",
)
PM_UIDB_A = add_post_mortem_report(
    CASE_TRAFFICKING, day=155, deceased_name=None, date_of_death=dt(days=154), date_of_postmortem=dt(days=155),
    doctor_name="Dr. Alka Mehta", place="Sonepur District Mortuary", cause_of_death="Drowning",
    injury_list=[], rectal_temperature=30.1, rigor_mortis_state="Passing off", rigor_mortis_time_estimate="18-24 hours",
    viscera_preserved=1, viscera_sent_to_fsl_ts=dt(days=156),
)
UIDB_A = add_uidb_record(
    CASE_TRAFFICKING, day=155, uidb_serial_no="UIDB-2026-0091", state="State X", district="Sonepur",
    police_station=STATION_NAME, age_from=20, age_to=25, sex="FEMALE", found_date=dt(days=155), height_cm=161.0,
    religion="Hindu", dd_number="DD-441", dd_date=dt(days=155), found_place="Riverbank near Sonepur Junction",
    parentage="D/O Ram Sharma", address="Unknown", build="Slim", complexion="Fair", face="Oval", hair="Black",
    eyes="Black", beard=None, mustaches=None, dress_upper="Kurta", dress_upper_colour="Red",
    dress_lower="Jeans", dress_lower_colour="Blue", remarks="Mole noted on left cheek",
    police_post="Sonepur Outpost", pm_id=PM_UIDB_A, notification_no="NOTIF-2026-018", notification_date=dt(days=156),
    matched_missing_serial_no=None, matching_date=None,
)

# MP_B / UIDB_B: ZIPNET already populated matched_missing_serial_no, but
# MP_B's case is still shown OPEN -- the "ignored match" signal. Its DNA
# sample was dispatched 72h after collection (no reason recorded) and
# came back INCONCLUSIVE with no examining expert, yet is the sole basis
# ZIPNET used for the match.
MP_B = add_missing_person_report(
    CASE_TRAFFICKING, day=145, name="Sunita Yadav", age=30, sex="FEMALE", height_cm=155.0,
    build="Medium", complexion="Dark", hair="Black, short", clothing_description="Green saree",
    dress_colour_tokens=["green"], distinguishing_marks="Scar on right hand",
    last_seen_date=dt(days=145), last_seen_place="MG Road area",
    last_seen_circumstances="Did not return home from work", district="MG Road", status="OPEN",
)
PM_UIDB_B = add_post_mortem_report(
    CASE_TRAFFICKING, day=156, deceased_name=None, date_of_death=dt(days=155), date_of_postmortem=dt(days=156),
    doctor_name="Dr. Alka Mehta", place="Sonepur District Mortuary", cause_of_death="Undetermined",
    injury_list=[], rectal_temperature=29.0, rigor_mortis_state="Fully established", rigor_mortis_time_estimate="12-18 hours",
    viscera_preserved=1, viscera_sent_to_fsl_ts=dt(days=157),
)
UIDB_B = add_uidb_record(
    CASE_TRAFFICKING, day=156, uidb_serial_no="UIDB-2026-0094", state="State X", district="MG Road",
    police_station="MG Road Police Station", age_from=28, age_to=33, sex="FEMALE", found_date=dt(days=156),
    height_cm=156.0, religion="Hindu", dd_number="DD-447", dd_date=dt(days=156), found_place="MG Road drain",
    parentage="D/O Mohan Yadav", address="Unknown", build="Medium", complexion="Dark", face="Round",
    hair="Black", eyes="Black", beard=None, mustaches=None, dress_upper="Saree", dress_upper_colour="Green",
    dress_lower=None, dress_lower_colour=None, remarks="Scar noted on right hand", police_post="MG Road Outpost",
    pm_id=PM_UIDB_B, notification_no="NOTIF-2026-021", notification_date=dt(days=157),
    matched_missing_serial_no=MP_B, matching_date=dt(days=157),
)
DNA_B = add_dna_sample_record(
    CASE_TRAFFICKING, PM_UIDB_B, day=156, sample_source="MOLAR_TOOTH",
    collected_ts=dt(days=156), dispatch_ts=dt(days=159), dispatch_delay_reason=None,
    conclusion_category="INCONCLUSIVE", expert_examined=False,
)

# MP_C / UIDB_C: fully compliant -- ZIPNET-matched, case correctly closed
# out, DNA dispatched within 24h with an examined expert and a clean
# MATCHES conclusion. Proves zero false positives across all four checks.
MP_C = add_missing_person_report(
    CASE_TRAFFICKING, day=150, name="Rekha Singh", age=40, sex="FEMALE", height_cm=150.0,
    build="Heavy", complexion="Fair", hair="Grey, short", clothing_description="Yellow salwar",
    dress_colour_tokens=["yellow"], distinguishing_marks="None recorded",
    last_seen_date=dt(days=150), last_seen_place="Cyber Crime Cell jurisdiction",
    last_seen_circumstances="Did not return from a scheduled visit", district="Cyber Crime Cell", status="RESOLVED",
)
PM_UIDB_C = add_post_mortem_report(
    CASE_TRAFFICKING, day=157, deceased_name="Rekha Singh", date_of_death=dt(days=156), date_of_postmortem=dt(days=157),
    doctor_name="Dr. Alka Mehta", place="Sonepur District Mortuary", cause_of_death="Cardiac arrest",
    injury_list=[], rectal_temperature=31.0, rigor_mortis_state="Fully established", rigor_mortis_time_estimate="10-14 hours",
    viscera_preserved=1, viscera_sent_to_fsl_ts=dt(days=158),
)
UIDB_C = add_uidb_record(
    CASE_TRAFFICKING, day=157, uidb_serial_no="UIDB-2026-0097", state="State X", district="Cyber Crime Cell",
    police_station="Cyber Crime Cell", age_from=38, age_to=43, sex="FEMALE", found_date=dt(days=157),
    height_cm=150.0, religion="Hindu", dd_number="DD-452", dd_date=dt(days=157), found_place="Cyber Crime Cell jurisdiction",
    parentage="D/O Late Mohan Singh", address="Known, next of kin informed", build="Heavy", complexion="Fair",
    face="Round", hair="Grey", eyes="Black", beard=None, mustaches=None, dress_upper="Salwar",
    dress_upper_colour="Yellow", dress_lower=None, dress_lower_colour=None, remarks="Identified by family",
    police_post="Cyber Crime Cell", pm_id=PM_UIDB_C, notification_no="NOTIF-2026-024", notification_date=dt(days=158),
    matched_missing_serial_no=MP_C, matching_date=dt(days=158),
)
DNA_C = add_dna_sample_record(
    CASE_TRAFFICKING, PM_UIDB_C, day=157, sample_source="STERNUM",
    collected_ts=dt(days=157), dispatch_ts=dt(days=158), dispatch_delay_reason=None,
    conclusion_category="MATCHES", expert_examined=True,
)

# UIDB_NOISE: different sex/age/district entirely -- must never be
# suggested as a candidate match for MP_A, MP_B, or MP_C.
UIDB_NOISE = add_uidb_record(
    CASE_TRAFFICKING, day=158, uidb_serial_no="UIDB-2026-0099", state="State X", district="Faraway District",
    police_station="Faraway Police Station", age_from=50, age_to=60, sex="MALE", found_date=dt(days=158),
    height_cm=172.0, religion="Hindu", dd_number="DD-460", dd_date=dt(days=158), found_place="Faraway highway",
    parentage="S/O Unknown", address="Unknown", build="Heavy", complexion="Dark", face="Square", hair="Grey",
    eyes="Black", beard="Bearded", mustaches="Yes", dress_upper="Bushirt", dress_upper_colour="White",
    dress_lower="Trousers", dress_lower_colour="Black", remarks="No identification marks noted",
    police_post="Faraway Outpost", pm_id=None, notification_no="NOTIF-2026-026", notification_date=dt(days=159),
    matched_missing_serial_no=None, matching_date=None,
)

ground_truth["cases"][CASE_TRAFFICKING] = {
    "title": "Missing Persons - Sonepur Corridor",
    "recruiter": RECRUITER,
    "victims": VICTIMS,
    "transporter": TRANSPORTER,
    "receiver": RECEIVER,
    "receiver_cluster": RECEIVER_CLUSTER,
    "repeat_location": {"name": LOCATION_NAME, "min_independent_sources": 3},
    "mundane_station": STATION_NAME,
    "transporter_vehicle": TRANSPORTER_VEHICLE,
    "uidb_candidate_missing_person_id": MP_A, "uidb_candidate_uidb_id": UIDB_A, "uidb_candidate_pm_id": PM_UIDB_A,
    "uidb_ignored_missing_person_id": MP_B, "uidb_ignored_uidb_id": UIDB_B, "uidb_ignored_pm_id": PM_UIDB_B,
    "uidb_ignored_dna_sample_id": DNA_B,
    "uidb_clean_missing_person_id": MP_C, "uidb_clean_uidb_id": UIDB_C, "uidb_clean_pm_id": PM_UIDB_C,
    "uidb_clean_dna_sample_id": DNA_C,
    "uidb_noise_id": UIDB_NOISE,
}

# ---------------------------------------------------------------------------
# CASE 3: Narcotics - Physical-evidence vertical slice (Sept 2026 pivot)
#
# Two seizures under the same case: one fully s.52A-compliant (must produce
# ZERO compliance flags -- proves the detector isn't just always firing),
# one with every NDPS Test-Memo/chain-of-custody defect the research
# identified, planted so ground truth can assert each specific flag fires.
# ---------------------------------------------------------------------------
CASE_NARCOTICS = "C003"

add_case_type(CASE_NARCOTICS, "NARCOTICS", status="CONFIRMED", reason="seed data: NDPS seizure case")

add_fir(CASE_NARCOTICS, "Sonepur Police Station", 150,
        "Acting on prior information, a police team intercepted a vehicle near the Sonepur bypass "
        "and recovered a quantity of suspected heroin concealed in the door panel. Accused apprehended "
        "at the spot; seizure proceedings conducted as per NDPS Act procedure.")
add_fir(CASE_NARCOTICS, "Sonepur Police Station", 165,
        "Follow-up raid based on the earlier interception recovered a further quantity of suspected "
        "charas from a rented storage unit linked to the same accused.")

# --- Property A: compliant seizure (heroin) ---
PROP_CLEAN = add_case_property(
    CASE_NARCOTICS, "NARCOTICS", "NDPS_TEST_MEMO", day=150,
    place="Sonepur bypass checkpoint",
    officer={"name": "SI Manoj Tiwari", "rank": "Sub-Inspector"},
    witnesses=[{"name": "Ramesh Yadav", "address": "Sonepur"}, {"name": "Suresh Prasad", "address": "Sonepur"}],
)
add_property_item(
    PROP_CLEAN, description="Suspected heroin, powder form", quantity=1, unit="packet",
    gross_weight=252.0, net_weight=250.0, exhibit_mark="Exh. A-1",
    seal_description="Cloth seal, wax impression 'ST'", seal_count=1,
)
add_custody_event(PROP_CLEAN, "MALKHANA_DEPOSIT", day=150, register_no="XIX/2026/041",
                   countersigned_by="MHC(M) R.K. Singh")
add_custody_event(PROP_CLEAN, "MOVEMENT", day=151, road_certificate_no="RC/XXI/2026/019",
                   from_location="Sonepur Malkhana", to_location="State FSL", countersigned_by="HC Dinesh Kumar")
add_custody_event(PROP_CLEAN, "LAB_RECEIPT", day=152, seals_intact_and_tallied=1,
                   report_no="FSL/2026/DRG/0091")
add_ndps_sampling(
    PROP_CLEAN,
    crime_no="150/2026", drug_description="heroin", net_weight_seized=250.0,
    lot_size=1, date_of_draw_of_sample=dt(days=150, hours=2), num_samples=2, sample_weight_each=5.0,
    prepared_in_triplicate=True, magistrate_certification_ts=dt(days=151),
    net_weight_lab_received=249.9, lab_date_of_receipt=dt(days=152),
    disposal_form7_ref=None, disposal_form10_ref=None,
)

# --- Property B: non-compliant seizure (charas) -- every Part B3 defect planted ---
PROP_VIOLATION = add_case_property(
    CASE_NARCOTICS, "NARCOTICS", "NDPS_TEST_MEMO", day=165,
    place="Rented storage unit, Sonepur",
    officer={"name": "SI Manoj Tiwari", "rank": "Sub-Inspector"},
    witnesses=[{"name": "Ajay Singh", "address": "Sonepur"}, {"name": "Vijay Singh", "address": "Sonepur"}],
)
add_property_item(
    PROP_VIOLATION, description="Suspected charas, multiple packets", quantity=18, unit="packet",
    gross_weight=1210.0, net_weight=1200.0, exhibit_mark="Exh. B-1",
    seal_description="Cloth seal, wax impression 'ST'", seal_count=1,
)
add_custody_event(PROP_VIOLATION, "MALKHANA_DEPOSIT", day=165, register_no="XIX/2026/047",
                   countersigned_by="MHC(M) R.K. Singh")
add_custody_event(PROP_VIOLATION, "MOVEMENT", day=167, road_certificate_no="RC/XXI/2026/024",
                   from_location="Sonepur Malkhana", to_location="State FSL", countersigned_by="HC Dinesh Kumar")
# seal found NOT intact/tallied at the lab -- signal #3
add_custody_event(PROP_VIOLATION, "LAB_RECEIPT", day=168, seals_intact_and_tallied=0,
                   report_no="FSL/2026/DRG/0104")
add_ndps_sampling(
    PROP_VIOLATION,
    crime_no="165/2026", drug_description="charas",
    net_weight_seized=1200.0,
    lot_size=45,                                    # signal #5: exceeds charas's 40-package bulk lot limit
    date_of_draw_of_sample=dt(days=164, hours=10),  # signal #6: BEFORE seizure_datetime (day 165)
    num_samples=2, sample_weight_each=10.0,        # signal #4: below the 24g GSR minimum for charas
    prepared_in_triplicate=False,                  # signal #6: not triplicate
    magistrate_certification_ts=None,              # signal #1: missing certification
    net_weight_lab_received=1150.0,                # signal #2: 50g / ~4.2% short -- exceeds tolerance
    lab_date_of_receipt=dt(days=168),
    disposal_form7_ref="FORM7/2026/003", disposal_form10_ref=None,  # signal #7: incomplete disposal chain
)

ground_truth["cases"][CASE_NARCOTICS] = {
    "title": "Narcotics - Sonepur Storage Unit",
    "compliant_property": PROP_CLEAN,
    "violation_property": PROP_VIOLATION,
    "expected_violation_flags": [
        "MAGISTRATE_CERTIFICATION_MISSING", "WEIGHT_MISMATCH", "SEAL_MISMATCH",
        "SAMPLE_BELOW_RULE_MINIMUM", "LOT_SIZE_EXCEEDED", "TEST_MEMO_NOT_TRIPLICATE",
        "SAMPLE_DRAWN_BEFORE_SEIZURE", "DISPOSAL_CERTIFICATE_INCOMPLETE",
    ],
}

# ---------------------------------------------------------------------------
# CASE 4/5: Robbery/Theft - Ring Bazaar Vehicle Theft Ring (+ a separate
# recovery/raid case, deliberately, so the vehicle/property-match signals
# demonstrate genuine CROSS-case linking, not just cross-item matching
# within one case file)
# ---------------------------------------------------------------------------
CASE_ROBBERY = "C004"
CASE_ROBBERY_RECOVERY = "C005"

add_case_type(CASE_ROBBERY, "ROBBERY_THEFT", status="CONFIRMED", reason="seed data: vehicle/property theft ring")
add_case_type(CASE_ROBBERY_RECOVERY, "ROBBERY_THEFT", status="CONFIRMED", reason="seed data: recovered-property raid, linked to C004")

add_fir(CASE_ROBBERY, "Ring Bazaar Police Station", 200,
        "Complainant reported theft of a Honda Activa motorcycle (registration KA05AB1234, chassis "
        "MB8ES1234K123456, engine ES1234K7890), a Dell Inspiron laptop (serial SN-LAP-778812), a gold "
        "chain, and a television from the residence overnight.")
add_fir(CASE_ROBBERY, "Ring Bazaar Police Station", 201,
        "Complainant reported theft of a TVS Jupiter scooter (registration TN01ZZ9999, chassis "
        "MD6JA1234L000111, engine JA1234L555) from a parking area.")

# --- Stolen-property report (IIF-I-style), case C004 ---
STOLEN_PROP = add_case_property(CASE_ROBBERY, "ROBBERY_THEFT", "STOLEN_PROPERTY_REPORT", day=200,
                                 place="Ring Bazaar residential complex",
                                 officer={"name": "SI Manoj Tiwari", "badge": "SI-4471"},
                                 witnesses=["Complainant"])
ITEM_VEHICLE_CLEAN = add_property_item(
    STOLEN_PROP, "Motorcycle - Honda Activa", 1, "unit", None, None,
    identifiers={"vehicle_type": "Motorcycle", "registration": "KA05AB1234",
                 "chassis": "MB8ES1234K123456", "engine": "ES1234K7890"},
)
ITEM_VEHICLE_TAMPER = add_property_item(
    STOLEN_PROP, "Scooter - TVS Jupiter", 1, "unit", None, None,
    identifiers={"vehicle_type": "Scooter", "registration": "TN01ZZ9999",
                 "chassis": "MD6JA1234L000111", "engine": "JA1234L555"},
)
ITEM_LAPTOP_STOLEN = add_property_item(
    STOLEN_PROP, "Laptop - Dell Inspiron", 1, "unit", None, None,
    identifiers={"serial": "SN-LAP-778812"}, estimated_value=45000,
)
ITEM_CHAIN_STOLEN = add_property_item(
    STOLEN_PROP, "Gold chain", 1, "unit", None, None, estimated_value=60000,
)
ITEM_TV_NOISE = add_property_item(
    STOLEN_PROP, "Television", 1, "unit", None, None, estimated_value=20000,
)

# --- Recovery memo (IIF-IV-style), case C005 -- a DIFFERENT case, so any
# match found below is a genuine cross-case link, not a same-case echo ---
RECOVERY_PROP_LINGERING = add_case_property(CASE_ROBBERY_RECOVERY, "ROBBERY_THEFT", "RECOVERY_MEMO", day=215,
                                             place="Ring Bazaar raid site",
                                             officer={"name": "SI Manoj Tiwari", "badge": "SI-4471"},
                                             witnesses=["Panch witness 1", "Panch witness 2"])
ITEM_VEHICLE_CLEAN_RECOVERED = add_property_item(
    RECOVERY_PROP_LINGERING, "Motorcycle recovered", 1, "unit", None, None,
    identifiers={"vehicle_type": "Motorcycle", "registration": "KA09AB1234",  # partial match: last 4 "1234"
                 "chassis": "MB8ES1234K123456", "engine": "ES1234K7890"},
)
ITEM_VEHICLE_TAMPER_RECOVERED = add_property_item(
    RECOVERY_PROP_LINGERING, "Scooter recovered - suspected re-birthed", 1, "unit", None, None,
    identifiers={"vehicle_type": "Scooter", "registration": "TN02XX0000",
                 "chassis": "MD6JA1234L000111",  # chassis matches...
                 "engine": "JA9999L777"},         # ...but engine does not -- tampering signature
)
ITEM_LAPTOP_RECOVERED = add_property_item(
    RECOVERY_PROP_LINGERING, "Laptop - Dell Inspiron", 1, "unit", None, None,
    identifiers={"serial": "SN-LAP-778812"}, estimated_value=44000,  # exact serial -> LINK regardless of value
)
ITEM_CHAIN_RECOVERED = add_property_item(
    RECOVERY_PROP_LINGERING, "Gold chain", 1, "unit", None, None, estimated_value=55000,  # within 20% of 60000 -> CANDIDATE
)
ITEM_BICYCLE_NOISE = add_property_item(
    RECOVERY_PROP_LINGERING, "Bicycle", 1, "unit", None, None, estimated_value=3000,
)
# Deliberately no COURT_DISPOSAL event, and a later MOVEMENT event pushes
# "as of" well past ROBBERY_LINGERING_PROPERTY_MAX_DAYS (90) from seizure.
add_custody_event(RECOVERY_PROP_LINGERING, "MALKHANA_DEPOSIT", day=215, register_no="MK-2201",
                   to_location="Ring Bazaar Malkhana")
add_custody_event(RECOVERY_PROP_LINGERING, "MOVEMENT", day=330, from_location="Ring Bazaar Malkhana",
                   to_location="District FSL", countersigned_by="SI Manoj Tiwari")

# --- A second, compliant recovery property: disposed of well within the
# lingering threshold, and holding only a non-matching item -- proves the
# lingering-property and property-match detectors both stay silent here ---
RECOVERY_PROP_CLEAN = add_case_property(CASE_ROBBERY_RECOVERY, "ROBBERY_THEFT", "RECOVERY_MEMO", day=216,
                                         place="Ring Bazaar raid site",
                                         officer={"name": "SI Manoj Tiwari", "badge": "SI-4471"},
                                         witnesses=["Panch witness 1"])
ITEM_WALLET_NOISE = add_property_item(RECOVERY_PROP_CLEAN, "Wallet", 1, "unit", None, None, estimated_value=2000)
add_custody_event(RECOVERY_PROP_CLEAN, "COURT_DISPOSAL", day=240, report_no="DISP-889",
                   conclusion_category="RELEASED_TO_OWNER")

# --- MO-series scenario (Digital evidence, NCRB IIF-II fields) ---
FIR_MO_1 = add_fir(CASE_ROBBERY, "Ring Bazaar Police Station", 220,
                    "Accused Suresh Pawar (phone 9830000001) and Accused Iqbal Sheikh (phone 9830000002) "
                    "snatched a gold chain from a pedestrian near the roadside market late in the "
                    "evening, riding a motorcycle and posing as delivery agents.")
FIR_MO_2 = add_fir(CASE_ROBBERY, "Ring Bazaar Police Station", 250,
                    "Accused Suresh Pawar (phone 9830000001) and Accused Iqbal Sheikh (phone 9830000002) "
                    "were identified snatching a gold chain from a woman near a roadside market stall in "
                    "the afternoon, again riding a motorcycle and posing as delivery agents.")
FIR_MO_3 = add_fir(CASE_ROBBERY, "Ring Bazaar Police Station", 400,
                    "Accused Ramesh Yadav (phone 9830000009) broke into a locked shop at night and stole "
                    "electronics using a crowbar, fleeing on foot -- unrelated modus operandi, for "
                    "false-positive testing.")

MO_FIR_1 = add_crime_mo_record(CASE_ROBBERY, FIR_MO_1, day=220, method_1="Chain Snatching",
                                conveyance="Motorcycle", character_assumed="Delivery Agent",
                                place_type="Roadside Market", property_type="Gold Chain",
                                time_of_day_band="EVENING", language_dialect="Hindi",
                                operates_with_accomplices=True)
MO_FIR_2 = add_crime_mo_record(CASE_ROBBERY, FIR_MO_2, day=250, method_1="Chain Snatching",
                                conveyance="Motorcycle", character_assumed="Delivery Agent",
                                place_type="Roadside Market", property_type="Gold Chain",
                                time_of_day_band="AFTERNOON", language_dialect="Hindi",
                                operates_with_accomplices=True)
MO_FIR_3 = add_crime_mo_record(CASE_ROBBERY, FIR_MO_3, day=400, method_1="House-breaking",
                                conveyance="None", character_assumed="Unknown", place_type="Shop",
                                property_type="Electronics", time_of_day_band="NIGHT", language_dialect="Hindi")

ground_truth["cases"][CASE_ROBBERY] = {
    "title": "Robbery/Theft - Ring Bazaar Vehicle Theft Ring",
    "recovery_case_id": CASE_ROBBERY_RECOVERY,
    "vehicle_clean_stolen_item": ITEM_VEHICLE_CLEAN, "vehicle_clean_recovered_item": ITEM_VEHICLE_CLEAN_RECOVERED,
    "vehicle_tamper_stolen_item": ITEM_VEHICLE_TAMPER, "vehicle_tamper_recovered_item": ITEM_VEHICLE_TAMPER_RECOVERED,
    "laptop_stolen_item": ITEM_LAPTOP_STOLEN, "laptop_recovered_item": ITEM_LAPTOP_RECOVERED,
    "chain_stolen_item": ITEM_CHAIN_STOLEN, "chain_recovered_item": ITEM_CHAIN_RECOVERED,
    "noise_stolen_items": [ITEM_TV_NOISE], "noise_recovered_items": [ITEM_BICYCLE_NOISE, ITEM_WALLET_NOISE],
    "lingering_property_id": RECOVERY_PROP_LINGERING, "compliant_property_id": RECOVERY_PROP_CLEAN,
    "mo_series_firs": [FIR_MO_1, FIR_MO_2], "mo_noise_fir": FIR_MO_3,
    "mo_series_min_shared_accused": 2,
}

# ---------------------------------------------------------------------------
# CASE 6/7/8: Assault/Homicide - Physical (inquest/post-mortem/MLC/forensic)
# + Digital (tower/cell-site) vertical slice (Sept 2026 pivot, module 3).
#
# C006 = the violation-heavy custodial-death case (every planted defect).
# C007 = an unrelated older cold case, used ONLY so the fingerprint/
#        ballistics cross-case matches below are genuine cross-CASE links,
#        not same-case echoes (same pattern as C004/C005 for Robbery/Theft).
# C008 = a fully compliant homicide, planted so ground truth can assert
#        ZERO flags fire on clean data (same clean/violation pairing used
#        for Narcotics' PROP_CLEAN/PROP_VIOLATION).
# ---------------------------------------------------------------------------
CASE_ASSAULT = "C006"
CASE_ASSAULT_COLDCASE = "C007"
CASE_ASSAULT_CLEAN = "C008"

add_case_type(CASE_ASSAULT, "ASSAULT_HOMICIDE", status="CONFIRMED", reason="seed data: custodial-death homicide investigation")
add_case_type(CASE_ASSAULT_COLDCASE, "ASSAULT_HOMICIDE", status="CONFIRMED", reason="seed data: unresolved cold case, linked to C006 via forensic match")
add_case_type(CASE_ASSAULT_CLEAN, "ASSAULT_HOMICIDE", status="CONFIRMED", reason="seed data: compliant homicide investigation")

# --- C006: custodial-death homicide, every planted defect ---
FIR_ASSAULT = add_fir(CASE_ASSAULT, "Riverside Police Station", 500,
                       "A detainee Manoj Kumar was found dead inside the police lockup at the Riverside "
                       "Godown facility. Investigation initiated into the circumstances of the custodial "
                       "death; a companion assault victim, witness Ram Lal, was also examined at the "
                       "district hospital in connection with the same incident.")

INQUEST_VIOLATION = add_inquest_report(
    CASE_ASSAULT, day=500, fir_id=FIR_ASSAULT, deceased_name="Manoj Kumar",
    inquest_date=dt(days=500), place_of_occurrence="Riverside Godown",
    witness_count=1, witnesses=["Head Constable Ramesh"],
    injury_list=["blunt trauma to head", "ligature mark on neck"],
    conducting_officer="Executive Magistrate S. Rao", is_custodial_death=True,
    death_ts=dt(days=500, hours=22, minutes=0),
    intimation_ts=dt(days=503, hours=22, minutes=0),  # 72h later -> INTIMATION_DELAYED
    body_forwarded_ts=dt(days=501),
)
PM_VIOLATION = add_post_mortem_report(
    CASE_ASSAULT, day=501, fir_id=FIR_ASSAULT, deceased_name="Manoj Kumar",
    date_of_death=dt(days=500), date_of_postmortem=dt(days=501), doctor_name="Dr. Kavita Iyer",
    place="District Hospital Mortuary", cause_of_death="Craniocerebral injury",
    injury_list=["blunt trauma to head"],  # missing "ligature mark on neck" -> INQUEST_PM_INJURY_MISMATCH
    rectal_temperature=None, rigor_mortis_state=None, rigor_mortis_time_estimate=None,  # missing timing
    viscera_preserved=1, viscera_sent_to_fsl_ts=dt(days=502),
)
MLC_LOW_FOLLOWUP = add_mlc_record(
    CASE_ASSAULT, day=500, fir_id=FIR_ASSAULT, patient_name="Ram Lal", hospital="District Hospital",
    date_of_examination=dt(days=500), injury_list=["fracture of forearm"],
    injury_classification="GRIEVOUS", treating_doctor="Dr. Kavita Iyer", follow_up_days=1,
)
MLC_HIGH_FOLLOWUP = add_mlc_record(
    CASE_ASSAULT, day=500, fir_id=FIR_ASSAULT, patient_name="Ram Lal", hospital="District Hospital",
    date_of_examination=dt(days=500), injury_list=["bruising"],
    injury_classification="SIMPLE", treating_doctor="Dr. Kavita Iyer", follow_up_days=25,
)

# --- C007: cold case (minimal), gives the forensic matches below a genuine second case ---
FIR_COLDCASE = add_fir(CASE_ASSAULT_COLDCASE, "Riverside Police Station", 100,
                        "Unresolved case: an unidentified assailant was reported near the Riverside "
                        "Godown area in connection with an earlier unsolved assault; no arrest made "
                        "at the time.")

# Fingerprint: AFIS/NAFIS is a real, searchable, networked national database
# -- an identical NFN across two exhibits is a genuine automated hit.
FORENSIC_FINGERPRINT_LINK = add_forensic_match(
    "FINGERPRINT", CASE_ASSAULT, CASE_ASSAULT_COLDCASE, "C006-FP-1", "C007-FP-COLD",
    match_confidence_numeric=16, identifier_value="NFN-88213", examiner_asserted=False,
    fsl_report_no="AFIS/2026/1123", report_date=dt(days=505),
)
# Ballistics: India has NO verified networked ballistics database -- this
# is ONLY an examiner's opinion comparing two named exhibits, never a hit.
FORENSIC_BALLISTICS_CANDIDATE = add_forensic_match(
    "BALLISTICS", CASE_ASSAULT, CASE_ASSAULT_COLDCASE, "C006-F1", "C007-F1-COLD",
    match_confidence_category="MATCHES", examiner_asserted=True, examiner_name="Ballistics Expert R. Menon",
    fsl_report_no="FSL/BAL/2026/0071", report_date=dt(days=506),
)
# DNA: categorical outcome misused as a positive match in the case file --
# INCONCLUSIVE is not a match, whatever the case file's own notes claim.
FORENSIC_DNA_MISUSE = add_forensic_match(
    "DNA", CASE_ASSAULT, CASE_ASSAULT, "C006-DNA-CRIMESCENE", "C006-DNA-ACCUSED-REF",
    match_confidence_category="INCONCLUSIVE", examiner_asserted=False,
    fsl_report_no="FSL/DNA/2026/0039", report_date=dt(days=507),
    attributes={"treated_as_positive_in_case_file": True},
)

# --- Digital: one uncertified tower ping matching the death place/time
# (triggers BOTH the certification flag and the spatio-temporal
# correlation), one certified/unrelated ping as noise ---
TOWER_UNCERTIFIED_MATCH = add_tower_location_record(
    CASE_ASSAULT, "9840000001", day=500, hour=21, minute=45,
    cell_id="RVGW-CELL-04", locality_name="Riverside Godown Road", is_certified_65b=False,
)
TOWER_CERTIFIED_NOISE = add_tower_location_record(
    CASE_ASSAULT, "9840000002", day=500, hour=10, minute=0,
    cell_id="CMKT-CELL-11", locality_name="Central Market", is_certified_65b=True, certificate_ref="CERT-2026-0091",
)

# --- C008: fully compliant homicide -- proves zero flags on clean data ---
FIR_ASSAULT_CLEAN = add_fir(CASE_ASSAULT_CLEAN, "Lakeview Police Station", 520,
                             "Complainant reported the stabbing death of Suresh Rathi at his residence "
                             "in Lakeview Colony. Investigation conducted with full procedural compliance.")
INQUEST_CLEAN = add_inquest_report(
    CASE_ASSAULT_CLEAN, day=520, fir_id=FIR_ASSAULT_CLEAN, deceased_name="Suresh Rathi",
    inquest_date=dt(days=520), place_of_occurrence="Lakeview Colony",
    witness_count=3, witnesses=["Witness A", "Witness B", "Witness C"],
    injury_list=["stab wound to chest"], conducting_officer="Executive Magistrate N. Bhatt",
    is_custodial_death=False, death_ts=dt(days=520, hours=20, minutes=0),
)
PM_CLEAN = add_post_mortem_report(
    CASE_ASSAULT_CLEAN, day=521, fir_id=FIR_ASSAULT_CLEAN, deceased_name="Suresh Rathi",
    date_of_death=dt(days=520), date_of_postmortem=dt(days=521), doctor_name="Dr. Anjali Desai",
    place="City Hospital Mortuary", cause_of_death="Haemorrhagic shock",
    injury_list=["stab wound to chest"],  # matches inquest exactly
    rectal_temperature=34.2, rigor_mortis_state="Fully established", rigor_mortis_time_estimate="6-8 hours",
    viscera_preserved=1, viscera_sent_to_fsl_ts=dt(days=522),
)
MLC_CLEAN = add_mlc_record(
    CASE_ASSAULT_CLEAN, day=520, fir_id=FIR_ASSAULT_CLEAN, patient_name="Suresh Rathi",
    hospital="City Hospital", date_of_examination=dt(days=520), injury_list=["stab wound to chest"],
    injury_classification="GRIEVOUS", treating_doctor="Dr. Anjali Desai", follow_up_days=25,  # consistent, no flag
)
FORENSIC_DNA_CLEAN_LINK = add_forensic_match(
    "DNA", CASE_ASSAULT_CLEAN, CASE_ASSAULT_CLEAN, "C008-DNA-CRIMESCENE", "C008-DNA-ACCUSED-REF",
    match_confidence_category="MATCHES", examiner_asserted=False,
    fsl_report_no="FSL/DNA/2026/0044", report_date=dt(days=523),
)
TOWER_CLEAN_CERTIFIED = add_tower_location_record(
    CASE_ASSAULT_CLEAN, "9850000001", day=520, hour=19, minute=30,
    cell_id="LKVW-CELL-02", locality_name="Lakeview Colony Gate", is_certified_65b=True, certificate_ref="CERT-2026-0104",
)

ground_truth["cases"][CASE_ASSAULT] = {
    "title": "Assault/Homicide - Riverside Custodial Death",
    "coldcase_id": CASE_ASSAULT_COLDCASE, "clean_case_id": CASE_ASSAULT_CLEAN,
    "inquest_violation_id": INQUEST_VIOLATION, "pm_violation_id": PM_VIOLATION,
    "inquest_min_witnesses": 2,
    "custodial_intimation_hours": 72,
    "mismatched_injury": "ligature mark on neck",
    "mlc_low_followup_id": MLC_LOW_FOLLOWUP, "mlc_high_followup_id": MLC_HIGH_FOLLOWUP,
    "forensic_fingerprint_link_id": FORENSIC_FINGERPRINT_LINK,
    "forensic_ballistics_candidate_id": FORENSIC_BALLISTICS_CANDIDATE,
    "forensic_dna_misuse_id": FORENSIC_DNA_MISUSE,
    "tower_uncertified_id": TOWER_UNCERTIFIED_MATCH, "tower_certified_noise_id": TOWER_CERTIFIED_NOISE,
}
ground_truth["cases"][CASE_ASSAULT_CLEAN] = {
    "title": "Assault/Homicide - Lakeview Compliant Investigation",
    "inquest_clean_id": INQUEST_CLEAN, "pm_clean_id": PM_CLEAN, "mlc_clean_id": MLC_CLEAN,
    "forensic_dna_clean_link_id": FORENSIC_DNA_CLEAN_LINK, "tower_clean_id": TOWER_CLEAN_CERTIFIED,
}

# ---------------------------------------------------------------------------
# CASE 9: Organized Crime - Interstate Vehicle Theft Syndicate (Sept 2026
# pivot, module 6 -- the last of the six case types). Deliberately reuses
# the Robbery/Theft ring's own identifiers (vehicle KA05AB1234, phones
# 9830000001/9830000002/9830000009 from C004's MO-series FIRs) across new
# FIRs filed in a DIFFERENT case at DIFFERENT police stations, so the
# cross-case identifier links and interstate alert below are genuine
# cross-CASE signals (same pattern as C004/C005 and C006/C007), not
# same-case echoes. Also plants charge_sheet/charge_sheet_accused ground
# truth exercising every filter in the BNS s.111/MCOCA legal gate,
# including the *Zakir Abdul Mirajkar* per-syndicate-not-per-accused rule:
# Suresh Pawar and Ramesh Yadav individually have only ONE qualifying
# charge-sheet each, but their syndicate (connected via shared phone/
# vehicle infrastructure with Iqbal Sheikh and Deepak Malhotra) has TWO.
# ---------------------------------------------------------------------------
CASE_ORGANIZED_CRIME = "C009"

add_case_type(CASE_ORGANIZED_CRIME, "ORGANIZED_CRIME", status="CONFIRMED",
              reason="seed data: interstate vehicle-theft syndicate, linked to C004 via shared identifiers")

FIR_ORG_1 = add_fir(CASE_ORGANIZED_CRIME, "Neighbouring State Task Force", 600,
                     "Accused Iqbal Sheikh (phone 9830000002) and Accused Ramesh Yadav (phone 9830000009) "
                     "were apprehended during a joint interstate raid, in possession of a Honda Activa "
                     "motorcycle (registration KA05AB1234) traced to an earlier theft, and were found "
                     "operating a vehicle-theft racket across state lines.")
FIR_ORG_2 = add_fir(CASE_ORGANIZED_CRIME, "Interstate Crime Cell", 650,
                     "Accused Suresh Pawar (phone 9830000001) was found coordinating the vehicle-theft "
                     "syndicate's interstate operations from outside the state, working alongside Accused "
                     "Deepak Malhotra (phone 9830000005) in arranging onward sale of stolen vehicles.")
# A minimal, otherwise-unconnected FIR used only to carry Deepak Malhotra's
# charge-sheet-history exclusion tests (too-old / non-cognizable / low-
# punishment) without cluttering the interstate-linkage narrative above.
# Deepak is still part of the syndicate via his co-accusal with Suresh
# Pawar on FIR_ORG_2 -- same phone 9830000005 in both FIRs so the two
# mentions resolve to ONE confirmed PERSON entity (a shared hard identifier
# is exactly what entity resolution requires to auto-merge a name across
# records; see app/resolution/resolver.py).
FIR_ORG_3 = add_fir(CASE_ORGANIZED_CRIME, "Records Cell", 100,
                     "Accused Deepak Malhotra (phone 9830000005) was named in an earlier, unrelated case "
                     "record retained for criminal-history reference.")
# Negative control: a lone accused with no co-accusal and no shared
# identifier with anyone else -- must never appear in any syndicate,
# however many charge-sheets of his own he has, since BNS s.111/MCOCA
# (s.2(1)(f)) define a syndicate as two or more persons.
FIR_ORG_NEGATIVE = add_fir(CASE_ORGANIZED_CRIME, "Records Cell", 300,
                           "Accused Manoj Bhatt (phone 9830099999) acted alone in an unrelated matter, "
                           "with no known associates.")

# --- Charge-sheet ground truth ---
# CS_QUALIFY_1 and CS_QUALIFY_2 are the syndicate's only two qualifying
# charge-sheets, and they charge two DIFFERENT, non-overlapping accused
# sets (Suresh+Iqbal vs Ramesh alone) -- proving the s.111 count is taken
# per syndicate, not per accused.
CS_QUALIFY_1 = add_charge_sheet(
    CASE_ROBBERY, FIR_MO_1, day=235, accused_fir_id=FIR_MO_1,
    cognizance_date=dt(days=235), offence_cognizable=True, max_punishment_years=3,
)
CS_QUALIFY_2 = add_charge_sheet(
    CASE_ROBBERY, FIR_MO_3, day=415, accused_fir_id=FIR_MO_3,
    cognizance_date=dt(days=415), offence_cognizable=True, max_punishment_years=4,
)
# CS_TOO_OLD: otherwise-qualifying, but its cognizance_date falls outside
# the 10-year lookback measured from the syndicate's latest cognizance
# date (day 425 below) -- excluded by the lookback window alone.
CS_TOO_OLD = add_charge_sheet(
    CASE_ORGANIZED_CRIME, FIR_ORG_3, day=425 - 3700, accused_fir_id=FIR_ORG_3,
    cognizance_date=dt(days=425 - 3700), offence_cognizable=True, max_punishment_years=5,
)
# CS_NOT_COGNIZABLE: within the lookback window and above the punishment
# floor, excluded only because the offence is not cognizable.
CS_NOT_COGNIZABLE = add_charge_sheet(
    CASE_ORGANIZED_CRIME, FIR_ORG_3, day=420, accused_fir_id=FIR_ORG_3,
    cognizance_date=dt(days=420), offence_cognizable=False, max_punishment_years=5,
)
# CS_LOW_PUNISHMENT: within the lookback window and cognizable, excluded
# only because max_punishment_years falls below the 3-year floor.
CS_LOW_PUNISHMENT = add_charge_sheet(
    CASE_ORGANIZED_CRIME, FIR_ORG_3, day=425, accused_fir_id=FIR_ORG_3,
    cognizance_date=dt(days=425), offence_cognizable=True, max_punishment_years=2,
)
# CS_NEGATIVE_LONE: a single-accused charge-sheet that would qualify on its
# own merits -- proves a lone accused never forms a "syndicate" of one.
CS_NEGATIVE_LONE = add_charge_sheet(
    CASE_ORGANIZED_CRIME, FIR_ORG_NEGATIVE, day=305, accused_fir_id=FIR_ORG_NEGATIVE,
    cognizance_date=dt(days=305), offence_cognizable=True, max_punishment_years=5,
)

ground_truth["cases"][CASE_ORGANIZED_CRIME] = {
    "title": "Organized Crime - Interstate Vehicle Theft Syndicate",
    "linked_case_id": CASE_ROBBERY,
    "shared_vehicle": "KA05AB1234",
    "shared_phones_interstate": ["9830000001", "9830000002"],
    "shared_phone_cross_case_only": "9830000009",
    "cross_case_link_min_firs": 2,
    "interstate_alert_min_firs": 3,
    "syndicate_accused_names": ["Suresh Pawar", "Iqbal Sheikh", "Ramesh Yadav", "Deepak Malhotra"],
    "qualifying_charge_sheet_ids": [CS_QUALIFY_1, CS_QUALIFY_2],
    "excluded_too_old_charge_sheet_id": CS_TOO_OLD,
    "excluded_not_cognizable_charge_sheet_id": CS_NOT_COGNIZABLE,
    "excluded_low_punishment_charge_sheet_id": CS_LOW_PUNISHMENT,
    "negative_control_lone_accused": "Manoj Bhatt",
    "negative_control_lone_charge_sheet_id": CS_NEGATIVE_LONE,
    "negative_control_fir_id": FIR_ORG_NEGATIVE,
}

# ---------------------------------------------------------------------------
# Background noise: unrelated random activity for realism / false-positive testing
# ---------------------------------------------------------------------------
NOISE_PHONES = [f"97000{str(i).zfill(5)}" for i in range(1, 25)]
for i in range(80):
    a, b = RNG.sample(NOISE_PHONES, 2)
    add_cdr(a, b, day=RNG.randint(0, 110), hour=RNG.randint(6, 22), minute=RNG.randint(0, 59),
            duration=RNG.randint(10, 600))
NOISE_ACCOUNTS = [f"NAC{str(i).zfill(4)}" for i in range(1, 25)]
for i in range(60):
    a, b = RNG.sample(NOISE_ACCOUNTS, 2)
    add_txn(a, b, amount=RNG.randint(500, 30000), day=RNG.randint(0, 110), hour=RNG.randint(6, 22),
            minute=RNG.randint(0, 59))
for i, day in enumerate([15, 40, 65, 90]):
    add_fir(CASE_FRAUD, "MG Road Police Station", day,
            f"Unrelated complaint {i+1}: petty theft reported, no suspects identified at this time.")


def generate(reset: bool = True):
    init_db(reset=reset)
    conn = get_connection()
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO cases (case_id, title, category, opened_date) VALUES (?, ?, ?, ?)",
        [
            (CASE_FRAUD, "Fraud Ring Alpha", "financial_fraud", dt(days=0)),
            (CASE_TRAFFICKING, "Missing Persons - Sonepur Corridor", "women_safety", dt(days=100)),
            (CASE_NARCOTICS, "Narcotics - Sonepur Storage Unit", "narcotics", dt(days=150)),
            (CASE_ROBBERY, "Robbery/Theft - Ring Bazaar Vehicle Theft Ring", "robbery_theft", dt(days=200)),
            (CASE_ROBBERY_RECOVERY, "Recovered Property - Ring Bazaar Raid", "robbery_theft", dt(days=215)),
            (CASE_ASSAULT, "Assault/Homicide - Riverside Custodial Death", "assault_homicide", dt(days=500)),
            (CASE_ASSAULT_COLDCASE, "Assault/Homicide - Riverside Cold Case", "assault_homicide", dt(days=100)),
            (CASE_ASSAULT_CLEAN, "Assault/Homicide - Lakeview Compliant Investigation", "assault_homicide", dt(days=520)),
            (CASE_ORGANIZED_CRIME, "Organized Crime - Interstate Vehicle Theft Syndicate", "organized_crime", dt(days=600)),
        ],
    )
    cur.executemany(
        "INSERT INTO case_case_types (case_id, case_type, status, confidence, reason, confirmed_by, confirmed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        case_case_type_rows,
    )
    cur.executemany(
        "INSERT INTO case_property (property_id, case_id, case_type, form_type, seizure_datetime, place, "
        "seizing_officer_json, witnesses_json, av_recording_id, recording_hash, forwarded_to_magistrate_ts, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        case_property_rows,
    )
    cur.executemany(
        "INSERT INTO property_item (item_id, property_id, description, quantity, unit, gross_weight, "
        "net_weight, identifiers_json, exhibit_mark, seal_description, seal_count, estimated_value) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        property_item_rows,
    )
    cur.executemany(
        "INSERT INTO custody_event (event_id, property_id, event_type, event_ts, register_no, "
        "road_certificate_no, from_location, to_location, countersigned_by, seals_intact_and_tallied, "
        "report_no, conclusion_category, attributes_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        custody_event_rows,
    )
    cur.executemany(
        "INSERT INTO ndps_sampling (memo_id, property_id, crime_no, drug_description, net_weight_seized, "
        "lot_size, date_of_draw_of_sample, num_samples, sample_weight_each, prepared_in_triplicate, "
        "magistrate_certification_ts, net_weight_lab_received, lab_date_of_receipt, disposal_form7_ref, "
        "disposal_form10_ref, conveyance_chassis_no, conveyance_engine_no) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ndps_sampling_rows,
    )
    cur.executemany(
        "INSERT INTO fir_records (fir_id, case_id, station, date, text) VALUES (?, ?, ?, ?, ?)",
        fir_rows,
    )
    cur.executemany(
        "INSERT INTO crime_mo_record (record_id, case_id, fir_id, date, method_1, conveyance, "
        "character_assumed, place_type, property_type, time_of_day_band, language_dialect, "
        "operates_with_accomplices, is_recidivist, is_generally_armed) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        crime_mo_record_rows,
    )
    cur.executemany(
        "INSERT INTO post_mortem_report (pm_id, case_id, fir_id, deceased_name, date_of_death, "
        "date_of_postmortem, doctor_name, place, cause_of_death, injury_list_json, rectal_temperature, "
        "rigor_mortis_state, rigor_mortis_time_estimate, viscera_preserved, viscera_sent_to_fsl_ts, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        post_mortem_report_rows,
    )
    cur.executemany(
        "INSERT INTO inquest_report (inquest_id, case_id, fir_id, deceased_name, inquest_date, "
        "place_of_occurrence, witness_count, witnesses_json, injury_list_json, conducting_officer, "
        "is_custodial_death, death_ts, intimation_ts, body_forwarded_ts, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        inquest_report_rows,
    )
    cur.executemany(
        "INSERT INTO mlc_record (mlc_id, case_id, fir_id, patient_name, hospital, date_of_examination, "
        "injury_list_json, injury_classification, treating_doctor, follow_up_days, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        mlc_record_rows,
    )
    cur.executemany(
        "INSERT INTO forensic_match (match_id, match_type, case_id_a, case_id_b, exhibit_a, exhibit_b, "
        "match_confidence_numeric, match_confidence_category, examiner_asserted, examiner_name, "
        "fsl_report_no, report_date, identifier_value, attributes_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        forensic_match_rows,
    )
    cur.executemany(
        "INSERT INTO tower_location_record (record_id, case_id, phone, cell_id, locality_name, timestamp, "
        "is_certified_65b, certificate_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        tower_location_record_rows,
    )
    cur.executemany(
        "INSERT INTO missing_person_report (missing_person_id, case_id, fir_id, name, age, sex, height_cm, "
        "build, complexion, hair, clothing_description, dress_colour_tokens_json, distinguishing_marks, "
        "last_seen_date, last_seen_place, last_seen_circumstances, district, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        missing_person_report_rows,
    )
    cur.executemany(
        "INSERT INTO uidb_record (uidb_id, case_id, uidb_serial_no, state, district, police_station, "
        "age_from, age_to, sex, found_date, height_cm, religion, dd_number, dd_date, fir_no, found_place, "
        "parentage, address, build, complexion, face, hair, eyes, beard, mustaches, dress_upper, "
        "dress_upper_colour, dress_lower, dress_lower_colour, remarks, police_post, pm_id, reward_amount, "
        "notification_no, notification_date, matched_missing_serial_no, matching_date, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "?, ?, ?, ?, ?, ?, ?)",
        uidb_record_rows,
    )
    cur.executemany(
        "INSERT INTO dna_sample_record (sample_id, case_id, pm_id, sample_source, collected_ts, dispatch_ts, "
        "dispatch_delay_reason, conclusion_category, expert_examined, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        dna_sample_record_rows,
    )
    cur.executemany(
        "INSERT INTO charge_sheet (charge_sheet_id, case_id, fir_id, cognizance_date, offence_cognizable, "
        "max_punishment_years, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        charge_sheet_rows,
    )
    cur.executemany(
        "INSERT INTO intel_records (record_id, case_id, source_category, reporting_unit, date, text) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        intel_rows,
    )
    cur.executemany(
        "INSERT INTO cdr_records (record_id, caller, callee, timestamp, duration_sec) VALUES (?, ?, ?, ?, ?)",
        cdr_rows,
    )
    cur.executemany(
        "INSERT INTO transaction_records (record_id, sender, receiver, amount, timestamp) VALUES (?, ?, ?, ?, ?)",
        txn_rows,
    )
    conn.commit()
    conn.close()

    with open(GROUND_TRUTH_PATH, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    return {
        "cases": 2,
        "fir_records": len(fir_rows),
        "intel_records": len(intel_rows),
        "cdr_records": len(cdr_rows),
        "transaction_records": len(txn_rows),
    }


if __name__ == "__main__":
    stats = generate(reset=True)
    print(json.dumps(stats, indent=2))
