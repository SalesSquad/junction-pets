/** Public, synthetic data. No real image, person, location or device. */
export const id = (suffix) => `00000000-0000-4000-8000-${String(suffix).padStart(12, '0')}`;

export const FIXTURE = Object.freeze({
  schemaVersion: 1,
  id: 'camera-bag-v1',
  taskId: id(100),
  title: 'Pack your camera bag',
  now: '2026-11-14T12:00:00Z',
  sessionId: id(401),
  captureGeneration: 1,
  maxEvidenceAgeMs: 300_000,
  steps: [
    { stepId: id(201), subjectId: id(301), label: 'Camera', detail: 'Camera body, with the lens cap on.', icon: 'camera' },
    { stepId: id(202), subjectId: id(302), label: 'Microphone', detail: 'Microphone and its receiver.', icon: 'mic' },
    { stepId: id(203), subjectId: id(303), label: 'Your charger', detail: 'Check it is yours, then put it in the bag.', icon: 'charger' },
  ],
  archived: {
    evidenceId: id(500), stepId: id(203), subjectId: id(303), sessionId: id(401),
    captureGeneration: 0, capturedAt: '2026-11-14T11:00:00Z',
    label: 'Your charger · desk', classification: 'historical',
    detail: 'A dated sighting. It says nothing about what is in your bag now.',
  },
  observations: [
    {
      evidenceId: id(501), stepId: id(203), subjectId: id(303), sessionId: id(401),
      captureGeneration: 1, capturedAt: '2026-11-14T11:59:30Z',
      label: 'Your charger · fixture identity match', classification: 'verified-fixture',
      detail: 'Synthetic exact-identity evidence for transport parity. Still not a completed step.',
    },
    {
      evidenceId: id(502), stepId: id(203), subjectId: id(399), sessionId: id(401),
      captureGeneration: 1, capturedAt: '2026-11-14T11:59:30Z',
      label: 'A similar white charger', classification: 'lookalike',
      detail: 'A different synthetic item. Rejected as evidence for your charger.',
    },
  ],
});

export const TRANSPORT_KEYS = ['schemaVersion', 'taskId', 'commandId', 'expectedRevision', 'operation', 'payload'];
export const OPERATIONS = Object.freeze({
  confirmStep: ['stepId'], interrupt: [], observe: ['evidenceId'],
  resume: ['evidenceIds'], correctStep: ['stepId'], revokeEvidence: ['evidenceId'],
});
