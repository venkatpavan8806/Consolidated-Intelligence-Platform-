"""
Curated gazetteer backstop for entity extraction.

A general-purpose small NER model is weak on Indian place names outside its
training distribution (it may drop them entirely or mis-tag them as PERSON) --
verified during development of this system. This gazetteer is not meant to be
exhaustive; it only needs to cover the place names this project's case data
actually uses, plus the police-station names that must NOT be treated as
investigatively meaningful "repeat locations" (a station recurring because it
filed many unrelated cases is expected, not a signal).
"""

PLACES = [
    "Sonepur Junction",
    "Sonepur",
    "MG Road",
    "Whitefield",
    "Andheri",
]

# Station names are recognized as ORGANIZATION (case-handling entity), never as
# a LOCATION for the repeat-location signal -- their recurrence is expected.
POLICE_STATIONS = [
    "Sonepur Police Station",
    "MG Road Police Station",
    "Cyber Crime Cell",
]


def match_gazetteer(text: str):
    """Return list of (start, end, matched_text, entity_type) for gazetteer hits.
    Longer entries are matched first so e.g. 'Sonepur Police Station' does not
    also get partially matched as the place 'Sonepur'.
    """
    hits = []
    claimed = [False] * len(text)

    def try_match(terms, entity_type):
        for term in sorted(terms, key=len, reverse=True):
            start = 0
            while True:
                idx = text.find(term, start)
                if idx == -1:
                    break
                end = idx + len(term)
                if not any(claimed[idx:end]):
                    hits.append((idx, end, term, entity_type))
                    for i in range(idx, end):
                        claimed[i] = True
                start = idx + 1

    try_match(POLICE_STATIONS, "ORGANIZATION")
    try_match(PLACES, "LOCATION")
    return hits
