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

# Missing link recovery
LINK_RECOVERY_MASK_FRACTION = 0.2
LINK_RECOVERY_WEIGHT_STRUCTURAL = 0.6
LINK_RECOVERY_WEIGHT_CROSS_SOURCE = 0.4
LINK_RECOVERY_HIGH_THRESHOLD = 0.66
LINK_RECOVERY_MEDIUM_THRESHOLD = 0.4
