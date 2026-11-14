// Entirely fictional, authored fixtures. No real participants, employers or verification.
export const asOf = '2026-11-14';
const time = (hour) => `2026-11-15T${hour}:00Z`;
const window = (start, end) => ({ start: time(start), end: time(end) });
const card = (id, skills, title, sourceType, excerpt, outcome, ref) => ({
  id, skills, title, sourceType, excerpt, outcome,
  issuer: 'Candidate-provided fictional portfolio', ref,
  observedDate: '2026-11-10', externalVerification: false,
});
export const roles = [
  { id: 'repair', employerId: 'loop', employer: 'Loop Works · fictional employer', title: 'Build a repair-service prototype',
    summary: 'A practical builder to make a small service usable, measurable and ready for a conversation.',
    requiredSkills: [{ id: 'javascript', label: 'JavaScript', weight: 5 }, { id: 'accessibility', label: 'Accessibility', weight: 3 }, { id: 'testing', label: 'Testing', weight: 2 }],
    availability: [window('09:00', '10:20')], relevantTopIds: ['mira'] },
  { id: 'host', employerId: 'commons', employer: 'Commons Studio · fictional employer', title: 'Host a community co-design session',
    summary: 'A thoughtful facilitator to turn different needs into a clear, testable service idea.',
    requiredSkills: [{ id: 'facilitation', label: 'Facilitation', weight: 5 }, { id: 'research', label: 'Research', weight: 3 }, { id: 'accessibility', label: 'Accessibility', weight: 2 }],
    availability: [window('09:20', '10:40')], relevantTopIds: ['jules'] },
];
export const candidates = [
  { id: 'mira', name: 'Mira', headline: 'I make small things work.', bio: 'I built a repair desk prototype and wrote down what broke.',
    availability: [window('09:00', '10:00')], evidence: [
      card('M-01', ['javascript', 'testing'], 'Repair desk: offline queue', 'artifact', 'A 42-line queue stores repair requests locally. The supplied code sample includes replay and empty-queue checks.', 'Six authored replay cases complete without duplicate requests in the fictional sample.', 'demo:repair-queue/v1'),
      card('M-02', ['accessibility'], 'Keyboard walkthrough', 'walkthrough', 'Supplied walkthrough follows focus order, field labels and error recovery using the keyboard.', 'Three missing labels identified and corrected in the fictional prototype.', 'demo:keyboard-notes/v2'),
    ] },
  { id: 'devon', name: 'Devon', headline: 'Visionary. Full-stack. Everything-ready.',
    bio: 'JavaScript accessibility testing facilitation research. Expert JavaScript, accessibility, testing, facilitation and research. JavaScript accessibility testing facilitation research leader. Award-winning results-driven innovator.',
    availability: [window('09:20', '10:40')], evidence: [
      card('D-01', ['javascript', 'accessibility', 'testing', 'facilitation', 'research'], 'General résumé statement', 'statement', 'I am an expert in all of these skills. No work sample, method or result supplied.', '', 'demo:resume-statement/v1'),
    ] },
  { id: 'jules', name: 'Jules', headline: 'I help a room find its next step.', bio: 'I plan workshops and keep usable notes.',
    availability: [window('09:40', '10:40')], evidence: [
      card('J-01', ['facilitation', 'research'], 'Neighbourhood repair workshop', 'artifact', 'Supplied agenda, anonymised fictional interview prompts and synthesis notes explain how competing needs became a prototype question.', 'Five fictional workshop observations mapped to two experiments with explicit open questions.', 'demo:workshop-pack/v1'),
      card('J-02', ['accessibility'], 'Inclusive session walkthrough', 'walkthrough', 'Supplied plan includes quiet participation, readable instructions and a keyboard-operable feedback form.', 'An alternative written participation path was added after a fictional rehearsal.', 'demo:session-walkthrough/v1'),
    ] },
  { id: 'ren', name: 'Ren', headline: 'A fresh conversation, still to be explored.', bio: 'Interested in learning through practical work. Portfolio not yet shared.',
    availability: [window('12:00', '13:00')], evidence: [] },
];
