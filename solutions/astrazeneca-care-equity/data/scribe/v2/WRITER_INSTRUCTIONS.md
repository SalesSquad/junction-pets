# Writer instructions: SAMA pathway scribe v2

You write short Finnish clinical-style notes from specifications. A small model is later trained
to read such a note and list the dated cancer-pathway events in it. The correct answer for every
note is already fixed in its specification, so a note is only usable if it says exactly what its
specification says: nothing missing, nothing added, every date string intact.

Everything here is invented. The notes are training text for a research model and are not for
clinical use.

## 1. Files

**Input.** `data/scribe/v2/slices/slice-XX.json` (XX = `01` .. `12`; you are given one). It is a
JSON array of 100 specifications. Each specification starts on a line that begins with
`{"slice":` and spans several short lines; every string of `facts_fi` and `wording` is on a line
of its own. Work through the file one `part` at a time (25 specifications). A whole slice is too
long to read in one go, so read it by line range:

<!-- part-lines:start -->
| slice | part 1 | part 2 | part 3 | part 4 | lines in file |
| --- | --- | --- | --- | --- | --- |
| `slice-01.json` | 2-225 | 226-443 | 444-687 | 688-918 | 919 |
| `slice-02.json` | 2-226 | 227-466 | 467-697 | 698-921 | 922 |
| `slice-03.json` | 2-223 | 224-449 | 450-677 | 678-912 | 913 |
| `slice-04.json` | 2-229 | 230-452 | 453-673 | 674-907 | 908 |
| `slice-05.json` | 2-240 | 241-483 | 484-708 | 709-929 | 930 |
| `slice-06.json` | 2-241 | 242-464 | 465-695 | 696-917 | 918 |
| `slice-07.json` | 2-225 | 226-450 | 451-690 | 691-929 | 930 |
| `slice-08.json` | 2-225 | 226-455 | 456-684 | 685-919 | 920 |
| `slice-09.json` | 2-217 | 218-443 | 444-678 | 679-903 | 904 |
| `slice-10.json` | 2-239 | 240-478 | 479-731 | 732-958 | 959 |
| `slice-11.json` | 2-233 | 234-466 | 467-685 | 686-910 | 911 |
| `slice-12.json` | 2-235 | 236-477 | 478-692 | 693-923 | 924 |
<!-- part-lines:end -->

Read the lines of part 1, write its 25 notes, save the file, then go on to part 2.

**Output.** For slice XX write four files:

```
data/scribe/v2/haiku-raw/slice-XX-part1.json   specifications n = 1 .. 25    (part 1)
data/scribe/v2/haiku-raw/slice-XX-part2.json   specifications n = 26 .. 50   (part 2)
data/scribe/v2/haiku-raw/slice-XX-part3.json   specifications n = 51 .. 75   (part 3)
data/scribe/v2/haiku-raw/slice-XX-part4.json   specifications n = 76 .. 100  (part 4)
```

Each file is one JSON array of at most 25 objects, in the order of `n`, and each object has
exactly two keys:

```json
[
  {"id": "<the id of the specification, copied character for character>", "note_text": "<the note>"},
  {"id": "...", "note_text": "..."}
]
```

- UTF-8, valid JSON, nothing before `[` or after `]`: no Markdown fence, no comment, no trailing comma.
- `note_text` is one string without line breaks. Do not use double quotes inside a note.
- Real ids are 64 hexadecimal characters. Never invent or change an id.
- If you cannot write a note that follows every rule for some specification, leave that id out.
  A missing note costs nothing; a note that breaks a rule is worse than none.
- Create the `haiku-raw` directory if it does not exist. Write no other file and change no
  existing file.

## 2. What is in a specification

Read these fields:

| field | meaning |
| --- | --- |
| `id` | copy into the output |
| `n`, `part` | position in the slice (1..100) and output file (1..4) |
| `kind` | `standard`, `careful` or `no_event` (section 5) |
| `style` | the kind of note to write (section 6) |
| `note_date` | the day the note is written. Never printed in the note (rule 3.3) |
| `facts_fi` | everything the note must state, one fact per line |
| `date_strings` | the exact date strings that must appear, each once |
| `wording` | extra binding instructions for this note (empty for `standard`) |

The remaining fields (`facts`, `distractors`, `ground_truth`, `focus`, `date_forms`,
`distractor_forms`, `split_hint`, `sampler`, `synthetic`, `slice`) are the answer key and
bookkeeping. Use them to understand the specification. Never copy their English codes
(`REFERRAL_SENT`, `PUBLIC_PRIMARY`, ...) into a note.

The lines of `facts_fi` have these shapes:

| line | what it is |
| --- | --- |
| `syöpäpolun tuloreitti: X` (first line, kinds `standard` and `careful`) | the route by which the patient entered the cancer pathway (rule 3.4) |
| `asiointipaikka: X` (first line, kind `no_event`) | the service where this ordinary contact takes place (rule 3.4) |
| `<Finnish name of the event> [<explanation in English>]: <date string>` | a cancer-pathway event that really happened on that date (rule 3.5) |
| `<Finnish name> [not a pathway event]: <date string>`, `<Finnish name> [has not happened yet]: <date string>`, and every dated line of a `no_event` specification | a dated item that is **not** a pathway event (rule 3.6) |
| `ilman päivämäärää: <statement in English>` | something the note must also say, in your own Finnish words, without attaching any date to it |

The Finnish name tells you which fact it is, and the English text in square brackets tells you
what a reader must not be able to misunderstand. Neither is text for the note. Do not translate
the bracket, and do not build your sentence on the noun phrase.

## 3. Rules

### 3.1 Language and length

- Finnish, in the register of a real patient record.
- **60 to 140 words**, counted as whitespace-separated tokens (`len(note_text.split())`).
  Write 85 to 120 so that a miscount does not cost the note. Count the words; if a note has
  fewer than 75, add neutral content (rule 3.2). A date string such as `3. marraskuuta 2025`
  counts as three words.
- One paragraph of running prose. No heading, no list, no line break, no Markdown.
- Do not begin the note with the name of the style or any other label
  (`Hoitajan puhelinmerkintä:`, `Käyntimerkintä.`, `Loppulausunnon ote.`). Start with content.

### 3.2 State exactly the given facts

- State every line of `facts_fi`. Leave none out and soften none.
- Add no other pathway step, with or without a date: no extra contact, assessment, referral,
  specialist appointment, confirmed diagnosis, team meeting or start of treatment. If the
  specification has no diagnosis line, the note does not say that a diagnosis has been confirmed.
  Naming the disease is fine; narrating a step that is not in the specification is not.
- One date string belongs to one fact. Do not attach a date string to a different fact, and do not
  let one date string cover two events.
- Fill the remaining length with neutral, undated content that fits the facts: how the patient
  feels now, functional ability, coping at home, mood, general counselling, practical
  arrangements. Symptoms may be named, but never when they began unless the specification gives
  that. Examinations may be mentioned in general terms (`tutkimukset`, `kuvantaminen`,
  `verikokeet`), never when they were done. Do not write about tolerating a treatment when the
  specification has no start of treatment.

### 3.3 Dates

A program checks every note. It rejects the note if a date string is missing or altered, if
anything else in the note looks like a date, or if the length is outside 60 to 140 words.

- Every string in `date_strings` appears **exactly once, character for character**: same digits,
  same dots and spaces, same lower-case letters, same inflection.

  | given | rejected |
  | --- | --- |
  | `marraskuussa 2025` | `Marraskuussa 2025` at the start of a sentence (capital letter). Build the sentence so that a month string is never the first word. |
  | `3.2.2025` | `03.02.2025`, `3.2.25`, `3. helmikuuta 2025` |
  | `3.2.` | `3.2.2025` (do not add the year), `3.2` |
  | `3. marraskuuta 2025` | `3.11.2025`, `3. marraskuuta` |
  | `12 päivää sitten` | `12 pv sitten`, `kaksitoista päivää sitten`, `noin 12 päivää sitten` |
  | `8 viikkoa sitten` | `8 vk sitten`, `kaksi kuukautta sitten` |

- A string that ends in a dot (`3.2.`) may end a sentence; do not add a second dot:
  `Lähete saapui 6.8. Hoito alkoi 10.10.2025.`
- `marraskuussa 2025` means some day in that month. Do not add a day to it.
- **No other date or time reference of any kind.** Not the note date, not `tänään`, `eilen`,
  `huomenna`, `toissapäivänä`, `viime viikolla`, `viime kuussa`, `viime vuonna`; no year on its
  own (`vuonna 2019`); no month name outside a given string (`maaliskuun alussa`); no
  `2 viikon kuluttua`, `kuukautta aiemmin`; no weekday (`maanantaina`), season (`keväällä`) or
  holiday; no duration that would date something (`kolmen viikon ajan`, `parin kuukauden ajan`).
  Weekdays and durations slip past the program but still make the note wrong, because they tell
  the reader a date that is not in the answer key.
- **No digit outside the date strings.** No age, laboratory value, blood pressure, dose, clock
  time, percentage, telephone or room number, grade or stage. A value such as `13.5.` or
  `klo 14.30.` at the end of a sentence is read as a date and the note is rejected. If a small
  number is unavoidable, write it in letters (`kaksi lasta`) and only where it is not a time reference.
- `note_date` is given only so that the relative strings make sense: `12 päivää sitten` counts
  back from `note_date`, and `3.2.` lies in the year of `note_date`. The model that reads the note
  receives the note date separately. Do not write it into the note in any form.

### 3.4 Route

Finnish names of the five services: `julkinen perusterveydenhuolto` (terveyskeskus, terveysasema,
tk), `työterveyshuolto` (työterveys, työterveysasema), `yksityinen terveydenhuolto` (yksityinen
lääkäriasema), `päivystys` (päivystyspoliklinikka, yhteispäivystys, päivystysapu) and `seulonta`
(seulontayksikkö, seulontatutkimus).

- **Kinds `standard` and `careful`:** the note must say in so many words that the patient came
  onto the cancer pathway through the given service. Being a client of a service is not enough;
  a reader must be able to point at the sentence that says the pathway started there. Some ways to
  say it, with the service put in the right case; vary them and invent your own:
  `syöpäepäily heräsi tk:n vastaanotolla` / `selvittelyt käynnistyivät työterveyshuollossa` /
  `hakeutui alun perin yksityiselle lääkäriasemalle, josta asia eteni` /
  `ohjautunut hoitopolulle päivystyksen kautta` / `jatkotutkimuksiin ohjattu seulonnan perusteella` /
  `polku sai alkunsa työterveydestä` / `tk:sta ohjattu jatkoselvittelyihin syöpäepäilyn vuoksi`.
  Avoid the stock sentence `Syöpäpolun tuloreitti on ...`, and do not put the route sentence
  first in every note: in at least half of your notes it comes in the middle or near the end.
- **Kind `no_event`:** say plainly in which service the contact takes place
  (`työterveyshoitajan vastaanotolla`, `tk:n hammashoitolassa`, `yksityisellä lääkäriasemalla`,
  `päivystyksessä`, `seulontatutkimuksessa`). Do not write `syöpäpolku` or `tuloreitti`.
- **All kinds: name only the given service.** Do not mention any of the other four anywhere in the
  note, not even in passing (no `tk` in a työterveys note, no `päivystys` unless the route is
  päivystys). Hospital words are not routes and are always allowed: `erikoissairaanhoito`, `esh`,
  `poliklinikka`, `pkl`, `keskussairaala`, `osasto`.
- Staff on the entry side must match the route: `terveyskeskuslääkäri` / `työterveyslääkäri` /
  `yksityisen lääkäriaseman yleislääkäri` / `päivystävä lääkäri` / `seulontayksikön lääkäri`, and
  the corresponding nurse or booking service. The bracket of each `facts_fi` line names the right one.

### 3.5 Pathway events

Each event line is a completed fact tied to its date string: affirmative, past, no hedge
(`ilmeisesti`, `noin`, `arviolta`), no plan, no negation. Write it the way a clinician would,
with a verb. A sentence built on the noun phrase of the line (`lähetteen lähettäminen tapahtui
...`, `syöpähoidon aloitus oli ...`) is exactly the mechanical wording to avoid.
For every event a reader must be able to tell which of the nine it is:

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

You may choose a plausible cancer site (lung, colorectal, breast, prostate, haematological or
other) and a matching specialty and treatment, or leave the site unnamed. Vary it.

### 3.6 Dated items that are not events

State them as what they are, so that nobody could take them for a pathway step:

- `syntymäaika`: `s. 20.7.1961`, `syntynyt 20.7.1961`.
- `aiempi syöpään liittymätön rokotuskäynti`: an earlier vaccination, clearly unrelated to the
  present matter. Do not say where it was given (that would name a second service).
- `tuleva, vielä toteutumaton ...`: an appointment that has not taken place. Use the future or
  `on varattu`, `on tulossa`. Never write it as something that happened.
- In a `no_event` note every dated line is ordinary care.

### 3.7 The moment of writing is not an event

The note is written on `note_date`, but nothing that belongs to the pathway happens "now". Do not
present the present contact as a first contact, a physician's assessment, a referral being
written, a specialist appointment, a diagnosis being given, a team meeting or a start of
treatment. Every pathway event lies in the past at its given date string. The present contact is
a status check, a telephone call, a summary. Just write it as one; do not announce what kind of
contact it is (`Tämä käynti on tilannekatsaus`). The present needs no time word: write
`pot. kertoo yskän helpottaneen`, never `tänään pot. kertoo ...`.

### 3.8 People

The patient and all staff are invented and stay unnamed: no first names, surnames or initials, no
personal identity code, address, telephone number or employer, and no real hospital, clinic or
company name. Write `pot.`, `potilas`, `asiakas`, `allekirjoittanut`, `hoitaja`, `lääkäri`,
`keskussairaala`, `syöpätautien pkl`.

### 3.9 Never reveal the origin

Never say or hint that the text is synthetic, invented, generated, an example, a test or written
from a specification. No `kuvitteellinen`, `synteettinen`, `esimerkki`, `testi`, `tekoäly`.

### 3.10 Sound like a clinician, not like the specification

The value of your notes is that they do not all sound alike. A note that repeats the wording of
the specification, of these instructions or of your previous note teaches the model a phrase
instead of a meaning.

- **Do not copy the specification.** No run of five or more consecutive words from a `facts_fi`
  line, apart from the date string itself. No sentence of the form `<noun phrase of the line> oli
  <date>` repeated for each fact.
- **Do not copy the examples of section 8.** None of their sentences may appear in your notes,
  and not their skeleton either (route, then the facts in order, then the same closing).
- **Do not copy yourself.** No sentence twice in your 100 notes. No two consecutive notes with
  the same opening words or the same closing sentence.
- Vary the order: facts need not be chronological; the route, the birth date and the unrelated
  items can come anywhere.
- Vary the voice: passive, `allekirjoittanut`, `pot. kertoo`, telegraphic fragments without a verb.
- Vary the filler. Pick two or three topics per note and rotate: present symptoms, pain,
  appetite and weight (no numbers), sleep, mood and worry, mobility, work, family and help at
  home, questions the patient asked, what was explained, how to get in touch.
- Use natural clinical abbreviations where they fit, typically two to five per note, never
  forced: `pot.`, `yt.`, `anam.`, `esh`, `pkl`, `vo`, `sh`, `el`, `dg`, `PAD`, `jatkot`,
  `kontr.`, `ad`, `ko.`, `em.`, `os.`, `tutk.`, `oik.`, `vas.`, `s.` and, only when it is the
  route, `tk` or `tth`. Never abbreviate inside a date string.

## 4. Why the wording matters

An independent reader checked sixty notes of the first data set. The two notes where the label
could not be defended were both wording problems:

- `on saanut lähetteen marraskuussa 2025`: "the patient got a referral" fits a referral being
  sent as well as a referral being received.
- `Yt. sisältää käynnin 20.3.2025`: a visit whose type is not stated.

Rule 3.5 and the `careful` specifications exist to remove exactly these two ambiguities.

## 5. The three kinds

**`standard`** (75 per slice). A pathway note with one to four events. `wording` is empty; the
rules above apply.

**`careful`** (12 or 13 per slice). The lines of `wording` are binding. Each of these forces one
of two distinctions:

- *Sent versus received.* `lähetteen lähettäminen` is the act of the referring physician.
  `lähetteen vastaanottaminen` is the arrival and registration of the referral at the hospital.
  When both are present they are two acts on two dates, and the verb at each date must show the
  direction. When only one is present, write from the side named in `wording` and do not say
  anything about the other act.
- *Which contact.* `ensimmäinen yhteydenotto` (the patient gets in touch; a nurse or the booking
  service answers), `lääkärin arvio` (the physician of the entry service examines) and
  `erikoislääkärikäynti` (the treating specialist in specialised care) are three different
  things. Say who received the patient at each date. Name the specialty or the clinic for a
  specialist appointment.

Some `careful` specifications contain a line `ilman päivämäärää: ...` (for example that the
patient has not yet seen a specialist). Say it in your own Finnish words, and give it no date.

**`no_event`** (12 or 13 per slice). An ordinary note that has nothing to do with cancer: a
vaccination, a prescription renewal, a dental check, a minor complaint, a routine check-up. The
correct extraction is an empty list, so:

- do not mention cancer, a tumour, a suspicious finding, cancer screening or further
  investigations;
- the dated lines are ordinary care; write them as such;
- where `focus` is `non_cancer_lookalike`, the line deliberately resembles a pathway step (a
  referral to physiotherapy, an appointment with an orthopaedic surgeon, diabetes being
  diagnosed). Keep the benign reason that the line gives explicit in the note;
- where `focus` is `non_cancer_screening`, the screening is not a cancer screening. Say what it
  is (for example bone density, hearing, eye fundus).

## 6. The four styles

| `style` | write it as |
| --- | --- |
| `käyntimerkintä` | a visit entry by a clinician. The present visit is a status check (rule 3.7). |
| `hoitajan puhelinmerkintä` | a nurse's entry about a telephone call with the patient. The call is routine contact, not the first contact. |
| `loppulausunnon ote` | an excerpt of a summary or discharge statement, looking back. |
| `lähetekirje` | the background section of a letter to a colleague. Do not write that a referral is being written or sent now (`lähetän`, `pyydän arviota`); a referral appears only if a line of `facts_fi` says so, and then in the past with its date string. |

The style shapes the voice of the note. Its name is never written into the note (rule 3.1).

## 7. Check before saving

For every note:

1. Is every string of `date_strings` in the note exactly once, unchanged, and not capitalised?
2. Is there any other digit, date, weekday, month name, duration or word like `tänään` or `eilen`? Remove it.
   Look for `tänään` in particular: it is easy to write when describing how the patient is.
3. Is the length between 60 and 140 words, and preferably between 85 and 120?
4. Is every line of `facts_fi` stated, including the route or service and any `ilman päivämäärää` line?
5. Could a reader tell for each event which of the nine it is, and for each other dated item that it is not an event?
6. Is any pathway step mentioned that is not in the specification, or presented as happening now? Remove it.
7. Is only the given service named? No name, no identifier, no hint that the text is invented?
8. `kind` is `no_event`: is the note free of anything about cancer?
9. Does the note start with content, not a label? Does it share a sentence or a five-word run
   with the specification, with an example of section 8 or with one of your earlier notes? Rewrite it.

For every file: valid JSON array, at most 25 objects, keys exactly `id` and `note_text`, ids copied
unchanged, correct file name.

## 8. Three worked examples

These show that the rules can be met. They are not templates: rule 3.10 forbids reusing their
sentences or their structure. The specifications are abridged and their ids are placeholders.

<!-- example-spec -->
```json
{"id": "EXAMPLE-STANDARD", "kind": "standard", "focus": "sampler_v1", "style": "hoitajan puhelinmerkintä", "note_date": "2025-10-15", "facts_fi": ["syöpäpolun tuloreitti: työterveyshuolto", "lähetteen lähettäminen [the referring physician wrote the referral and SENT it to specialised care; this is not its arrival]: 4 viikkoa sitten", "syöpädiagnoosin vahvistaminen [the cancer diagnosis was confirmed]: lokakuussa 2025", "tuleva, vielä toteutumaton kontrolliaika [has not happened yet]: 12.11.2025", "syntymäaika [not a pathway event]: 3.4.1968"], "date_strings": ["4 viikkoa sitten", "lokakuussa 2025", "12.11.2025", "3.4.1968"], "wording": [], "facts": [{"type": "REFERRAL_SENT", "date": "2025-09-17", "precision": "DAY", "expression": "4 viikkoa sitten", "form": "weeks", "meaning": "lähetteen lähettäminen"}, {"type": "DIAGNOSIS", "date": "2025-10-01", "precision": "MONTH", "expression": "lokakuussa 2025", "form": "month", "meaning": "syöpädiagnoosin vahvistaminen"}], "distractors": [{"kind": "future", "expression": "12.11.2025", "date": "2025-11-12", "meaning": "tuleva, vielä toteutumaton kontrolliaika"}, {"kind": "birth", "expression": "3.4.1968", "date": "1968-04-03", "meaning": "syntymäaika"}], "ground_truth": {"entry_route": "OCCUPATIONAL", "events": [{"type": "REFERRAL_SENT", "date": "2025-09-17", "precision": "DAY"}, {"type": "DIAGNOSIS", "date": "2025-10-01", "precision": "MONTH"}]}}
```

<!-- example-output -->
```json
[{"id": "EXAMPLE-STANDARD", "note_text": "Soitettu sovitusti, pot. s. 3.4.1968 vastaa kotoa. Kertoo ruokahalun heikentyneen, paino kuitenkin ennallaan ja kipuja vähän. Yöunet katkonaisia, mieliala vaihtelee odottelun vuoksi. Taustana suolistosyövän selvittelyt, jotka käynnistyivät työterveyshuollossa: työterveyslääkärin lähete esh:oon lähti 4 viikkoa sitten. Dg varmistui PAD-vastauksesta lokakuussa 2025, ja asia on käyty pot:n kanssa läpi. Kerrattu, mihin soittaa, jos vointi heikkenee tai nousee kuume. Kannustettu liikkumaan voimien mukaan ja syömään pieniä aterioita usein. Puoliso on tukena arjessa. Kontr. on varattu 12.11.2025, kutsu on tullut perille. Pot. toivoo saavansa tiedon jatkosta myös kirjeitse. Ei muuta kysyttävää tällä erää."}]
```

<!-- example-spec -->
```json
{"id": "EXAMPLE-CAREFUL", "kind": "careful", "focus": "referral_sent_and_received", "style": "loppulausunnon ote", "note_date": "2025-03-20", "facts_fi": ["syöpäpolun tuloreitti: julkinen perusterveydenhuolto", "lääkärin arvio [examined and assessed by: terveyskeskuslääkäri; not a nurse, not the treating specialist in specialised care]: 3.2.", "lähetteen lähettäminen [the referring physician wrote the referral and SENT it to specialised care; this is not its arrival]: 4. helmikuuta 2025", "lähetteen vastaanottaminen [the referral ARRIVED at the specialised-care unit and was registered there; this is not its sending and not the patient getting a referral]: 37 päivää sitten", "erikoislääkärikäynti [the patient attended the appointment of the treating specialist in specialised care]: 2 viikkoa sitten", "aiempi syöpään liittymätön rokotuskäynti [not a pathway event]: 14.10.2023"], "date_strings": ["3.2.", "4. helmikuuta 2025", "37 päivää sitten", "2 viikkoa sitten", "14.10.2023"], "wording": ["Perspective: a specialised-care unit, or a summary that knows both dates of the referral.", "Two separate acts on two dates: the referring physician SENT the referral, and the referral ARRIVED in specialised care and was registered there. The verb at each date string must show the direction (sending: 'lähetti', 'lähti', 'lähetetty', 'toimitettu'; arrival: 'saapui', 'tuli', 'vastaanotettu', 'kirjattu saapuneeksi').", "Never 'potilas sai lähetteen' or 'lähete tehty', and never a referral without a verb that shows sending or arrival."], "facts": [{"type": "PHYSICIAN_ASSESSMENT", "date": "2025-02-03", "precision": "DAY", "expression": "3.2.", "form": "no_year", "meaning": "lääkärin arvio"}, {"type": "REFERRAL_SENT", "date": "2025-02-04", "precision": "DAY", "expression": "4. helmikuuta 2025", "form": "long", "meaning": "lähetteen lähettäminen"}, {"type": "REFERRAL_RECEIVED", "date": "2025-02-11", "precision": "DAY", "expression": "37 päivää sitten", "form": "days", "meaning": "lähetteen vastaanottaminen"}, {"type": "SPECIALIST_VISIT", "date": "2025-03-06", "precision": "DAY", "expression": "2 viikkoa sitten", "form": "weeks", "meaning": "erikoislääkärikäynti"}], "distractors": [{"kind": "vaccination", "expression": "14.10.2023", "date": "2023-10-14", "meaning": "aiempi syöpään liittymätön rokotuskäynti"}], "ground_truth": {"entry_route": "PUBLIC_PRIMARY", "events": [{"type": "PHYSICIAN_ASSESSMENT", "date": "2025-02-03", "precision": "DAY"}, {"type": "REFERRAL_SENT", "date": "2025-02-04", "precision": "DAY"}, {"type": "REFERRAL_RECEIVED", "date": "2025-02-11", "precision": "DAY"}, {"type": "SPECIALIST_VISIT", "date": "2025-03-06", "precision": "DAY"}]}}
```

<!-- example-output -->
```json
[{"id": "EXAMPLE-CAREFUL", "note_text": "Yskä ja laihtuminen veivät pot:n alun perin terveyskeskukseen, josta syöpäepäilyn selvittely käynnistyi. Tk-lääkäri tutki pot:n 3.2. ja lähetti lähetteen keuhkosairauksien pkl:lle 4. helmikuuta 2025. Yksikköömme lähete saapui ja kirjattiin vastaanotetuksi 37 päivää sitten. Keuhkolääkärin vastaanotolla pkl:lla pot. kävi 2 viikkoa sitten. Yt. kohtalainen, liikkuu omatoimisesti ja pärjää kotona puolison turvin. Hengenahdistusta rasituksessa, levossa ei. Ruokahalu on heikko, mutta nesteitä kuluu riittävästi. Tupakoinnin lopettamista tuettu, kirjalliset ohjeet annettu yhteydenottoa varten. Rokotustiedoista ilmenee influenssarokotus 14.10.2023, mikä ei liity nykyiseen asiaan. Pot:lle kerrottu, että seuraavista vaiheista ilmoitetaan kirjeitse."}]
```

<!-- example-spec -->
```json
{"id": "EXAMPLE-NO-EVENT", "kind": "no_event", "focus": "prescription_renewal", "style": "hoitajan puhelinmerkintä", "note_date": "2026-01-22", "facts_fi": ["asiointipaikka: yksityinen terveydenhuolto", "verenpainelääkkeen reseptin uusiminen: 9 päivää sitten", "tuleva, vielä toteutumaton lääkityksen seurantakäynti: 14. huhtikuuta 2026"], "date_strings": ["9 päivää sitten", "14. huhtikuuta 2026"], "wording": ["This note has nothing to do with cancer: no cancer, tumour, suspicious finding, cancer screening or further investigations.", "Say clearly in which service the contact takes place (the given asiointipaikka).", "The upcoming appointment has not happened; do not write it as done."], "facts": [], "distractors": [{"kind": "ordinary", "expression": "9 päivää sitten", "date": "2026-01-13", "meaning": "verenpainelääkkeen reseptin uusiminen"}, {"kind": "future", "expression": "14. huhtikuuta 2026", "date": "2026-04-14", "meaning": "tuleva, vielä toteutumaton lääkityksen seurantakäynti"}], "ground_truth": {"entry_route": "PRIVATE", "events": []}}
```

<!-- example-output -->
```json
[{"id": "EXAMPLE-NO-EVENT", "note_text": "Asiakas soittaa yksityisen lääkäriaseman hoitajalle verenpainelääkityksestään. Resepti on uusittu 9 päivää sitten ja lääke haettu apteekista ongelmitta. Kotimittauksissa paineet ovat asiakkaan mukaan olleet tavoitetasolla, huimausta tai päänsärkyä ei ole ollut. Lääke otetaan aamuisin, unohduksia ei juuri tule. Kerrattu suolan vähentäminen, säännöllinen liikunta ja kotimittausten kirjaaminen omaseurantavihkoon. Asiakas kokee vointinsa hyväksi, jaksaa arjessa normaalisti ja kyselee vielä lääkkeen ottamisesta matkoilla. Lääkityksen seurantakäynti on varattu lääkäriasemalle 14. huhtikuuta 2026, sitä ennen ei ole tarvetta kontrolliin. Ohjattu ottamaan yhteyttä aiemmin, jos paineet nousevat tai ilmaantuu uusia oireita. Asiakas kiittää neuvoista."}]
```

## 9. Notes for whoever uses the output

- For kind `no_event` the answer key still names a service in `entry_route`, because the output
  format of the model requires one of the five values. The convention is: when a note has no
  pathway event, `entry_route` is the service in which the note says the contact takes place.
- Ids of kinds `standard` and `careful` are the SHA-256 of the answer key (route and events), the
  same rule as in the first data set, and none of them occurs there. Ids of kind `no_event` also
  cover the dated content, because an empty answer cannot identify a note.
- To use a specification with the first data set's code (`scribe/verify.py`, `scribe/metrics.py`,
  `scribe/evaluate.py --extra-test`), lift the answer key to the top level:
  `row = {**spec, **spec["ground_truth"], "target_json": json.dumps(spec["ground_truth"], ensure_ascii=False, separators=(",", ":"))}`.
  For kind `standard` this string equals the `target_json` of `scribe/sample.py`.
- `verify.accept` of the first data set returns false for any row without an event, so `no_event`
  notes need an acceptance rule of their own. In a `no_event` specification every dated item is
  listed under `distractors`; `facts` is empty.
- `split_hint` applies the hash rule of `scribe/sample.py` to the id. It is a suggestion that
  keeps identical answer keys in one split; nothing depends on it.
- The explanations in `facts_fi` and the lines of `wording` are in English on purpose. In a pilot
  with Finnish explanations the writer pasted them into the notes; see `runs/v2-data.jsonl`.
- Measured in those pilots with Claude Haiku through the local helper (medium effort, answer as
  JSON): six notes in one call used 11,860 to 14,388 output tokens, hidden reasoning included, and
  three of six such calls timed out; three notes in one call used 7,960 to 12,514 output tokens,
  and one of four such calls stopped at a 12,000-token limit. A writer that is limited to 16,000
  output tokens per call cannot return a 25-note part in one call.
- The slices were built by `data/scribe/v2/slices/_build_slices.py` and checked by
  `data/scribe/v2/slices/_validate_slices.py`, which also runs the three examples above and the
  statements of rule 3.3 through the date check of `scribe/verify.py`.
