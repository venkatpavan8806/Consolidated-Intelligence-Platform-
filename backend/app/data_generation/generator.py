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


# ---------------------------------------------------------------------------
# CASE 1: Fraud Ring Alpha
# ---------------------------------------------------------------------------
CASE_FRAUD = "C001"

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
        ],
    )
    cur.executemany(
        "INSERT INTO fir_records (fir_id, case_id, station, date, text) VALUES (?, ?, ?, ?, ?)",
        fir_rows,
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
