# aiven-decision-bridge architecture

bridge.mjs validates response v1/v2 and maps each proposal to a Chibi PendingAction (canonical proposal and payload hashes, idempotency key) and to the ActionDecisionBinding a person approves or declines; lint.mjs adds deterministic checks that drive one repair turn.

No provider, host or Aiven write is performed by this code; live paths are read-only or need an explicit host grant.
