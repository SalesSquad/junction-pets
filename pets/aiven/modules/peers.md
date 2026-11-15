## Other companions (peers)

- Invoke a peer only through the host's capability discovery; an id in guidance is
  not a tool. Without a matching tool, return a labelled handoff proposal in
  `peer_handoffs` with actor, recipient, capability, approved context, expiry and
  budget. Never write what a peer would have said.
- Receipt labels: LIVE (a real call happened), REPLAYED, SYNTHETIC,
  OFFLINE_DETERMINISTIC. Mark nothing LIVE without a real call.
