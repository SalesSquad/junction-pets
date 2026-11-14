# Lens learning loop

Work: LENS-LEARNING-20261114. Source admission: Junction commit
`9e1915827fabff9836dac217ab69727e514acc49`.

## Design decision

Extend the existing Resume browser journey with an executable, explicitly
synthetic learning experience: teach a preference, pause/resume a task, correct
that preference, reuse it in a later episode, then forget it and its derived
state. Episodes, confirmed preferences, and user-attested learning outcomes stay
separate. Goals and feedback can change the suggested amount of help. Model
decisions are advisory and cannot confirm progress, consent or mastery.

The Junction implementation is a portable reference and developer simulation,
not the authenticated private Chibi memory store. Real identity, authorization,
encrypted persistence and consent remain in private Chibi. Existing Chibi and
Taimi sources are referenced, never copied into this repository. No raw video,
private conversation or real personal profile belongs in fixtures or receipts.

## Shared implementation contract

Browser core: `apps/meta-resume-web/learning-core.mjs`.
`createLearningSession({scope, now})` returns `dispatch(command, {actor})`,
`snapshot()`, `recommend(task, {requested})`, `admitDecision(decision, task)`,
`exportState()` and `handoff(recipient, task)`.
`restoreLearningSession(saved, {scope, now})` validates the full synthetic save.
Scope has exact keys tenantId, ownerId, contextId; fixture IDs are synthetic.
All commands have exact keys schema, commandId, expectedRevision, operation,
payload. Schema is `lens.learning-command/v1`; actor is supplied by the caller,
never accepted from command data. User commands alone can change consent,
confirm/correct/forget memory, feedback and learning outcomes.

Operations and exact payloads:
- `setConsent`: {enabled:boolean}
- `setGoal`: {goal:'finish'|'learn'}
- `startEpisode`: {episodeId:string, templateId:string}
- `proposeMemory`: {memoryId:string, style:'one_step'|'detailed'|'quiet'}
- `confirmMemory`: {memoryId:string}
- `correctMemory`: {memoryId:string, style:'one_step'|'detailed'|'quiet'}
- `forgetMemory`: {memoryId:string}
- `forgetAll`: {}
- `checkpoint`: {taskId:string, taskRevision:integer, nextStepId:string|null}
- `recordOutcome`: {stepId:string, correct:boolean, hints:integer}
- `recordFeedback`: {proposalId:string, value:'useful'|'distracting'}
- `setReminder`: {reminderId:string, stepId:string}
- `ackReminder`: {reminderId:string}

Task inputs have exact keys taskId, revision, status ('active', 'interrupted',
'completed'), nextStepId (string|null). Recommendations carry explicit
SYNTHETIC/advisory labels and bind scope, episode, learning revision, memory
epoch, task revision, and expiry. Reject stale results after any relevant user
change. A repeated assisted practice does not create independent mastery.

## Evaluation transport contract

`simulate.mjs` writes a suite with schema `lens.learning-evaluation-suite/v1`,
evidenceMode `SYNTHETIC`, source {baseCommit, files}, and cases. Each case has
{id, request, expected, domain}. `request` is the existing exact
`factory.decision-assist-request/v1` object; its source_sha256 equals SHA-256 of
its input UTF-8 bytes. `expected` maps question names to allowed choice values
(an array per question). It is NEVER sent to a provider. `domain` contains
separate deterministic observations for the local simulation report.

`evaluate.py` imports the verified pinned Factory decision adapter from an
external checkout. It must not copy private Factory sources or read keys for
offline runs. Offline injected transports test serialization/normalization and
are labelled simulated responses; actual Jev/Decisions runs require explicit
live selection and remain separate. Preserve refusals, malformed replies,
timeouts and unknown delivery without blind retries. Count actual calls and
tokens; unknown cost stays unknown. No provider output grants runtime authority.

## Acceptance

Run the bounded local simulation, provider-contract simulation, and one browser
journey covering teach → pause → resume → correct → next episode → forget.
Include wrong-scope restore, stale response, denied model mutation, assisted
practice, duplicate command and changed-goal cases. Run each real provider only
on the fixed synthetic suite through existing authorized credentials/budget.
These checks do not qualify physical glasses, production memory, actual
Taimi mastery, SAM inference or a live private Chibi host.
