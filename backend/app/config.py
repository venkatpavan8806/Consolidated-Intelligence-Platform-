import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "cip.db")
GROUND_TRUTH_PATH = os.path.join(DATA_DIR, "ground_truth.json")
PIPELINE_TIMINGS_PATH = os.path.join(DATA_DIR, "last_pipeline_run.json")

os.makedirs(DATA_DIR, exist_ok=True)

JWT_SECRET = os.environ.get("CIP_JWT_SECRET", "dev-only-secret-change-in-production")
JWT_ALGORITHM = "HS256"

# Role-typing / exclusion thresholds
UTILITY_MIN_IN_DEGREE = 8
UTILITY_MAX_OUT_DEGREE = 0

# Burner-SIM rotation detection thresholds
BURNER_MIN_CONTACT_SET_SIZE = 6
BURNER_MIN_SHARED_CONTACTS = 5
BURNER_MIN_JACCARD = 0.5
BURNER_MAX_GAP_DAYS = 10

# Mule layering thresholds
MULE_MIN_FAN_IN = 5
MULE_WINDOW_DAYS = 10

# Cross-source temporal motif
MOTIF_CALL_BEFORE_TRANSFER_MIN_MINUTES = 5
MOTIF_CALL_BEFORE_TRANSFER_MAX_MINUTES = 45

# Women-Safety / structural bridge path
BRIDGE_LOW_DEGREE_MAX = 3
BRIDGE_LOW_VOLUME_MAX = 3
BRIDGE_HIGH_DEGREE_MIN = 4
RECRUITER_MIN_FANOUT = 3
RECRUITER_FANOUT_MAX_DEGREE = 3  # "low-degree" contacts of the recruiter

# Repeat location signal
REPEAT_LOCATION_MIN_SOURCES = 3

# NDPS Physical-evidence compliance thresholds (Part B3 of the Sept 2026
# research; sourced to GSR 899(E) 23.12.2022 sampling rules unless marked).
# Sample quantity to be drawn per package/lot, in grams -- below this and
# the sample itself is non-compliant regardless of how much was seized.
NDPS_SAMPLE_MIN_GRAMS = {
    "heroin": 5, "cocaine": 5,
    "poppy straw": 100,
    "ganja": 24, "opium": 24, "charas": 24,
}
NDPS_SAMPLE_MIN_GRAMS_DEFAULT = 5  # "other powders/liquids" per the Rules
# Max identical packages bunched into one lot before a fresh lot is required.
NDPS_LOT_SIZE_MAX_DEFAULT = 10
NDPS_LOT_SIZE_MAX_BULK = {"ganja": 40, "poppy straw": 40, "charas": 40}
# Weight-mismatch tolerance between the Test Memo's seizure weight and the
# lab's received weight -- a *Bharat Aambale* "discrepancy in physical
# evidence" once exceeded. [I] design default, not an official figure.
NDPS_WEIGHT_MISMATCH_TOLERANCE_FRACTION = 0.01
NDPS_WEIGHT_MISMATCH_TOLERANCE_GRAMS = 0.5

# Case-type classification (Axis B). Controlled 6-value case-type field,
# replacing the old free-text cases.category. The classifier only ever
# writes status='SUGGESTED' rows to case_case_types -- an investigator must
# confirm or reject before any case-type-scoped module treats the case as
# that type (see HANDOFF.md Section 4: "Do not build a version that
# auto-activates modules without confirmation").
CASE_TYPES = [
    "FINANCIAL_FRAUD",
    "TRAFFICKING_MISSING_PERSON",
    "NARCOTICS",
    "ASSAULT_HOMICIDE",
    "ROBBERY_THEFT",
    "ORGANIZED_CRIME",
]

# Legacy free-text cases.category -> new controlled case-type, used only to
# migrate/seed the three original demo cases; new cases are classified fresh.
LEGACY_CATEGORY_TO_CASE_TYPE = {
    "financial_fraud": "FINANCIAL_FRAUD",
    "women_safety": "TRAFFICKING_MISSING_PERSON",
    "narcotics": "NARCOTICS",
}

# Structured-signal weight: a detector/lead of a case-type-mapped lead_type
# actually firing on entities/records tied to this case is strong,
# highly-specific evidence -- each distinct lead_type contributes this much
# confidence (capped), separately from how many individual leads of that
# type exist (five burner-rotation leads is not 5x more "financial fraud"
# than one).
CLASSIFIER_STRUCTURAL_SIGNAL_WEIGHT = 0.4
CLASSIFIER_STRUCTURAL_SIGNAL_MAX = 0.8

# Keyword-signal weight: a curated term appearing in the case's free-text
# FIR/intel narratives is weaker, lower-precision evidence (a word can
# appear in an unrelated sentence) -- each distinct matched keyword group
# contributes less, and is capped lower than any single structural signal.
CLASSIFIER_KEYWORD_SIGNAL_WEIGHT = 0.12
CLASSIFIER_KEYWORD_SIGNAL_MAX = 0.35

# A case type is only suggested once its combined score clears this floor --
# below it, whatever matched is too thin to put in front of an investigator.
CLASSIFIER_SUGGESTION_THRESHOLD = 0.2

# Curated, deterministic keyword lexicon per case type. Plain substring
# matching (case-insensitive) on FIR/intel narrative text -- no ML, no
# embeddings, per the governing "no black-box ML" rule. Every term here is
# a real procedural/legal term an investigator would recognise, not a
# guessed synonym; a case type with no research-grounded structured
# detector yet (Assault/Homicide, Robbery/Theft, Organized Crime -- see
# HANDOFF.md Section 6 checklist) still gets an honest, text-only signal
# rather than nothing, but its confidence is capped lower than a
# structurally-grounded suggestion so the investigator can see the
# difference in the "reason" field.
CASE_TYPE_KEYWORDS = {
    "FINANCIAL_FRAUD": [
        "cyber fraud", "phishing", "otp fraud", "ponzi", "fraudulent transaction",
        "fake investment", "money laundering", "cheating", "embezzlement",
        "mule account", "shell company", "layering", "forged document",
    ],
    "TRAFFICKING_MISSING_PERSON": [
        "missing person", "trafficking", "human trafficking", "abducted",
        "kidnapped", "recruiter", "lured", "rescued", "forced labour",
        "immoral traffic", "unidentified dead body", "missing since",
    ],
    "NARCOTICS": [
        "ndps", "narcotic", "psychotropic", "charas", "ganja", "heroin",
        "cocaine", "poppy straw", "opium", "drug peddler", "contraband",
        "seizure of narcotic",
    ],
    "ASSAULT_HOMICIDE": [
        "murder", "homicide", "culpable homicide", "grievous hurt", "assault",
        "stabbed", "post-mortem", "postmortem", "fatal injuries",
        "inquest", "attempt to murder",
    ],
    "ROBBERY_THEFT": [
        "robbery", "dacoity", "theft", "stolen", "burglary", "house-breaking",
        "snatching", "looted", "break-in", "chain snatching",
    ],
    "ORGANIZED_CRIME": [
        "organized crime", "organised crime", "syndicate", "gang", "mcoca",
        "extortion", "contract killing", "criminal conspiracy", "underworld",
    ],
}

# lead_type -> case_type this lead is strong structural evidence for.
# BROKER_BRIDGE is deliberately excluded: HANDOFF.md marks it "General /
# cross-cutting (applies to any case type)", so it carries no case-type
# signal on its own.
CLASSIFIER_LEAD_TYPE_TO_CASE_TYPE = {
    "BURNER_ROTATION": "FINANCIAL_FRAUD",
    "MULE_LAYERING": "FINANCIAL_FRAUD",
    "CALL_BEFORE_TRANSFER": "FINANCIAL_FRAUD",
    "WOMEN_SAFETY_RECRUITER": "TRAFFICKING_MISSING_PERSON",
    "WOMEN_SAFETY_TRANSPORTER": "TRAFFICKING_MISSING_PERSON",
    "REPEAT_LOCATION": "TRAFFICKING_MISSING_PERSON",
    "NDPS_COMPLIANCE": "NARCOTICS",
}

# Missing link recovery
LINK_RECOVERY_MASK_FRACTION = 0.2
LINK_RECOVERY_WEIGHT_STRUCTURAL = 0.6
LINK_RECOVERY_WEIGHT_CROSS_SOURCE = 0.4
LINK_RECOVERY_HIGH_THRESHOLD = 0.66
LINK_RECOVERY_MEDIUM_THRESHOLD = 0.4
