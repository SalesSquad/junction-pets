# Invented SMS cue-declaration review

`reviewFictionalSms(text)` from `sms-guidance.mjs` is a pure, deterministic
teaching helper for an invented scenario. It examines **supplied cue declarations**,
not SMS text. It is not a phishing detector, sender authentication service,
financial advisor or bank connection. No input is fetched, opened or executed.
[`example-sms.json`](example-sms.json) is entirely fictional: no real message,
URL, phone number, person, account, credential or bank assertion is included.

## Exact input

Accept a primitive string of at most **8,192 UTF-8 bytes**, parsed with ordinary
`JSON.parse`: duplicate object members use the last value. This is not a
canonical or duplicate-key security parser. Malformed input, missing/extra
fields and wrong types throw `TypeError`; there are no defaults or coercions.

| Field | Required value / domain |
| --- | --- |
| `schemaVersion` | Exactly `1` |
| `kind` | Exactly `"fictional-sms-safety-scenario"` |
| `scenarioId` | `fictional-` plus 1–64 lowercase ASCII letters/digits/hyphens, beginning with a letter/digit; no controls |
| `cues` | Exactly six boolean-or-null fields listed below |
| `outsideCheck` | `"reported-match"`, `"reported-mismatch"`, `"unknown"`, or explicit `null` |
| `requestedAction` | `"guidance"`, `"open-link"`, `"account-login"`, `"make-payment"`, or `"confirm-authenticity"` |

The six cue fields, in deterministic output order, are `urgentDeadline`,
`messageLink`, `credentialRequest`, `paymentRequest`, `attachment`,
`displayNameMatch`. `true` means a cue is declared present; `false` means
declared absent; `null` means unknown. Missing is malformed, never equivalent
to false or null. Numeric zero, strings and other values are rejected.

An outside check is an **unverified supplied declaration**, not a check performed
by this helper. A reported match and displayed branding cannot authenticate the
sender. A reported mismatch adds a warning but does not establish fraud.
The closed input deliberately has no message text, contact, URL, account,
credential, login result or authenticity field. Scenario labels are identifiers,
not instructions, evidence or real user information.

## Exact output

Returns exactly `{schemaVersion:1, kind:"fictional-sms-guidance-report",
scenarioId, classification, warningSigns, unknownFields, notes, guidance,
action, deniedAction, boundary}`. There is no probability or confidence score.

- `classification` is `declared-warning-signs` when any warning exists;
  otherwise `incomplete-declarations` when any unknown exists; otherwise
  `no-listed-warning-declared`. **None means safe, genuine, fraudulent,
  complete threat coverage, or independently verified.**
- `warningSigns` contains `{code, field}` for each true first-five cue, in cue
  order: `declared-urgent-deadline`, `declared-message-link`,
  `declared-credential-request`, `declared-payment-request`,
  `declared-attachment`. Fields are `cues.<name>`. An outside mismatch appends
  `{code:"reported-outside-mismatch", field:"outsideCheck"}`.
- `unknownFields` lists every null cue path in cue order, followed by
  `outsideCheck` when that declaration is null or `"unknown"`. Unknowns remain
  visible even when warnings dominate the classification.
- `notes` is always `branding-is-not-authentication` and
  `outside-check-is-an-unverified-declaration`.
- `guidance` always contains three inert codes: do not follow message links or
  attachments; do not share credentials or codes; verify through an independently
  reached official channel. Their exact strings are
  `do-not-follow-message-links-or-attachments`, `do-not-share-credentials-or-codes`,
  `verify-through-independently-reached-official-channel`. They are not a claim
  that any channel was reached, checked or contacted; no channel URL or number
  is invented. This is illustrative safety guidance, not incident-response coverage.
- `action` is always `guidance-only`; `deniedAction` is null for `guidance`,
  otherwise the exact requested action. Link opening, login, payments and
  authenticity confirmation remain refused even with no declared warning.
- `boundary` is always `{synthetic:true, senderAuthenticated:false,
  fraudDetermined:false, accountAccessed:false, financialActionExecuted:false}`.

Every result is newly allocated. Calls are deterministic and independent of
object member order or past calls. No provider, filesystem, clock, user account,
device or network is accessed. A Node source helper is not automatically exposed
as a generated plugin tool or Chibi runtime capability.

## Source checks

`node --test tests/pet-s-pankki.test.mjs` covers ten positive/adversarial/boundary
cases: warning mapping, null/false/missing, branding and reported checks, refused
effects, closed bounded JSON, duplicate-member behavior, isolation and the
invented example. The six authored model evals remain unchanged and are not
executed or qualified by these deterministic checks.
