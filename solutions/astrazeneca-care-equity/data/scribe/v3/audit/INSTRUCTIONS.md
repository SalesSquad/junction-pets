# Auditor instructions: SAMA pathway scribe, teaching round 2

Everything here is SYNTHETIC: invented Finnish clinical-style notes written by a language model from sampled
answer keys. No real patients. Nothing is for clinical use.

You are one of eight independent auditors. You check whether the claimed answer of each note is really what
the note says. Judge from the note alone.

## 1. Files

**Input.** `data/scribe/v3/audit/slice-XX.json` (XX = `01` .. `08`; you are given one). A JSON array of
30 items:

```json
{"audit_id": "a1b2c3d4e5f6",
 "note_date": "2026-04-30",
 "note_text": "<the note, Finnish, one string>",
 "claimed": {"entry_route": "EMERGENCY",
             "events": [{"index": 0, "type": "PHYSICIAN_ASSESSMENT", "date": "2025-09-30", "precision": "DAY"},
                        {"index": 1, "type": "REFERRAL_SENT", "date": "2025-11-01", "precision": "MONTH"}]}}
```

`claimed.events` may be empty: the claim is then that the note states no dated cancer-pathway event at all.

**Do not open any other file** under `data/scribe/v3/` or `scribe/` (in particular not `key.json`, the
candidates, the judges' output or another auditor's output). Do not use a model or a tool to pre-label
the notes. Your verdicts must be your own reading of the note.

**Output.** `data/scribe/v3/audit/out/slice-XX.json` (create the `out` directory if needed; write no other
file and change no existing file). One JSON array with one object per item, in the order of the input, and
`audit_id` on every item:

```json
[
  {"audit_id": "a1b2c3d4e5f6",
   "events": [
     {"index": 0, "verdict": "stated", "quote": "Päivystävä lääkäri tutki ja arvioi potilasta 212 päivää sitten"},
     {"index": 1, "verdict": "wrong_type", "quote": "lähete saapui erikoissairaanhoitoon marraskuussa 2025"}
   ],
   "unlisted_event": {"present": false, "quote": ""},
   "route_ok": true}
]
```

UTF-8, valid JSON, nothing before `[` or after `]`. `events` has exactly one entry per claimed event, with
the same `index`. An optional `"comment"` string per item is allowed and is not scored.

## 2. Dates

Resolve every date expression against `note_date`:

| in the note | means |
| --- | --- |
| `3.2.2025`, `3. helmikuuta 2025` | 2025-02-03 |
| `3.2.` (no year) | that day and month in the year of `note_date` |
| `12 päivää sitten` | `note_date` minus 12 days |
| `8 viikkoa sitten` | `note_date` minus 56 days (8 x 7) |
| `helmikuussa 2025` | the calendar month 2025-02 |

A claimed event with `"precision": "MONTH"` and `"date": "2025-02-01"` claims **the month** February 2025,
not the first day of it; it is right when the note gives that month for that event. A claimed event with
`"precision": "DAY"` is right only when the note's expression resolves to exactly that day. Do the
arithmetic carefully (month lengths, leap years); a date that is off by one day is `wrong_date`.

## 3. The nine event types

Codes and their Finnish names:

| code | Finnish name |
| --- | --- |
| `SYMPTOM_ONSET_REPORTED` | `oireiden alku` |
| `FIRST_CONTACT` | `ensimmäinen yhteydenotto terveydenhuoltoon` |
| `PHYSICIAN_ASSESSMENT` | `lääkärin arvio` |
| `REFERRAL_SENT` | `lähetteen lähettäminen` |
| `REFERRAL_RECEIVED` | `lähetteen vastaanottaminen` |
| `SPECIALIST_VISIT` | `erikoislääkärikäynti` |
| `DIAGNOSIS` | `syöpädiagnoosin vahvistaminen` |
| `MDT_DECISION` | `moniammatillinen hoitopäätös` |
| `TREATMENT_START` | `syöpähoidon aloitus` |

The definitions, copied from `data/scribe/v2/WRITER_INSTRUCTIONS.md` (section 3.5; written for the writers of
version 2, so "the note must make clear that" is the definition, and the "never" column lists wordings that do
NOT establish the event):

| line begins | the note must make clear that | some ways to say it (vary them, invent your own) | never |
| --- | --- | --- | --- |
| `oireiden alku` | the patient reports when the symptoms that led to the suspicion began | `pot. kertoo oireiden alkaneen ...`, `oireilu alkanut anam. mukaan ...`, `ensimmäiset oireet pot. huomasi ...`, `vaivat alkoivat oman kertoman mukaan ...` | a finding at an examination presented as the onset |
| `ensimmäinen yhteydenotto terveydenhuoltoon` | the patient got in touch for the first time and was answered by a nurse or the booking service, not examined by a physician | `otti ensimmäisen kerran yhteyttä työterveyshoitajaan ...`, `soitti ensi kertaa ajanvaraukseen ...`, `ensikontakti sh:n puhelinajalle ...`, `hakeutui ensimmäisen kerran hoitajan vastaanotolle ...` | `kävi lääkärissä`, a bare `käynti` or `kontakti` |
| `lääkärin arvio` | the physician of the entry service examined and assessed the patient | `työterveyslääkäri tutki pot:n ...`, `tk-lääkärin vo:lla arvioitu ...`, `päivystävä lääkäri arvioi tilanteen ...`, `yleislääkäri tutki ja totesi jatkoselvittelyn tarpeen ...` | `erikoislääkäri`, a bare `vastaanotto`, a nurse |
| `lähetteen lähettäminen` | the referring physician wrote the referral and **sent** it to specialised care | `lähete esh:oon lähetettiin ...`, `lähetin lähetteen ...`, `lähete lähti ...`, `lähete laadittu ja toimitettu kirurgian pkl:lle ...` | `pot. sai lähetteen`, `lähete tehty`, `lähete saapui` |
| `lähetteen vastaanottaminen` | the referral **arrived** at the specialised-care unit and was registered there | `lähete saapui pkl:lle ...`, `lähete kirjattu vastaanotetuksi ...`, `lähete tullut yksikköömme ...`, `lähete vastaanotettu syöpätautien pkl:lla ...` | `pot. sai lähetteen`, `lähete lähetetty` |
| `erikoislääkärikäynti` | the patient attended the appointment of the treating specialist in specialised care | `kävi onkologin vastaanotolla ...`, `urologian pkl:lla erikoislääkärin vo ...`, `kirurgin vastaanotto esh:ssa ...`, `keuhkolääkäri tapasi pot:n pkl:lla ...` | a bare `käynti`, `lääkärin arvio` |
| `syöpädiagnoosin vahvistaminen` | the cancer diagnosis was confirmed | `syöpädiagnoosi varmistui ...`, `dg varmistui PAD-vastauksesta ...`, `histologinen varmistus saatiin ...`, `diagnoosi vahvistettiin ...` | `epäily`, `alustava` |
| `moniammatillinen hoitopäätös` | the multidisciplinary meeting decided on treatment | `moniammatillinen kokous teki hoitopäätöksen ...`, `hoitolinjasta päätettiin moniammatillisessa kokouksessa ...`, `moniammatillinen työryhmä linjasi hoidon ...` | `hoitoa suunnitellaan` |
| `syöpähoidon aloitus` | the first cancer treatment started | `sytostaattihoito aloitettiin ...`, `sädehoito alkoi ...`, `hormonihoito käynnistettiin ...`, `ensimmäinen hoitojakso alkoi ...` | `hoito on tarkoitus aloittaa` |

Dated items that are not pathway events (same source, section 3.6):

State them as what they are, so that nobody could take them for a pathway step:

- `syntymäaika`: `s. 20.7.1961`, `syntynyt 20.7.1961`.
- `aiempi syöpään liittymätön rokotuskäynti`: an earlier vaccination, clearly unrelated to the
  present matter. Do not say where it was given (that would name a second service).
- `tuleva, vielä toteutumaton ...`: an appointment that has not taken place. Use the future or
  `on varattu`, `on tulossa`. Never write it as something that happened.
- In a `no_event` note every dated line is ordinary care.

The moment of writing (`note_date`) is not an event. A plan, a booked or future appointment, a negation or a
hedge (`ilmeisesti`, `noin`) does not state an event.

## 4. Verdict per claimed event

Give exactly one verdict for every claimed event:

| verdict | when | quote |
| --- | --- | --- |
| `stated` | the note states that an event of this type happened on this date (this month for `MONTH`) | the passage that states it, including the date expression |
| `wrong_date` | the note states an event of this type, but its date resolves to another day (or another month) | the passage with the date expression the note really gives |
| `wrong_type` | the note has this date, but what happened then is another kind of event or not a pathway event (referral arrived instead of sent, a nurse instead of a physician, a plan instead of a completed act, ...) | the passage that shows what the note really says at that date |
| `not_stated` | the note states no such event: neither this type at another date nor this date with another event | empty string |
| `ambiguous` | a careful reader cannot decide between `stated` and one of the others (the verb does not show sent or received, it is unclear who assessed, the date could belong to two events, ...) | the passage that is unclear |

Use `ambiguous` only for a real doubt about the note, not to avoid the date arithmetic.

**The quote** is an exact substring of `note_text`: copied character for character, including punctuation,
capital letters and spaces, with no ellipsis, no added quotation marks and nothing left out in the middle.
Keep it short (one clause or sentence, at most about 200 characters) and make sure it contains the evidence.
A verdict whose quote is not an exact substring of the note is discarded by the scorer, and so is a
`stated`, `wrong_date`, `wrong_type` or `ambiguous` verdict with an empty quote. If you can run code, check
`quote in note_text` for every quote before saving.

## 5. `unlisted_event`

`{"present": true, "quote": "..."}` when the note states a completed, dated cancer-pathway event (one of the
nine types) that is **not** in the claimed list: its type or its resolved date differs from every claimed
entry. The quote is an exact substring that shows the event and its date. Otherwise
`{"present": false, "quote": ""}`.

Do not count: birth dates, vaccinations and other care unrelated to cancer, future or booked appointments,
pathway steps mentioned without any date, and the event you already marked `wrong_date` or `wrong_type`
(that one is the same statement of the note, counted once).

## 6. `route_ok`

| code | Finnish name |
| --- | --- |
| `PUBLIC_PRIMARY` | `julkinen perusterveydenhuolto` |
| `OCCUPATIONAL` | `työterveyshuolto` |
| `PRIVATE` | `yksityinen terveydenhuolto` |
| `EMERGENCY` | `päivystys` |
| `SCREENING` | `seulonta` |

From `data/scribe/v2/WRITER_INSTRUCTIONS.md` (section 3.4): Finnish names of the five services: `julkinen perusterveydenhuolto` (terveyskeskus, terveysasema,
tk), `työterveyshuolto` (työterveys, työterveysasema), `yksityinen terveydenhuolto` (yksityinen
lääkäriasema), `päivystys` (päivystyspoliklinikka, yhteispäivystys, päivystysapu) and `seulonta`
(seulontayksikkö, seulontatutkimus).

`route_ok` is `true` when the note says that the patient came onto the cancer pathway through the claimed
service. For an item with an empty event list it is `true` when the contact described in the note takes
place in the claimed service. Otherwise `false`.

## 7. Before saving

- 30 objects, each with the `audit_id` of its item, in input order.
- One verdict per claimed event, each one of: `stated`, `wrong_date`, `wrong_type`, `not_stated`, `ambiguous`.
- Every non-empty quote is an exact substring of its note.
- You judged the note, not the plausibility of the claim: a claim can be perfectly plausible and still not be
  what the note says.

The sample holds 240 notes in eight slices; which notes a gate accepted is not shown to you.
