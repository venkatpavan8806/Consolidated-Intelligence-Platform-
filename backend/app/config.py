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

# IMEI<->MSISDN device-continuity mapping (mentor-requested feature,
# grounded in the research pass's own DE-C findings: "IMEI from suspect's
# handset seen with a different SIM near the time -> SIM-swap-to-evade
# flag" and "Same IMEI active with a new SIM after the missing-date ->
# device-continuity lead"). A handset (IMEI) genuinely used by >=N distinct
# phone numbers over time is the signal -- one handset briefly lent to a
# family member is ordinary life, which is exactly why this is a candidate
# for human review, never an automated identity claim.
IMEI_MAPPING_MIN_DISTINCT_MSISDN = 2

# Mule layering thresholds
MULE_MIN_FAN_IN = 5
MULE_WINDOW_DAYS = 10

# Cross-source temporal motif
MOTIF_CALL_BEFORE_TRANSFER_MIN_MINUTES = 5
MOTIF_CALL_BEFORE_TRANSFER_MAX_MINUTES = 45

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
    "trafficking_missing_person": "TRAFFICKING_MISSING_PERSON",
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
    "NDPS_COMPLIANCE": "NARCOTICS",
    "ROBBERY_VEHICLE_LINK": "ROBBERY_THEFT",
    "ROBBERY_PROPERTY_MATCH": "ROBBERY_THEFT",
    "ROBBERY_LINGERING_PROPERTY": "ROBBERY_THEFT",
    "ROBBERY_MO_SERIES": "ROBBERY_THEFT",
    "ROBBERY_MO_SERIES_S112_CANDIDATE": "ROBBERY_THEFT",
    "INQUEST_WITNESS_VIOLATION": "ASSAULT_HOMICIDE",
    "INQUEST_PM_INJURY_MISMATCH": "ASSAULT_HOMICIDE",
    "POSTMORTEM_MISSING_TIMING_FIELDS": "ASSAULT_HOMICIDE",
    "CUSTODIAL_DEATH_INTIMATION_VIOLATION": "ASSAULT_HOMICIDE",
    "MLC_CLASSIFICATION_INCONSISTENCY": "ASSAULT_HOMICIDE",
    "FORENSIC_FINGERPRINT_MATCH": "ASSAULT_HOMICIDE",
    "FORENSIC_BALLISTICS_EXAMINER_ASSERTED": "ASSAULT_HOMICIDE",
    "FORENSIC_DNA_MATCH": "ASSAULT_HOMICIDE",
    "FORENSIC_CONFIDENCE_MISUSE": "ASSAULT_HOMICIDE",
    "UNCERTIFIED_TOWER_EVIDENCE": "ASSAULT_HOMICIDE",
    "SPATIOTEMPORAL_TOWER_CORRELATION": "ASSAULT_HOMICIDE",
    "UIDB_MISSING_PERSON_CANDIDATE_MATCH": "TRAFFICKING_MISSING_PERSON",
    "UIDB_IGNORED_ZIPNET_MATCH": "TRAFFICKING_MISSING_PERSON",
    "UIDB_UNSAMPLED_BODY": "TRAFFICKING_MISSING_PERSON",
    "UIDB_LATE_DNA_DISPATCH": "TRAFFICKING_MISSING_PERSON",
    "UIDB_WEAK_DNA_CONCLUSION_RELIED_ALONE": "TRAFFICKING_MISSING_PERSON",
    "CROSS_CASE_IDENTIFIER_LINK": "ORGANIZED_CRIME",
    "INTERSTATE_IDENTIFIER_LINKAGE_ALERT": "ORGANIZED_CRIME",
    "SHARED_INFRASTRUCTURE_LINK": "ORGANIZED_CRIME",
    "SYNDICATE_S111_THRESHOLD_MET": "ORGANIZED_CRIME",
}

# Robbery/Theft Physical evidence (Vahan Samanvay / ZIPNET-modeled).
# "Any two parameters from Registration/Chassis/Engine with partial Nos." is
# NCRB's own published matching rule (Vahan Samanvay FAQ) -- implemented
# here as: identical, or the last N characters identical (a partial-plate/
# partial-chassis match), for at least this many of the three fields.
ROBBERY_VEHICLE_MATCH_MIN_FIELDS = 2
ROBBERY_VEHICLE_PARTIAL_MATCH_SUFFIX_LEN = 4  # [I] design choice -- NCRB's FAQ says "partial" but does not specify a suffix length
# Non-vehicle property (a described item with no hard identifier): treated
# as a candidate match, never a LINK, when description matches and the
# recovered value sits within this fraction of the reported stolen value.
ROBBERY_PROPERTY_VALUE_MATCH_TOLERANCE_FRACTION = 0.20
# Recovered property sitting in the Malkhana with no court-disposal event
# this long after seizure -- a BNSS 497/503 (interim custody/disposal)
# lapse. [I] design default, not an official figure (research flagged this
# threshold as unspecified in primary sources).
ROBBERY_LINGERING_PROPERTY_MAX_DAYS = 90

# Robbery/Theft Digital evidence: NCRB IIF-II Crime Details Form MO-series
# rule. Research spec: ">=4 of 6 fields equal AND within 5 km AND within
# 60 days" -- the 5 km geo-proximity leg is dropped here because this
# system has no geocoded location records to test it against (an honest,
# documented simplification, not a silent omission); the remaining 6-field
# comparison and day window are implemented as specified.
MO_SERIES_FIELDS = ["method_1", "conveyance", "character_assumed", "place_type", "property_type", "time_of_day_band"]
MO_SERIES_MIN_MATCHING_FIELDS = 4
MO_SERIES_MAX_DAYS_APART = 60
# A matched series with this many shared accused across its FIRs clears the
# BNS s.112 (petty organised crime) bar -- notably lower than s.111/MCOCA,
# which needs a charge-sheet-count history (see Organized Crime, not yet
# built).
MO_SERIES_MIN_SHARED_ACCUSED_FOR_S112 = 2

# Assault/Homicide Physical evidence.
# BNSS s.194 (<- CrPC s.174): inquest by police/executive magistrate "in the
# presence of two or more respectable inhabitants" -- the statute's own
# figure, not a design default.
ASSAULT_INQUEST_MIN_WITNESSES = 2
# BNSS s.196 (<- CrPC s.176) requires prompt intimation of a custodial death
# to the magistrate/NHRC/family; the statute says "forthwith"/"immediately"
# without a fixed hour figure, so this is an [I] design default standing in
# for "forthwith", not a statutory number.
ASSAULT_CUSTODIAL_INTIMATION_MAX_HOURS = 24
# BNS s.116 (<- IPC s.320) grievous-hurt classification is defined by injury
# TYPE (fracture, dislocation, an injury endangering life, etc.), not by
# follow-up/hospitalisation duration -- there is no statutory day-count
# threshold. These two figures are [I] design heuristics that flag a
# classification worth a human re-check when it sits far outside what its
# own follow-up-days record would suggest (a "GRIEVOUS" case with almost no
# recorded follow-up, or a "SIMPLE" case with a long one), never a
# reclassification the platform performs itself.
ASSAULT_MLC_GRIEVOUS_MIN_FOLLOWUP_DAYS = 2
ASSAULT_MLC_SIMPLE_MAX_FOLLOWUP_DAYS = 20
# Physical+Digital joint signal: a tower ping within this many hours of the
# inquest's recorded time of death, at a locality name matching the
# inquest's place_of_occurrence, is a spatio-temporal correlation candidate.
# [I] design default -- the research pass's own spec additionally called
# for a 5 km geo-proximity leg, dropped here for the same documented reason
# as the Robbery/Theft MO-series rule: no geocoded coordinates exist in this
# system to test a real distance against, so locality-name matching stands
# in for it, honestly, rather than silently.
ASSAULT_TOWER_SPATIOTEMPORAL_WINDOW_HOURS = 2

# Trafficking/Missing Person Physical evidence: UIDB <-> missing-person
# candidate matching. Tolerances are the research pass's own proposed
# figures ([I], since ZIPNET's live matching logic itself isn't published),
# not statutory numbers.
UIDB_AGE_TOLERANCE_YEARS = 5
UIDB_HEIGHT_TOLERANCE_CM = 5
# Kattavellai's own 48-hour DNA-sample-dispatch direction (see Part C sec.
# C0 of the research pass) -- a real judicial figure, not a design default.
UIDB_DNA_DISPATCH_MAX_HOURS = 48

# Organized Crime. Cross-case identifier reuse and the BNS s.111 (<- MCOCA
# s.2(1)(d)) charge-sheet legal gate.
# "Same MSISDN/IMEI/account/VPA/vehicle reg appears in >=2 FIRs from
# different police stations/states -> link edge; >=3 FIRs -> Samanvaya-
# style interstate linkage alert" -- the research pass's own thresholds.
ORGANIZED_CRIME_CROSS_CASE_LINK_MIN_FIRS = 2
ORGANIZED_CRIME_INTERSTATE_ALERT_MIN_FIRS = 3
# BNS s.111's own statutory text, verbatim: "more than one charge-sheet"
# (i.e. count > 1, so >=2) "within the preceding period of ten years,"
# for an offence "punishable ... for a term of three years or more."
ORGANIZED_CRIME_CHARGE_SHEET_LOOKBACK_YEARS = 10
ORGANIZED_CRIME_MIN_PUNISHMENT_YEARS = 3
ORGANIZED_CRIME_MIN_QUALIFYING_CHARGE_SHEETS = 2

# Missing link recovery
LINK_RECOVERY_MASK_FRACTION = 0.2
LINK_RECOVERY_WEIGHT_STRUCTURAL = 0.6
LINK_RECOVERY_WEIGHT_CROSS_SOURCE = 0.4
LINK_RECOVERY_HIGH_THRESHOLD = 0.66
LINK_RECOVERY_MEDIUM_THRESHOLD = 0.4
