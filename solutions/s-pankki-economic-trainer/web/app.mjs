import {answerQuestion, BASKETS, budgetCapacity, centsToEuros, currentMonth, latestDate, readTransactions, selectEvidenceRows, spendingSummary} from '../src/coach.mjs';
import {syntheticRows} from '../src/demo-data.mjs';

const $ = (id) => document.getElementById(id);
let transactions = readTransactions(syntheticRows);
let assumptions = {regularBills: '350.00', irregularBuffer: '150.00', emergencyBuffer: '120.00'};
let lastQuestion = 'Where did my money go this month?';

function textElement(tag, className, value) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  el.textContent = value;
  return el;
}

function renderOverview() {
  const capacity = budgetCapacity(transactions, assumptions);
  $('balance').textContent = centsToEuros(capacity.balanceCents);
  $('available').textContent = centsToEuros(capacity.availableCents);
  $('last-date').textContent = new Date(`${latestDate(transactions)}T12:00:00Z`).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
  $('period-subtitle').textContent = `${new Set(transactions.map(x => x.accountId)).size} example account(s) · no live sync`;
}

function renderBaskets() {
  const summary = spendingSummary(transactions);
  const month = new Date(`${summary.month}-01T12:00:00Z`).toLocaleDateString('en-GB', {month: 'long', year: 'numeric', timeZone: 'UTC'});
  $('month-label').textContent = month.toUpperCase();
  const cards = $('basket-cards');
  cards.replaceChildren();
  const settings = [
    {id: 'mandatory-regular', icon: '⌂', color: '#8c71db', description: 'Rent, essentials and the bills that arrive again.'},
    {id: 'mandatory-irregular', icon: '✦', color: '#e6b16c', description: 'The surprises worth keeping a buffer for.'},
    {id: 'everyday', icon: '☼', color: '#64b69b', description: 'Little choices that add up — and can change.'},
  ];
  const total = Math.max(1, summary.spentCents);
  for (const option of settings) {
    const card = textElement('article', 'basket-card', '');
    card.append(textElement('span', 'basket-emoji', option.icon));
    card.append(textElement('h3', '', BASKETS.find(x => x.id === option.id).label));
    card.append(textElement('p', '', option.description));
    card.append(textElement('strong', '', centsToEuros(summary.totals[option.id])));
    const track = textElement('div', 'basket-bar', '');
    const fill = document.createElement('div');
    fill.style.setProperty('--bar', option.color);
    const portion = Math.max(0, Math.min(100, (summary.totals[option.id] * 100) / total));
    fill.style.width = `${portion.toFixed(1)}%`;
    track.append(fill); card.append(track);
    card.append(textElement('div', 'basket-foot', `${Math.round(portion)}% of net monthly outgoings`));
    cards.append(card);
  }
  const unclassified = summary.totals.unclassified;
  $('unclassified-banner').textContent = unclassified > 0
    ? `${centsToEuros(unclassified)} has an unmapped category. Lumo keeps it visible instead of silently guessing whether it is essential or discretionary.`
    : 'All recognised outgoings in this snapshot have an explicit basket; review category definitions before applying them to other datasets.';
}

function renderTransactions(highlight = []) {
  const tbody = $('transaction-rows');
  const highlights = new Set(highlight);
  tbody.replaceChildren();
  const visibleRows = selectEvidenceRows(transactions, highlight);
  $('row-count').textContent = `${visibleRows.length} / ${transactions.length} ROWS (CITED ROWS ALWAYS INCLUDED)`;
  for (const x of visibleRows) {
    const tr = document.createElement('tr');
    tr.id = `source-row-${x.row}`;
    if (highlights.has(x.row)) tr.className = 'highlight-row';
    tr.append(textElement('td', 'source-row', `#${x.row}`));
    tr.append(textElement('td', '', x.date));
    tr.append(textElement('td', 'category-name', x.category));
    const pillCell = document.createElement('td');
    const pill = textElement('span', `basket-tag ${x.basket === 'mandatory-irregular' ? 'basket-irregular' : x.basket === 'everyday' ? 'basket-everyday' : x.basket === 'unclassified' ? 'basket-unclassified' : x.basket === 'non-spending' ? 'basket-non-spending' : ''}`, x.basket.replaceAll('-', ' '));
    pillCell.append(pill); tr.append(pillCell);
    const amount = textElement('td', `right ${x.changeCents < 0 ? 'money-negative' : 'money-positive'}`, centsToEuros(x.changeCents));
    tr.append(amount); tbody.append(tr);
  }
}

function renderAnswer(question) {
  let answer;
  try { answer = answerQuestion(question, transactions, assumptions); }
  catch (error) { answer = {type: 'refusal', title: 'Calculation refused', message: error.message, sources: []}; }
  const area = $('answer');
  area.replaceChildren();
  area.append(textElement('div', 'answer-title', answer.type === 'refusal' ? 'NOT ENOUGH INFORMATION' : 'CALCULATED · NOT GENERATED'));
  area.append(textElement('p', 'answer-text', answer.message));
  if (answer.type === 'budget') {
    const x = answer.result;
    const gap = x.shortfallCents > 0 ? ` Reserves exceed observed balances by ${centsToEuros(x.shortfallCents)}; illustrative spending room is zero.` : '';
    area.append(textElement('div', 'answer-note', `max(0, observed ${centsToEuros(x.balanceCents)} − regular ${centsToEuros(x.reserves.regularBills)} − irregular ${centsToEuros(x.reserves.irregularBuffer)} − emergency ${centsToEuros(x.reserves.emergencyBuffer)}) = ${centsToEuros(x.availableCents)}.${gap} ${x.caveat}`));
  } else if (answer.type !== 'refusal') {
    area.append(textElement('div', 'answer-note', 'Derived from the local historical dataset. Transfers are excluded, refunds offset recognised spending, and unknown categories remain explicitly unclassified.'));
  }
  if (answer.sources.length) {
    const sourceList = textElement('div', 'source-list', '');
    sourceList.setAttribute('aria-label', 'Cited transaction row numbers');
    for (const row of answer.sources.slice(0, 30)) {
      const a = textElement('a', 'source-pill', `CSV #${row}`);
      a.href = `#source-row-${row}`;
      a.title = `Jump to source row ${row} in the evidence explorer`;
      sourceList.append(a);
    }
    if (answer.sources.length > 30) sourceList.append(textElement('span', 'source-pill', `+${answer.sources.length - 30} additional rows`));
    area.append(sourceList);
  }
  renderTransactions(answer.sources);
}

function renderAll() {
  renderOverview();
  renderBaskets();
  renderAnswer(lastQuestion);
}

document.querySelectorAll('[data-prompt]').forEach(button => {
  button.addEventListener('click', () => {
    lastQuestion = button.getAttribute('data-prompt');
    $('question').value = lastQuestion;
    renderAnswer(lastQuestion);
  });
});
$('ask-form').addEventListener('submit', event => {
  event.preventDefault();
  lastQuestion = $('question').value.trim();
  if (lastQuestion) renderAnswer(lastQuestion);
});
$('reserves-form').addEventListener('submit', event => {
  event.preventDefault();
  const proposed = {regularBills: $('regular').value, irregularBuffer: $('irregular').value, emergencyBuffer: $('emergency').value};
  try {
    budgetCapacity(transactions, proposed);
    assumptions = proposed;
    $('reserve-error').textContent = '';
    renderAll();
  } catch (error) {
    $('reserve-error').textContent = `I cannot calculate that reserve: ${error.message}`;
  }
});
$('dataset-upload').addEventListener('change', async event => {
  const file = event.target.files?.[0];
  if (!file) return;
  const errorBox = $('upload-error');
  errorBox.textContent = '';
  if (file.size > 5_000_000) { errorBox.textContent = 'Choose a one-customer JSON export smaller than 5 MB.'; return; }
  try {
    const raw = JSON.parse(await file.text());
    const parsed = readTransactions(raw);
    spendingSummary(parsed);
    budgetCapacity(parsed, assumptions); // validate aggregates before replacing the active dataset
    transactions = parsed;
    $('dataset-label').textContent = `LOCAL FILE · ${transactions.length} ROWS · SOURCE UNVERIFIED`;
    $('question').value = '';
    lastQuestion = 'Where did my money go this month?';
    renderAll();
  } catch (error) {
    errorBox.textContent = `Import refused: ${error.message}`;
  } finally {
    event.target.value = '';
  }
});
$('import-button').addEventListener('keydown', event => {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    $('dataset-upload').click();
  }
});

renderAll();
