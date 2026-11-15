#!/usr/bin/env python3
"""Bounded FI/SV/EN note constraints, derived only from a public request.

This is a deliberately conservative, deterministic baseline. Unknown grammar,
conflicting statements and unscoped trade-in notes remain explicit unknowns.
It is not an LLM, a trained parser, or a complete implementation of the sponsor
grammar. It never reads reveal labels or changes the official SDK globally.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import re
import unicodedata
from typing import Any

DAY = 1440
VERSION = "bounded-notes-3"


@dataclass
class NoteConstraints:
    readyAt: int | None = None
    releaseAt: int | None = None
    pickupBefore: int | None = None
    pickupHours: dict[str, Any] | None = None
    deliveryHours: dict[str, Any] | None = None
    noteDeadline: int | None = None
    manualRequired: bool | None = None
    platesRequired: bool | None = None
    summerTyres: bool | None = None
    evidence: dict[str, list[str]] = field(default_factory=dict)
    unknown: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    scope: str = "single_leg"
    version: str = VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


NUMBER_WORDS = {
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "one": 13, "two": 14, "three": 15, "four": 16, "five": 17,
    "yhdeksän": 9, "yhdeksältä": 9, "kymmenen": 10, "kymmeneltä": 10,
    "yksitoista": 11, "yhdentoista": 11, "yhdeltätoista": 11,
    "kaksitoista": 12, "kahdentoista": 12, "kahdeltatoista": 12,
    "yksi": 13, "yhden": 13, "yhdeltä": 13, "kaksi": 14, "kahden": 14, "kahdelta": 14,
    "kolme": 15, "kolmen": 15, "kolmelta": 15, "neljä": 16, "neljän": 16, "neljältä": 16, "neljalta": 16,
    "viisi": 17, "viiden": 17, "viideltä": 17,
    "nio": 9, "tio": 10, "elva": 11, "tolv": 12, "ett": 13,
    "två": 14, "tre": 15, "fyra": 16, "fem": 17,
}
WORD_RX = "(?:" + "|".join(sorted(map(re.escape, NUMBER_WORDS), key=len, reverse=True)) + ")"
CLOCK = re.compile(r"(?<![\w\d])(?P<h>\d{1,2})(?:[.:](?P<m>\d{2}))?\s*(?P<ap>a\.?m\.?|p\.?m\.?)?(?![\w\d])")
WORD_CLOCK = re.compile(r"\b(?:(?P<half>half|halv|puoli)\s+)?(?P<word>" + WORD_RX + r")\b")
RANGE = re.compile(r"(?<!\d)(\d{1,2})(?:[.:](\d{2}))?\s*[-–—]\s*(\d{1,2})(?:[.:](\d{2}))?(?!\d)")
FI_RANGE = re.compile(r"(?<!\d)(\d{1,2})(?:[.:](\d{2}))?:(?:stä|sta)\s+(\d{1,2})(?:[.:](\d{2}))?:(?:een|ään|aan)(?!\w)")
CORRECTION = re.compile(r"\b(?:correction|corrected|actually|sorry|rather|instead|korjaus|korjataan|siis|eiku|eikun|oikeasti|rättelse|rättat|istället)\b\s*:?", re.I)
READY = re.compile(r"\b(?:ready|available|valmi\w*|klar\w*|noudettav\w*)\b")
PICKUP = re.compile(r"\b(?:pickup|pick\s*up|collect\w*|collection|nou[dt]\w*|haettav\w*|hakea|hämt\w*|origin|yard|piha\w*|lähtö\w*)\b")
DELIVERY = re.compile(r"\b(?:deliver\w*|destination|arriv\w*|receiv\w*|toimit\w*|perillä|perille|vastaanot\w*|kohde|kohtee\w*|lever\w*|framme|mottag\w*)\b")
PAYMENT = re.compile(r"\b(?:payment|paid|paying|buyer\s+pays?\s+first|maksu\w*|makset\w*|betal\w*)\b")
AFTER = re.compile(r"\b(?:after|from|earliest|not\s+before|jälkeen|alkaen|aikaisintaan|ei\s+ennen|efter|tidigast|inte\s+före|först|framåt)\b")
BEFORE = re.compile(r"\b(?:before|by|latest|until|ennen|mennessä|viimeistään|asti|före|senast|till)\b")
OPEN = re.compile(r"\b(?:open\w*|closed|closes|hours|auki\w*|kiinni|avoinna|öppet|öppna\w*|stäng\w*|arkisin|vardagar|weekdays)\b")
DAILY = re.compile(r"\b(?:daily|every\s+day|weekdays|arkisin|joka\s+päivä|vardagar|varje\s+dag)\b")

DAY_NAMES = [
    (0, r"\b(?:monday|mon|maanantai\w*|måndag\w*|mån)\b|\bma\."),
    (1, r"\b(?:tuesday|tue|tues|tiistai\w*|tisdag\w*|tis)\b|\bti\."),
    (2, r"\b(?:wednesday|wed|keskiviik\w*|onsdag\w*|ons)\b|\bke\."),
    (3, r"\b(?:thursday|thu|thur|thurs|torstai\w*|torsdag\w*|tors)\b|\bto\."),
    (4, r"\b(?:friday|fri|perjantai\w*|fredag\w*|fre)\b|\bpe\."),
    (5, r"\b(?:saturday|sat|lauantai\w*|lördag\w*|lör)\b|\bla\."),
    (6, r"\b(?:sunday|sun|sunnuntai\w*|söndag\w*|sön)\b|\bsu\."),
]
DAY_AFTER = re.compile(r"\b(?:the\s+day\s+after\s+tomorrow|day\s+after\s+tomorrow|ylihuomenna|i\s+övermorgon)\b")
TOMORROW = re.compile(r"\b(?:tomorrow|tmrw|huomenna|i\s+morgon|imorgon)\b")
TODAY = re.compile(r"\b(?:today|tänään|idag|i\s+dag)\b")


def _has_day(text: str) -> bool:
    return bool(DAY_AFTER.search(text) or TOMORROW.search(text) or TODAY.search(text)
                or any(re.search(pattern, text) for _, pattern in DAY_NAMES))


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("’", "'")
    # Observed, unambiguous spelling variants only. This is not a general
    # fuzzy matcher: unfamiliar day or stop words must not pick a time origin.
    for typo, canonical in {"huomnna": "huomenna", "vastaaanottava": "vastaanottava"}.items():
        text = re.sub(r"\b" + typo + r"\b", canonical, text)
    return text


def _minutes(hour: int, minute: int, ampm: str | None = None) -> int | None:
    if minute < 0 or minute > 59:
        return None
    if ampm:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ampm.startswith("p") else 0)
    if not 0 <= hour <= 23:
        return None
    return hour * 60 + minute


def _clock_tokens(text: str) -> list[tuple[int, int, int]]:
    found: list[tuple[int, int, int]] = []
    for match in CLOCK.finditer(text):
        before = text[max(0, match.start() - 16):match.start()]
        after = text[match.end():match.end() + 12]
        # A bare number is a clock only in an explicitly temporal context.
        explicit = match["m"] is not None or match["ap"] is not None
        if not explicit and not re.search(r"(?:\bklo\.?|\bkl\.?|\bat|\bby|\bafter|\bbefore|\buntil|\bfrom|\bennen|\bjälkeen|\basti|\bföre|\befter|\bsenast)\s*$", before) and not re.match(r"\s*(?:mennessä|asti|jälkeen|alkaen|framåt)\b", after):
            continue
        if re.match(r"\s*(?:hours?|minutes?|tunt\w*|min\b|tim\w*)", after):
            continue
        minutes = _minutes(int(match["h"]), int(match["m"] or 0), match["ap"])
        if minutes is not None:
            found.append((match.start(), match.end(), minutes))
    for match in WORD_CLOCK.finditer(text):
        before = text[max(0, match.start() - 20):match.start()]
        if not match["half"] and not match["word"].endswith(("lta", "ltä")) and not re.search(r"(?:\bklo\.?|\bkl\.?|\bat|\bby|\bafter|\bbefore|\buntil|\bfrom|\bennen|\bjälkeen|\basti|\bföre|\befter|\bsenast)\s*$", before):
            continue
        minutes = NUMBER_WORDS[match["word"]] * 60 - (30 if match["half"] else 0)
        found.append((match.start(), match.end(), minutes))
    return sorted(found)


def _negated(text: str, start: int) -> bool:
    before = text[max(0, start - 22):start]
    # "not before" is a valid lower bound, not a denied clock.
    if re.search(r"(?:not\s+before|ei\s+ennen|inte\s+före)\s*(?:klo\.?|kl\.?)?\s*$", before):
        return False
    return bool(re.search(r"\b(?:not|ei|inte|ej)\s*(?:at|klo\.?|kl\.?)?\s*$", before))


def _day(text: str, arrived: int) -> int | None:
    base = arrived // DAY
    matches: list[int] = []
    working = text
    for expression, offset in [(DAY_AFTER, 2), (TOMORROW, 1), (TODAY, 0)]:
        for match in expression.finditer(working):
            if not _negated(working, match.start()):
                matches.append(base + offset)
        working = expression.sub(" ", working)
    for weekday, pattern in DAY_NAMES:
        for match in re.finditer(pattern, working):
            if _negated(working, match.start()):
                continue
            delta = (weekday - base % 7) % 7
            if delta < 2:  # Sponsor grammar names weekdays only 2–6 days away.
                return None
            matches.append(base + delta)
    return (matches[0] if len(set(matches)) == 1 else None) if matches else base


def _corrected_clause(clause: str) -> str:
    markers = list(CORRECTION.finditer(clause))
    if not markers:
        return clause
    marker = markers[-1]
    prefix, replacement = clause[:marker.start()], clause[marker.end():]
    tokens = _clock_tokens(prefix)
    if not tokens or not _clock_tokens(replacement):
        return clause
    # Carry the semantic role/day, but discard the superseded clocks. A new
    # explicit day also supersedes the old day instead of creating two days.
    context = prefix[:tokens[0][0]]
    if DAY_AFTER.search(replacement) or TOMORROW.search(replacement) or TODAY.search(replacement) or any(re.search(p, replacement) for _, p in DAY_NAMES):
        context = DAY_AFTER.sub(" ", context)
        context = TOMORROW.sub(" ", context)
        context = TODAY.sub(" ", context)
        for _, pattern in DAY_NAMES:
            context = re.sub(pattern, " ", context)
    return context + " " + replacement


def parse_notes(request: dict[str, Any]) -> NoteConstraints:
    """Parse only facts supported by bounded grammar; absent is not false."""
    result = NoteConstraints()
    note = request.get("note")
    if not note or not isinstance(note.get("text"), str) or not note["text"].strip():
        result.unknown.append("no_note")
        return result
    if len(request.get("legs", [])) != 1:
        result.scope = "unscoped_multi_leg"
        result.unknown.append("multi_leg_note_requires_explicit_leg_scope")
        return result
    arrived = request.get("arrivedAt")
    if not isinstance(arrived, int) or isinstance(arrived, bool) or arrived < 0:
        result.unknown.append("missing_or_invalid_arrivedAt")
        return result
    text = _normalize(note["text"])
    # Strip conventional clock abbreviation dots before sentence splitting.
    text = re.sub(r"\b(klo|kl)\.", r"\1", text)
    text = re.sub(r"\b([ap])\.m\.", r"\1m", text)
    text = re.sub(r"\bviim\.(?=\s)", "viimeistään", text)
    abbreviations = {"ma": "maanantai", "ti": "tiistai", "ke": "keskiviikko", "to": "torstai", "pe": "perjantai", "la": "lauantai", "su": "sunnuntai"}
    text = re.sub(r"\b(ma|ti|ke|to|pe|la|su)\.(?=\s+(?:klo\b|kl\b|\d))",
                  lambda match: abbreviations[match[1]], text)
    # Dotless FI day abbreviations are scoped by a clock marker. Bare English
    # "to" is not a Thursday; do not add it to the global weekday regex.
    text = re.sub(r"\b(ma|ti|ke|to|pe|la|su)(?=\s+(?:klo|kl)\b)",
                  lambda match: abbreviations[match[1]], text)
    # Only a dot *between* two digits is part of a clock. A period after
    # 16.30 still ends its sentence; otherwise the next stop contaminates it.
    clauses = [part.strip() for part in re.split(r"[;\n!?]+|(?<!\d)\.|\.(?!\d)", text) if part.strip()]
    assertions: dict[str, list[Any]] = {}

    def assert_value(name: str, value: Any, evidence: str) -> None:
        assertions.setdefault(name, []).append(value)
        result.evidence.setdefault(name, []).append(evidence)

    def temporal_assertion_count() -> int:
        return sum(len(assertions.get(name, [])) for name in
                   ("readyAt", "releaseAt", "pickupBefore", "pickupHours", "deliveryHours", "noteDeadline"))

    for original in clauses:
        # A contact reminder does not make preceding yard hours delivery
        # hours merely because it mentions arrival at the end of the clause.
        contact_parts = re.split(r",\s*(?:soita|call|ring|ilmoita)\b", original, maxsplit=1)
        clause = contact_parts[0]
        if len(contact_parts) > 1 and (_clock_tokens(contact_parts[1]) or _has_day(contact_parts[1])
                                       or RANGE.search(contact_parts[1]) or FI_RANGE.search(contact_parts[1])):
            result.unknown.append("unparsed_contact_timing: " + original)
        if re.match(r"^(?:soita|call|ring|ilmoita)\b", clause):
            result.unknown.append("contact_instruction: " + original)
            continue
        clause = _corrected_clause(clause)
        if re.search(r"\b(?:maybe|perhaps|probably|possibly|may|might|could|ehkä|ehka|mahdollisesti|kanske|möjligen|eventuellt)\b", clause):
            result.unknown.append("uncertain_statement: " + original)
            continue
        if re.search(r"\b(?:if|unless|jos|mikäli|om)\b", clause):
            result.unknown.append("conditional_statement: " + original)
            continue
        seen = False
        # Negations of requirements are distinct from "no plates", which
        # positively means transfer plates are needed.
        manual = re.search(r"\b(?:manual\w*|manuaal\w*|manuell\w*|käsivaih\w*)\b", clause)
        automatic = re.search(r"\b(?:automatic\w*|automaatt\w*|automat\w*)\b", clause)
        if manual and not automatic:
            assert_value("manualRequired", not _negated(clause, manual.start()), original)
            seen = True
        elif automatic and not manual and not _negated(clause, automatic.start()):
            assert_value("manualRequired", False, original)
            seen = True
        elif manual and automatic:
            result.ambiguous.append("manual_and_automatic_in_same_clause")
            seen = True
        no_plates = re.search(r"\b(?:no\s+(?:number\s+)?plates|without\s+(?:number\s+)?plates|(?:ei|ilman)\s+(?:kilp\w*|rekkar\w*)|(?:rekisteri)?kilvet\s+(?:puuttu\w*|poistettu|irrotettu)|utan\s+skylt\w*|skylt\w*\s+sakna\w*|needs?\s+(?:(?:transfer|trade)\s+)?plates|(?:siirto|koe)kil\w*\s+(?:tarvi\w*|mukaan)|ota\s+koekil\w*)\b", clause)
        has_plates = re.search(r"\b(?:has\s+(?:number\s+)?plates|plates\s+(?:are\s+)?present|kilvet\s+(?:on|löyty\w*)|skyltar\s+finns|(?:no|does\s+not|do\s+not)\s+(?:need\s+)?(?:transfer|trade)\s+plates\s*(?:needed)?|(?:transfer|trade)\s+plates\s+(?:are\s+)?not\s+(?:needed|required)|(?:siirto|koe)kil\w*\s+ei\s+tarvi\w*)\b", clause)
        if no_plates and _negated(clause, no_plates.start()):
            # "Does not need trade plates" negates the requirement. The
            # separate absent-plates phrases still positively require them.
            no_plates = None
        if bool(no_plates) != bool(has_plates):
            assert_value("platesRequired", bool(no_plates), original)
            seen = True
        elif no_plates and has_plates:
            result.ambiguous.append("conflicting_plate_requirement")
            seen = True
        summer = re.search(r"\b(?:summer\s+t[yi]res|kesären\w*|sommardäck\w*)\b", clause)
        winter = re.search(r"\b(?:winter\s+t[yi]res|talviren\w*|vinterdäck\w*)\b", clause)
        tyre_cargo = re.search(r"\b(?:boot|trunk|spare|extra|takakont\w*|tavar\w*|ylimääräi\w*|bagag\w*|bakl?uck\w*)\b", clause)
        if (summer or winter) and tyre_cargo:
            result.unknown.append("tyres_may_be_cargo: " + original)
            seen = True
        elif summer and not winter:
            assert_value("summerTyres", not _negated(clause, summer.start()), original)
            seen = True
        elif winter and not summer and not _negated(clause, winter.start()):
            assert_value("summerTyres", False, original)
            seen = True
        elif summer and winter:
            result.ambiguous.append("conflicting_tyre_requirement")
            seen = True

        ready_match = READY.search(clause)
        pickup, delivery, ready, payment = bool(PICKUP.search(clause)), bool(DELIVERY.search(clause)), bool(ready_match), bool(PAYMENT.search(clause))
        ranges = list(RANGE.finditer(clause)) + list(FI_RANGE.finditer(clause))
        temporal = FI_RANGE.sub(" ", RANGE.sub(" ", clause))
        before_ranges = temporal_assertion_count()
        if ranges and (OPEN.search(clause) or pickup or delivery):
            if _has_day(clause):
                # A date-specific opening interval must not become a global
                # weekday schedule. That needs a richer timeline than Hours.
                result.unknown.append("date_specific_hours_not_representable: " + original)
                seen = True
            elif len(ranges) == 1 and not (pickup and delivery):
                match = ranges[0]
                opens = _minutes(int(match[1]), int(match[2] or 0))
                closes = _minutes(int(match[3]), int(match[4] or 0))
                if opens is not None and closes is not None and opens < closes:
                    hours: dict[str, Any] = {"opens": opens, "closes": closes}
                    if re.search(r"\b(?:weekdays|arkisin|vardagar)\b", clause):
                        hours["weekdays"] = [0, 1, 2, 3, 4]
                    # The sponsor's observed generic "aukioloajat" statements
                    # describe pickup hours. Explicit delivery words override.
                    assert_value("deliveryHours" if delivery else "pickupHours", hours, original)
                    seen = True
            else:
                result.ambiguous.append("multiple_hours_or_stop_roles")
                seen = True
        ranges_consumed = temporal_assertion_count() > before_ranges
        before_clocks = temporal_assertion_count()
        clocks = [token for token in _clock_tokens(temporal) if not _negated(temporal, token[0])]
        day = _day(temporal, arrived)
        negated_ready_lower_bound = re.search(r"\b(?:not\s+ready\s+(?:before|until)|ei\s+(?:ole\s+)?valmi\w*\s+ennen|inte\s+klar\w*\s+före)\b", temporal)
        denied_readiness = ready_match and _negated(clause, ready_match.start()) and not negated_ready_lower_bound
        if denied_readiness:
            result.unknown.append("negated_readiness_without_lower_bound: " + original)
            seen = True
        elif not clocks and ready and not delivery and re.search(r"\b(?:immediately|right\s+now|heti|genast)\b", temporal):
            assert_value("readyAt", arrived, original)
            seen = True
        elif clocks and day is None:
            result.ambiguous.append("conflicting_or_unsupported_day")
            seen = True
        elif len(clocks) > 1:
            result.ambiguous.append("multiple_clocks_without_supported_correction")
            seen = True
        elif len(clocks) == 1 and day is not None:
            minute = clocks[0][2]
            after, before = bool(AFTER.search(temporal)), bool(BEFORE.search(temporal))
            timestamp = day * DAY + minute
            if pickup and delivery:
                result.ambiguous.append("multiple_stop_roles")
                seen = True
            elif payment and (after or ready):
                assert_value("releaseAt", timestamp, original)
                seen = True
            elif ready and not delivery:
                assert_value("readyAt", timestamp, original)
                seen = True
            elif delivery and before and not after:
                if OPEN.search(temporal) or re.search(r"\b(?:receiv\w*|vastaanot\w*|mottag\w*)\b", temporal):
                    if _has_day(temporal):
                        result.unknown.append("date_specific_hours_not_representable: " + original)
                    else:
                        assert_value("deliveryHours", {"closes": minute}, original)
                else:
                    assert_value("noteDeadline", timestamp, original)
                seen = True
            elif pickup and before and not after:
                has_explicit_day = _has_day(temporal)
                if has_explicit_day and (OPEN.search(temporal) or DAILY.search(temporal)):
                    result.unknown.append("date_specific_hours_not_representable: " + original)
                elif not has_explicit_day:
                    hours = {"closes": minute}
                    if re.search(r"\b(?:weekdays|arkisin|vardagar)\b", temporal):
                        hours["weekdays"] = [0, 1, 2, 3, 4]
                    assert_value("pickupHours", hours, original)
                else:
                    assert_value("pickupBefore", timestamp, original)
                seen = True
            elif pickup and after and not delivery:
                assert_value("readyAt", timestamp, original)
                seen = True
        clocks_consumed = temporal_assertion_count() > before_clocks
        invalid_clock = any((match["m"] is not None or match["ap"] is not None)
                            and _minutes(int(match["h"]), int(match["m"] or 0), match["ap"]) is None
                            for match in CLOCK.finditer(temporal))
        temporal_cue = (_has_day(temporal) or READY.search(temporal) or PAYMENT.search(temporal)
                        or OPEN.search(temporal) or AFTER.search(temporal) or BEFORE.search(temporal)
                        or re.search(r"\b(?:klo|kl|at)\b", temporal))
        # Recognizing a requirement does not consume another fact in its
        # clause. In particular, an unscoped "not before 16:00" must remain
        # unknown, so callers cannot clear the source note and lose its bound.
        # Track ranges and clocks separately: parsed hours cannot hide a
        # second unresolved clock, or vice versa. No generic clock is guessed
        # to mean readiness solely to make the clause appear complete.
        if ((ranges and not ranges_consumed) or (clocks and not clocks_consumed)
                or invalid_clock
                or (not ranges and not clocks and temporal_cue and not clocks_consumed)):
            result.unknown.append("unparsed_temporal_constraint: " + original)
            seen = True
        if not seen:
            result.unknown.append(original)
    for name, values in assertions.items():
        unique = []
        for value in values:
            if value not in unique:
                unique.append(value)
        if len(unique) == 1:
            setattr(result, name, unique[0])
        else:
            result.ambiguous.append("conflicting_" + name)
    return result


def note_adjusted_request(request: dict[str, Any], constraints: NoteConstraints | None = None) -> dict[str, Any]:
    """Return a copy with supported public constraints; never use truth labels.

    Requirements remain on the constraints object for a caller's post/audience
    decisions. The caller must explicitly opt in; no shared default is changed.
    A contradictory time window raises rather than widening the original one.
    """
    constraints = constraints or parse_notes(request)
    adjusted = deepcopy(request)
    if constraints.scope != "single_leg" or len(adjusted.get("legs", [])) != 1:
        return adjusted
    leg = adjusted["legs"][0]
    pickup = leg["pickup"]
    for timestamp in [constraints.readyAt, constraints.releaseAt]:
        if timestamp is not None:
            pickup["window"]["from"] = max(pickup["window"]["from"], timestamp)
    if constraints.pickupBefore is not None:
        pickup["window"]["to"] = min(pickup["window"]["to"], constraints.pickupBefore)
    for stop, hours in [("pickup", constraints.pickupHours), ("delivery", constraints.deliveryHours)]:
        place = leg[stop]
        if hours is not None and not place.get("privateAddress") and place.get("hours") is not None:
            combined = {**place["hours"], **hours}
            if combined["opens"] >= combined["closes"]:
                raise ValueError("Note hours conflict with public hours")
            place["hours"] = combined
    if pickup["window"]["from"] > pickup["window"]["to"]:
        raise ValueError("Note readiness conflicts with pickup window")
    if constraints.noteDeadline is not None:
        for option in adjusted["options"]:
            option["deadline"] = min(option["deadline"], constraints.noteDeadline)
    return adjusted
