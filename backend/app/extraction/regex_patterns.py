import re

PHONE_RE = re.compile(r"\b\d{10,11}\b")
ACCOUNT_RE = re.compile(r"\b\d{12}\b")
VEHICLE_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}\b")

# Rank/honorific prefixes stripped from a captured name before it is treated
# as the person's canonical display name (the rank itself is what marks the
# mention OFFICIAL, not a keyword match against the person's own name --
# see gotcha #3: never infer "official" from a substring of the NAME field).
RANK_PREFIXES = ["Inspector", "Sub-Inspector", "SI", "SHO", "ASI", "DySP", "Constable", "SP", "DIG", "IG"]

# Role keyword -> canonical fir_role. Longer/more specific phrases first so
# "Investigating Officer" is not shadowed by a shorter partial keyword.
ROLE_KEYWORDS = [
    ("Investigating Officer", "OFFICIAL"),
    ("Inspector", "OFFICIAL"),
    ("Accused", "ACCUSED"),
    ("Witness", "WITNESS"),
    ("Complainant", "COMPLAINANT"),
    ("Victim", "VICTIM"),
]

NAME_TOKEN_RE = r"[A-Z][a-zA-Z\.]*"
_ROLE_NAME_PATTERNS = [
    (re.compile(rf"\b{re.escape(kw)}\s+((?:{NAME_TOKEN_RE}\s+){{0,3}}{NAME_TOKEN_RE})"), role)
    for kw, role in ROLE_KEYWORDS
]


def extract_role_labeled_names(text: str):
    """Rule-based backstop for role-labeled names in FIR-style sentences.

    A general-purpose small NER model genuinely misses or truncates names in
    short FIR sentences (verified during development: it dropped a full name
    entirely in one sentence and truncated another to a single token). This
    keys off the role word instead of trusting NER, per the documented gotcha.
    """
    results = []
    claimed = [False] * len(text)
    for pattern, role in _ROLE_NAME_PATTERNS:
        for m in pattern.finditer(text):
            name_start, name_end = m.start(1), m.end(1)
            if any(claimed[name_start:name_end]):
                continue
            raw_name = m.group(1).strip()
            tokens = raw_name.split()
            while tokens and tokens[0].rstrip(".") in RANK_PREFIXES:
                tokens = tokens[1:]
            clean_name = " ".join(tokens).strip()
            if not clean_name:
                continue
            for i in range(name_start, name_end):
                claimed[i] = True
            results.append({
                "start": name_start,
                "end": name_end,
                "text": clean_name,
                "raw_text": raw_name,
                "fir_role": role,
            })
    return results


def extract_structured_identifiers(text: str):
    results = []
    for m in ACCOUNT_RE.finditer(text):
        results.append({"start": m.start(), "end": m.end(), "text": m.group(), "entity_type": "ACCOUNT"})
    account_spans = [(r["start"], r["end"]) for r in results]

    def overlaps(a, spans):
        return any(a[0] < e and a[1] > s for s, e in spans)

    for m in PHONE_RE.finditer(text):
        span = (m.start(), m.end())
        if overlaps(span, account_spans):
            continue
        results.append({"start": m.start(), "end": m.end(), "text": m.group(), "entity_type": "PHONE"})
    for m in VEHICLE_RE.finditer(text):
        results.append({"start": m.start(), "end": m.end(), "text": m.group(), "entity_type": "VEHICLE"})
    return results
