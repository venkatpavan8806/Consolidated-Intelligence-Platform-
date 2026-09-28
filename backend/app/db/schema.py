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

-- ---------------------------------------------------------------------
-- Assault/Homicide Physical + Digital evidence (Sept 2026 pivot, module 3).
--
-- post_mortem_report / inquest_report are deliberately kept generic --
-- no case_type column, no FK into the case_property/form_type spine --
-- so the future Trafficking/Missing-Person UIDB (unidentified dead body)
-- work can reuse this SAME pair rather than duplicating it, per the
-- research pass's explicit recommendation. A UIDB case simply has an
-- inquest_report/post_mortem_report with no confirmed deceased_name yet.
-- ---------------------------------------------------------------------

-- NHRC Model Autopsy Form (Annexure I) fields verified by the research
-- pass; rectal_temperature/rigor_mortis fields are the two the research
-- flagged as most commonly missing/incomplete in practice.
CREATE TABLE IF NOT EXISTS post_mortem_report (
    pm_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    fir_id TEXT,
    deceased_name TEXT,
    date_of_death TEXT,
    date_of_postmortem TEXT,
    doctor_name TEXT,
    place TEXT,
    cause_of_death TEXT,
    injury_list_json TEXT NOT NULL DEFAULT '[]',
    rectal_temperature REAL,
    rigor_mortis_state TEXT,
    rigor_mortis_time_estimate TEXT,
    viscera_preserved INTEGER,
    viscera_sent_to_fsl_ts TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

-- BNSS s.194 (<- CrPC s.174) inquest report + BNSS s.196 (<- CrPC s.176)
-- custodial-death intimation fields. death_ts/intimation_ts are kept as
-- full timestamps (the real forms are date-only) because the custodial-
-- death intimation-timing check and the Physical+Digital spatio-temporal
-- correlation signal both need genuine timestamps, not just dates.
CREATE TABLE IF NOT EXISTS inquest_report (
    inquest_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    fir_id TEXT,
    deceased_name TEXT,
    inquest_date TEXT,
    place_of_occurrence TEXT,
    witness_count INTEGER,
    witnesses_json TEXT NOT NULL DEFAULT '[]',
    injury_list_json TEXT NOT NULL DEFAULT '[]',
    conducting_officer TEXT,
    is_custodial_death INTEGER NOT NULL DEFAULT 0,
    death_ts TEXT,
    intimation_ts TEXT,
    body_forwarded_ts TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

-- Medico-Legal Case record for a non-fatal assault (BNS s.116, <- IPC
-- s.320 grievous-hurt classification).
CREATE TABLE IF NOT EXISTS mlc_record (
    mlc_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    fir_id TEXT,
    patient_name TEXT,
    hospital TEXT,
    date_of_examination TEXT,
    injury_list_json TEXT NOT NULL DEFAULT '[]',
    injury_classification TEXT,  -- SIMPLE | GRIEVOUS
    treating_doctor TEXT,
    follow_up_days INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

-- Polymorphic forensic-match record. match_confidence is deliberately
-- represented as TWO separate columns rather than one, because Indian
-- fingerprint reports report a numeric points-of-similarity score while
-- ballistics AND DNA reports report a categorical outcome (matches /
-- excludes / degraded / inconclusive) -- collapsing these into one numeric
-- field would misrepresent what a DNA/ballistics report actually says.
-- examiner_asserted distinguishes a real database hit (AFIS/NAFIS
-- fingerprint search -- India's only verified NETWORKED forensic database)
-- from an examiner's own opinion comparing two named exhibits (ballistics
-- has NO verified national networked database per the research pass, so
-- every ballistics cross-case link here MUST be examiner_asserted=1).
CREATE TABLE IF NOT EXISTS forensic_match (
    match_id TEXT PRIMARY KEY,
    match_type TEXT NOT NULL,  -- FINGERPRINT | BALLISTICS | DNA
    case_id_a TEXT NOT NULL,
    case_id_b TEXT NOT NULL,
    exhibit_a TEXT NOT NULL,
    exhibit_b TEXT NOT NULL,
    match_confidence_numeric REAL,     -- fingerprint: points of similarity
    match_confidence_category TEXT,    -- ballistics/DNA: MATCHES | EXCLUDES | DEGRADED | INCONCLUSIVE
    examiner_asserted INTEGER NOT NULL DEFAULT 0,
    examiner_name TEXT,
    fsl_report_no TEXT,
    report_date TEXT,
    identifier_value TEXT,  -- NFN for fingerprint, exhibit F-no for ballistics
    attributes_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(case_id_a) REFERENCES cases(case_id),
    FOREIGN KEY(case_id_b) REFERENCES cases(case_id)
);

-- Digital-evidence cell-site/tower-dump pings, kept separate from
-- cdr_records (call-to-call records) since a tower ping has no callee --
-- it's a location fix, not a call. is_certified_65b tracks the BSA 2023
-- s.63 / Evidence Act s.65B(4) certificate that *Anvar P.V.*, *Arjun
-- Panditrao Khotkar* and *Rahil v. State (NCT of Delhi)* (2025 INSC 858)
-- all make a condition precedent for this record to be usable at all.
CREATE TABLE IF NOT EXISTS tower_location_record (
    record_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    phone TEXT NOT NULL,
    cell_id TEXT,
    locality_name TEXT,
    timestamp TEXT NOT NULL,
    is_certified_65b INTEGER NOT NULL DEFAULT 0,
    certificate_ref TEXT,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

-- ---------------------------------------------------------------------
-- Trafficking/Missing-Person Physical evidence: Unidentified Dead Body
-- (UIDB) <-> missing-person candidate matching (Sept 2026 pivot, module 4).
-- Deliberately joins to the SAME post_mortem_report table Assault/Homicide
-- uses (via uidb_record.pm_id) rather than a duplicate table, per the
-- research pass's explicit recommendation that the UIDB/DNA material is
-- "the post-mortem/body-identification complement" to the live-trafficking
-- digital signals, not an unrelated schema.
-- ---------------------------------------------------------------------

-- Missing-person intake fields (DE-G's field list, said to mirror NCRB's
-- NCMP proforma but NOT independently verified against a government form
-- by either research pass -- flagged [I] "best-effort draft, needs SME/
-- police-officer review" rather than presented as a verified form, unlike
-- the ZIPNET UIDB fields below which ARE verified).
CREATE TABLE IF NOT EXISTS missing_person_report (
    missing_person_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    fir_id TEXT,
    name TEXT,
    age INTEGER,
    sex TEXT,  -- MALE | FEMALE | OTHER
    height_cm REAL,
    build TEXT,
    complexion TEXT,
    hair TEXT,
    clothing_description TEXT,
    dress_colour_tokens_json TEXT NOT NULL DEFAULT '[]',
    distinguishing_marks TEXT,
    last_seen_date TEXT,
    last_seen_place TEXT,
    last_seen_circumstances TEXT,
    district TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN | RESOLVED | CLOSED
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

-- ZIPNET "Unidentified Persons Found" / UIDB "Add Record" fields, verbatim
-- per the Delhi Police ZIPNET form the research pass verified --
-- including matched_missing_serial_no, ZIPNET's OWN real cross-case-
-- linking field (not a design proposal): the platform's job per the
-- research is to detect when this field SHOULD be populated but isn't
-- (see the candidate-match detector) and when it IS populated but the
-- linked missing-person case is still shown open (the "ignored match"
-- signal -- a real, exploitable data-quality/process-failure pattern).
CREATE TABLE IF NOT EXISTS uidb_record (
    uidb_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    uidb_serial_no TEXT,
    state TEXT,
    district TEXT,
    police_station TEXT,
    age_from INTEGER,
    age_to INTEGER,
    sex TEXT,
    found_date TEXT,
    height_cm REAL,
    religion TEXT,
    dd_number TEXT,
    dd_date TEXT,
    fir_no TEXT,
    found_place TEXT,
    parentage TEXT,
    address TEXT,
    build TEXT,
    complexion TEXT,
    face TEXT,
    hair TEXT,
    eyes TEXT,
    beard TEXT,
    mustaches TEXT,
    dress_upper TEXT,
    dress_upper_colour TEXT,
    dress_lower TEXT,
    dress_lower_colour TEXT,
    remarks TEXT,
    police_post TEXT,
    pm_id TEXT,  -- links to post_mortem_report.pm_id (the shared spine, not a new table)
    reward_amount REAL,
    notification_no TEXT,
    notification_date TEXT,
    matched_missing_serial_no TEXT,  -- ZIPNET's own real UIDB<->missing-person link field
    matching_date TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id),
    FOREIGN KEY(pm_id) REFERENCES post_mortem_report(pm_id)
);

-- DNA sample chain-of-custody for an unidentified body, kept separate from
-- forensic_match (which compares two named EXHIBITS) because this table
-- tracks whether a sample was drawn and dispatched AT ALL, and how -- the
-- "was a DNA sample even taken" question the Rajasthan HC/*Lokniti*
-- preservation logic and *Kattavellai*'s 48-hour dispatch direction are
-- both about. conclusion_category is categorical for the same reason it
-- is on forensic_match: no Indian DNA report retrieved by the research
-- states a likelihood ratio or percentage.
CREATE TABLE IF NOT EXISTS dna_sample_record (
    sample_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    pm_id TEXT,
    sample_source TEXT,  -- MOLAR_TOOTH | STERNUM | BLOOD_ON_GAUZE | OTHER
    collected_ts TEXT,
    dispatch_ts TEXT,
    dispatch_delay_reason TEXT,
    conclusion_category TEXT,  -- MATCHES | EXCLUDES | DEGRADED_NO_PROFILE | INCONCLUSIVE
    expert_examined INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id),
    FOREIGN KEY(pm_id) REFERENCES post_mortem_report(pm_id)
);

-- ---------------------------------------------------------------------
-- Organized Crime (Sept 2026 pivot, module 5) -- the "reference case type"
-- for the platform's whole cross-case-linking architecture, per the
-- research pass, since Organized Crime is definitionally about linking
-- multiple FIRs/charge-sheets to a syndicate, not just an investigative
-- aid on top of a single case. This module is what finally populates
-- common_identifier_index (see that table's original comment above) via
-- app/linking/common_identifiers.py's backfill, rather than leaving it an
-- unused placeholder.
--
-- charge_sheet + charge_sheet_accused implement BNS s.111 (<- MCOCA
-- s.2(1)(d))'s own statutory test verbatim: "more than one charge-sheet...
-- within the preceding period of ten years... that Court has taken
-- cognizance," for a cognizable offence carrying >=3 years. Per *Zakir
-- Abdul Mirajkar v. State of Maharashtra* (2022 LiveLaw (SC) 707) and
-- *Kavitha Lankesh v. State of Karnataka* (2022) 12 SCC 753, this count is
-- taken PER SYNDICATE, not per individual accused -- which is exactly why
-- charge_sheet_accused is a many-to-many join, not a single accused column
-- on charge_sheet.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS charge_sheet (
    charge_sheet_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    fir_id TEXT,
    cognizance_date TEXT,  -- NULL until a competent Court has taken cognizance
    offence_cognizable INTEGER NOT NULL DEFAULT 1,
    max_punishment_years INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS charge_sheet_accused (
    charge_sheet_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    PRIMARY KEY (charge_sheet_id, entity_id),
    FOREIGN KEY(charge_sheet_id) REFERENCES charge_sheet(charge_sheet_id)
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
