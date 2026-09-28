import sqlite3
from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    opened_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fir_records (
    fir_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    station TEXT NOT NULL,
    date TEXT NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

-- Free-text intelligence products distinct from FIRs: field surveillance
-- reports and reports passed down from intelligence agencies. Structurally
-- identical to fir_records (unstructured narrative text) since they go
-- through the same NLP extraction pipeline, but kept as a separate table so
-- provenance (which source category a fact came from) is never lost.
CREATE TABLE IF NOT EXISTS intel_records (
    record_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    source_category TEXT NOT NULL,
    reporting_unit TEXT NOT NULL,
    date TEXT NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS cdr_records (
    record_id TEXT PRIMARY KEY,
    caller TEXT NOT NULL,
    callee TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    duration_sec INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS transaction_records (
    record_id TEXT PRIMARY KEY,
    sender TEXT NOT NULL,
    receiver TEXT NOT NULL,
    amount REAL NOT NULL,
    timestamp TEXT NOT NULL
);

-- raw mentions extracted from FIR text (NER + regex)
CREATE TABLE IF NOT EXISTS entity_mentions (
    mention_id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    text TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    fir_role TEXT,
    extraction_method TEXT NOT NULL,
    extraction_score REAL NOT NULL,
    span_start INTEGER,
    span_end INTEGER
);

-- canonical resolved entities
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_value TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    is_official INTEGER NOT NULL DEFAULT 0,
    is_utility INTEGER NOT NULL DEFAULT 0
);

-- mapping of a mention (or a structured identifier occurrence) to a canonical entity
CREATE TABLE IF NOT EXISTS mention_entity_map (
    mention_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    PRIMARY KEY (mention_id, entity_id)
);

-- unresolved ambiguous groups for human review (one row per cluster, not per pair)
CREATE TABLE IF NOT EXISTS review_queue (
    cluster_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    mention_ids_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
);

-- graph edges (materialized, typed, with epistemic status)
CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    source_record_id TEXT,
    source_record_type TEXT,
    timestamp TEXT,
    epistemic_status TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    attributes_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    case_id TEXT,
    reason TEXT,
    payload_raw TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_dispositions (
    lead_id TEXT PRIMARY KEY,
    disposition TEXT NOT NULL,
    actor TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS case_assignments (
    username TEXT NOT NULL,
    case_id TEXT NOT NULL,
    PRIMARY KEY (username, case_id)
);

-- ---------------------------------------------------------------------
-- Physical/Digital evidence-axis pivot (Sept 2026 mentor-directed pivot).
--
-- Two independent axes:
--   Axis A (Evidence Type): DIGITAL vs PHYSICAL, a property of each record.
--     Digital = fir_records/intel_records/cdr_records/transaction_records
--     (unchanged, already existed). Physical = case_property + its child
--     tables below (new).
--   Axis B (Case Type): a controlled 6-value enum, a property of the CASE,
--     replacing the old free-text cases.category. A case can have MULTIPLE
--     active case types at once (e.g. Financial + Assault), so this is a
--     many-to-many table, not a column on `cases`. case_type values:
--     FINANCIAL_FRAUD | TRAFFICKING_MISSING_PERSON | NARCOTICS |
--     ASSAULT_HOMICIDE | ROBBERY_THEFT | ORGANIZED_CRIME.
--
-- cases.category is left in place for backward compatibility with existing
-- code/data; case_case_types is the new source of truth going forward.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS case_case_types (
    case_id TEXT NOT NULL,
    case_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SUGGESTED',  -- SUGGESTED | CONFIRMED | REJECTED
    confidence REAL,
    reason TEXT,
    confirmed_by TEXT,
    confirmed_at TEXT,
    PRIMARY KEY (case_id, case_type),
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

-- Shared Physical-evidence lifecycle spine, per the research-verified
-- seizure -> Malkhana -> forwarding -> FSL -> court-property-number chain
-- that recurs across all 6 case types (panchnama, NDPS Test Memo, digital-
-- device seizure memo, UIDB record, etc. are all instances of this same
-- shape via form_type). One row per seizure/panchnama-equivalent event;
-- case-type-specific child tables (e.g. ndps_sampling) carry the extra
-- verified fields a given form_type needs beyond this common shell.
CREATE TABLE IF NOT EXISTS case_property (
    property_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    case_type TEXT NOT NULL,
    form_type TEXT NOT NULL,  -- PANCHNAMA | NDPS_TEST_MEMO | DIGITAL_DEVICE_MEMO | UIDB_RECORD | ...
    seizure_datetime TEXT NOT NULL,
    place TEXT,
    seizing_officer_json TEXT NOT NULL DEFAULT '{}',
    witnesses_json TEXT NOT NULL DEFAULT '[]',
    av_recording_id TEXT,
    recording_hash TEXT,
    forwarded_to_magistrate_ts TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

-- Exhibit/item child of a seizure (Part C SC0 stage 2).
CREATE TABLE IF NOT EXISTS property_item (
    item_id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL,
    description TEXT NOT NULL,
    quantity REAL,
    unit TEXT,
    gross_weight REAL,
    net_weight REAL,
    identifiers_json TEXT NOT NULL DEFAULT '{}',  -- serial/IMEI/chassis/engine etc.
    exhibit_mark TEXT,  -- e.g. "F1", "EC1", "Exhibit A", "DNA 1496[A]/18"
    seal_description TEXT,
    seal_count INTEGER,
    estimated_value REAL,  -- INR; used by the Robbery/Theft stolen<->recovered
                            -- property-match signal's +/-20% value-tolerance rule
    FOREIGN KEY(property_id) REFERENCES case_property(property_id)
);

-- Custody-chain events after seizure -- Malkhana deposit, movement between
-- locations, lab receipt/report, court disposal (Part C SC0 stages 3-5),
-- modeled as one typed event log rather than three separate tables: every
-- compliance/cross-case signal (custody gap, missing road certificate,
-- seal mismatch) only needs "what happened, when, who countersigned"
-- regardless of which lifecycle stage it is.
CREATE TABLE IF NOT EXISTS custody_event (
    event_id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- MALKHANA_DEPOSIT | MOVEMENT | LAB_RECEIPT | LAB_REPORT | COURT_DISPOSAL
    event_ts TEXT NOT NULL,
    register_no TEXT,
    road_certificate_no TEXT,
    from_location TEXT,
    to_location TEXT,
    countersigned_by TEXT,
    seals_intact_and_tallied INTEGER,
    report_no TEXT,
    conclusion_category TEXT,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(property_id) REFERENCES case_property(property_id)
);

-- Narcotics Physical-evidence vertical slice: NDPS Test Memo (Form-6, Rule
-- 13(2) of the NDPS Seizure/Storage/Sampling/Disposal Rules 2022) plus the
-- s.52A magistrate-certification and disposal-chain fields that
-- *Yusuf @ Asif* / *Bharat Aambale* make outcome-determinative. Field names
-- follow the research-verified Test Memo + GSR 899(E) sampling-rule text.
CREATE TABLE IF NOT EXISTS ndps_sampling (
    memo_id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL,
    crime_no TEXT,
    drug_description TEXT NOT NULL,
    net_weight_seized REAL NOT NULL,
    lot_size INTEGER,
    date_of_draw_of_sample TEXT,
    num_samples INTEGER,
    sample_weight_each REAL,
    prepared_in_triplicate INTEGER NOT NULL DEFAULT 0,
    magistrate_certification_ts TEXT,
    net_weight_lab_received REAL,
    lab_date_of_receipt TEXT,
    disposal_form7_ref TEXT,   -- certificate of destruction
    disposal_form10_ref TEXT,  -- certificate of disposal
    conveyance_chassis_no TEXT,
    conveyance_engine_no TEXT,
    FOREIGN KEY(property_id) REFERENCES case_property(property_id)
);

-- Common identifier index (Part C SC2): the single shared join table every
-- cross-case digital rule is meant to key off -- MSISDN/IMEI/IMSI/account/
-- VPA/vehicle-registration/accused-ID, each with provenance. Populated
-- incrementally as each case-type module is built; not yet backfilled from
-- the pre-existing CDR/transaction tables (that backfill is a pipeline-
-- stage addition, tracked separately from this schema change).
CREATE TABLE IF NOT EXISTS common_identifier_index (
    identifier_id TEXT PRIMARY KEY,
    identifier_type TEXT NOT NULL,  -- MSISDN | IMEI | IMSI | ACCOUNT | VPA | VEHICLE_REG | ACCUSED_ID
    value TEXT NOT NULL,
    case_id TEXT NOT NULL,
    source_record_type TEXT,
    source_record_id TEXT,
    fir_no TEXT,
    police_station TEXT,
    date TEXT,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

-- Robbery/Theft Digital-evidence structured MO record, modeled on the real
-- NCRB IIF-II Crime Details Form (Item 4 "Type of crime") plus the IIF-III
-- offender-profile flags -- the national schema DE-Claude's research pass
-- found already exists for exactly this purpose, replacing any need for a
-- free-text-only MO comparison. One row per FIR; the MO-series detector
-- (app/detectors/robbery_theft_digital.py) compares rows pairwise.
CREATE TABLE IF NOT EXISTS crime_mo_record (
    record_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    fir_id TEXT NOT NULL,
    date TEXT NOT NULL,
    method_1 TEXT,           -- IIF-II "Method(s)" 1
    conveyance TEXT,         -- IIF-II "Conveyance(s) used"
    character_assumed TEXT,  -- IIF-II "Character assumed"
    place_type TEXT,         -- IIF-II "Type of place of occurrence"
    property_type TEXT,      -- IIF-II "Type of property stolen"
    time_of_day_band TEXT,   -- e.g. LATE_NIGHT | MORNING | AFTERNOON | EVENING
    language_dialect TEXT,   -- IIF-II "Language/Dialect used"
    operates_with_accomplices INTEGER,  -- IIF-III flag
    is_recidivist INTEGER,               -- IIF-III flag
    is_generally_armed INTEGER,          -- IIF-III flag
    FOREIGN KEY(case_id) REFERENCES cases(case_id),
    FOREIGN KEY(fir_id) REFERENCES fir_records(fir_id)
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db(reset: bool = False):
    import os
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
