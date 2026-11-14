"""Finnish relative-date lexicon for resolver arm A' (scribe/v3/resolve.py). Standard library only.

Written from general Finnish usage, not from any note set: no validation, test or stress note was read to write it.
Frozen with resolve.py (sha256 in data/scribe/v4/resolver/freeze.json) before anything else uses it.
Held out on purpose (they belong to the stress set of NVIDIA_OPTIONS.md step 3): number words for seven to twelve
and the adverb for "the day before yesterday". A phrase this file cannot place on one exact day goes to a person.
"""

VERSION = "fi-relative-lexicon-v1"
NUMBER_WORDS = {"yksi": 1, "kaksi": 2, "kolme": 3, "neljä": 4, "viisi": 5, "kuusi": 6}  # nominative, as in "kolme viikkoa sitten"
UNIT_DAYS = {"päivää": 1, "viikkoa": 7}  # partitive after a number: "kaksi päivää sitten", "kuusi viikkoa sitten"
SINGULAR_UNIT_DAYS = {"päivä": 1, "viikko": 7}  # nominative singular, alone or after "yksi": "viikko sitten" = 7 days
AGO = "sitten"
ADVERB_DAYS = {"eilen": 1}  # yesterday = 1 day before the note date
# No single exact day: these go to a person, never to a date.
TO_PERSON_UNITS = ("kuukausi", "kuukautta", "vuosi", "vuotta")  # "kuukausi sitten", "2 kuukautta sitten", "puoli vuotta sitten"
VAGUE_QUANTIFIERS = ("muutama", "pari", "useampi", "useita", "monta", "joitakin")  # "pari viikkoa sitten", "muutama päivä sitten"
TO_PERSON_PHRASES = ("viime viikolla", "viime kuussa", "viime vuonna")  # last week / month / year
