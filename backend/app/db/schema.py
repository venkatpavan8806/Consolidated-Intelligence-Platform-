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
