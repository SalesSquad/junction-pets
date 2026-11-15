/**
 * Synthetic EUR wallet rail for the hackathon. No bank account, PSP, IBAN,
 * external transfer or production ledger is connected. All balances are reset
 * when the demo process restarts. BankMatch remains the canonical finance
 * integration candidate; this fixture deliberately has no production API.
 */
import { digest } from './trust-envelope.mjs';

export const DEMO_STARTING_FUNDS_CENTS = 250_000;
const BUYER_WALLET = 'demo:buyer:wallet';
const supplierWallet = (supplierId) => `demo:supplier:${supplierId}:wallet`;

export function createSyntheticSettlement({ getOrder, TradeError, record, clock }) {
  const balances = new Map([[BUYER_WALLET, DEMO_STARTING_FUNDS_CENTS]]);
  const approvals = new Map();
  const transfers = new Map();
  const idempotencyKeys = new Map();
  const journal = [];
  let transferSerial = 0;

  const fail = (code, reason, status = 409) => { throw new TradeError(code, reason, status); };
  const matchOrder = (orderId, buyerId) => {
    const order = getOrder(orderId);
    if (buyerId !== order.buyerId) fail('BUYER_MISMATCH', 'Payment must belong to the committed demo buyer.', 403);
    if (!order.paymentEligible || !order.verifiedQuoteBodyDigest) {
      fail('SIGNED_TRADE_REQUIRED', 'A valid signed portfolio handshake must precede any synthetic payment.', 403);
    }
    return order;
  };
  const allocations = (order) => {
    const suppliers = new Map();
    for (const line of order.lines) {
      const supplierId = line.supplierId ?? 'supplier-demo';
      const amount = line.totalCents;
      if (typeof supplierId !== 'string' || !/^[a-z0-9-]{1,64}$/.test(supplierId) ||
          !Number.isSafeInteger(amount) || amount <= 0) fail('INVALID_ORDER_ALLOCATION', 'Order contains invalid server-owned supplier terms.');
      suppliers.set(supplierId, (suppliers.get(supplierId) ?? 0) + amount);
    }
    for (const [field, supplierId] of [['deliveryFeeCents', 'fictional-delivery-fee'], ['taxCents', 'fictional-tax-holding']]) {
      const amount = order.costBreakdown?.[field] ?? 0;
      if (!Number.isSafeInteger(amount) || amount < 0) fail('INVALID_ORDER_ALLOCATION', 'Declared charges must be nonnegative integer cents.');
      if (amount) suppliers.set(supplierId, (suppliers.get(supplierId) ?? 0) + amount);
    }
    const sum = [...suppliers.values()].reduce((total, amount) => total + amount, 0);
    if (!Number.isSafeInteger(sum) || sum !== order.totalCents) fail('INVALID_ORDER_ALLOCATION', 'Supplier allocations must equal the immutable order amount.');
    return [...suppliers].map(([supplierId, amountCents]) => ({ supplierId, amountCents }));
  };
  const post = ({ orderId, transferId, type, debitAccount, creditAccount, amountCents }) => {
    if (!Number.isSafeInteger(amountCents) || amountCents <= 0 || debitAccount === creditAccount) {
      fail('INVALID_JOURNAL', 'The demo journal needs one balanced positive debit and credit.');
    }
    const available = balances.get(debitAccount) ?? 0;
    if (available < amountCents) fail('INSUFFICIENT_DEMO_FUNDS', 'Fictional wallet has insufficient EUR cents.');
    balances.set(debitAccount, available - amountCents);
    balances.set(creditAccount, (balances.get(creditAccount) ?? 0) + amountCents);
    const entry = { id: `J-DEMO-${String(journal.length + 1).padStart(4, '0')}`, orderId,
      transferId, type, debitAccount, creditAccount, debitCents: amountCents,
      creditCents: amountCents, currency: 'EUR', at: new Date(clock()).toISOString(),
      prevHash: journal.at(-1)?.hash ?? 'GENESIS' };
    entry.hash = digest(entry);
    journal.push(entry);
    return entry.id;
  };
  const snapshot = () => ({ mode: 'SYNTHETIC_IN_MEMORY_NO_BANK_TRANSFER',
    currency: 'EUR', initialBuyerFundsCents: DEMO_STARTING_FUNDS_CENTS,
    buyerBalanceCents: balances.get(BUYER_WALLET),
    suppliers: [...balances].filter(([account]) => account.startsWith('demo:supplier:'))
      .map(([account, balanceCents]) => ({ account, balanceCents })) });
  const transferProposal = (order) => {
    const body = { orderId: order.id, amountCents: order.totalCents, currency: 'EUR',
      allocations: allocations(order), signedQuoteBodyDigest: order.verifiedQuoteBodyDigest,
      rail: 'IN_MEMORY_NO_BANK_OR_PSP' };
    return { ...body, digest: digest(body) };
  };
  const payment = (orderId, buyerId) => {
    const order = matchOrder(orderId, buyerId);
    return { proposal: transferProposal(order), approval: structuredClone(approvals.get(orderId) ?? null),
      transfer: structuredClone(transfers.get(orderId) ?? null), wallet: snapshot() };
  };
  const decidePayment = ({ orderId, buyerId, decision, proposalDigest, ...extra } = {}) => {
    if (Object.keys(extra).length) fail('PAYMENT_TERMS_FORBIDDEN', 'Only orderId, buyerId, decision and proposalDigest can authorize fictional payment.', 400);
    const order = matchOrder(orderId, buyerId);
    if (order.status !== 'SIMULATED_COMMITTED') fail('ORDER_NOT_PAYABLE', 'Only active simulated orders may be paid.');
    if (!['approve', 'reject'].includes(decision)) fail('INVALID_DECISION', 'Approve or reject this fictional payment.', 400);
    const proposal = transferProposal(order);
    if (typeof proposalDigest !== 'string' || proposalDigest !== proposal.digest) {
      fail('PAYMENT_TERMS_STALE', 'Fictional payment approval must bind the exact order, suppliers and EUR cents.');
    }
    const existing = approvals.get(order.id);
    if (existing) {
      if (existing.decision !== decision) fail('PAYMENT_DECISION_FINAL', 'Payment authorization cannot be reversed without a new order.');
      return payment(order.id, buyerId);
    }
    const approval = { orderId, decision, amountCents: order.totalCents, currency: 'EUR', proposalDigest,
      at: new Date(clock()).toISOString(), identity: 'UNAUTHENTICATED_DEMO_CLICK' };
    approvals.set(order.id, approval);
    record('DEMO_PAYMENT_DECISION', { orderId, decision, amountCents: order.totalCents,
      proposalDigest, mode: approval.identity });
    return payment(order.id, buyerId);
  };
  const settle = ({ orderId, buyerId, idempotencyKey, ...extra } = {}) => {
    if (Object.keys(extra).length) fail('PAYMENT_TERMS_FORBIDDEN', 'Transfer amount and beneficiaries are fixed by the server-owned order.', 400);
    if (typeof idempotencyKey !== 'string' || !/^[A-Za-z0-9_-]{10,80}$/.test(idempotencyKey)) {
      fail('INVALID_IDEMPOTENCY_KEY', 'A stable 10–80 character payment key is required.', 400);
    }
    const order = matchOrder(orderId, buyerId);
    const reused = idempotencyKeys.get(idempotencyKey);
    if (reused) {
      if (reused !== orderId) fail('IDEMPOTENCY_CONFLICT', 'That payment key belongs to another order.');
      return { ...payment(orderId, buyerId), idempotentReplay: true };
    }
    if (order.status !== 'SIMULATED_COMMITTED') fail('ORDER_NOT_PAYABLE', 'Canceled orders cannot transfer fictional money.');
    if (approvals.get(orderId)?.decision !== 'approve' ||
        approvals.get(orderId)?.proposalDigest !== transferProposal(order).digest) {
      fail('PAYMENT_APPROVAL_REQUIRED', 'A separate exact-proposal fictional payment approval is required.', 403);
    }
    if (transfers.has(orderId)) fail('PAYMENT_ALREADY_SETTLED', 'An order can transfer simulated EUR only once.');
    const split = allocations(order);
    if ((balances.get(BUYER_WALLET) ?? 0) < order.totalCents) fail('INSUFFICIENT_DEMO_FUNDS', 'Fictional buyer wallet has insufficient funds.');
    const transferId = `PAY-DEMO-${String(++transferSerial).padStart(4, '0')}`;
    const entryIds = split.map(({ supplierId, amountCents }) => post({ orderId, transferId,
      type: 'SIMULATED_PAYMENT', debitAccount: BUYER_WALLET,
      creditAccount: supplierWallet(supplierId), amountCents }));
    const transfer = { id: transferId, orderId, amountCents: order.totalCents, currency: 'EUR',
      allocations: split, journalEntryIds: entryIds, status: 'SIMULATED_SETTLED',
      at: new Date(clock()).toISOString(), rail: 'IN_MEMORY_NO_BANK_OR_PSP' };
    transfers.set(orderId, transfer);
    idempotencyKeys.set(idempotencyKey, orderId);
    record('DEMO_MONEY_TRANSFER_SETTLED', { orderId, transferId, amountCents: order.totalCents,
      allocations: split, journalEntryIds: entryIds, mode: transfer.rail });
    return { ...payment(orderId, buyerId), idempotentReplay: false };
  };
  const refundForCancellation = (order) => {
    const transfer = transfers.get(order.id);
    if (!transfer || transfer.status === 'SIMULATED_REFUNDED') return;
    const entryIds = transfer.allocations.map(({ supplierId, amountCents }) => post({
      orderId: order.id, transferId: transfer.id, type: 'SIMULATED_REVERSAL',
      debitAccount: supplierWallet(supplierId), creditAccount: BUYER_WALLET, amountCents }));
    transfer.status = 'SIMULATED_REFUNDED';
    transfer.refundJournalEntryIds = entryIds;
    record('DEMO_PAYMENT_REVERSED', { orderId: order.id, transferId: transfer.id,
      amountCents: transfer.amountCents, journalEntryIds: entryIds });
  };
  const verify = () => {
    const simulated = new Map([[BUYER_WALLET, DEMO_STARTING_FUNDS_CENTS]]);
    let prevHash = 'GENESIS', totalDebitCents = 0, totalCreditCents = 0;
    for (const [index, entry] of journal.entries()) {
      const { hash, ...unsigned } = entry;
      if (entry.prevHash !== prevHash || hash !== digest(unsigned) ||
          !Number.isSafeInteger(entry.debitCents) || entry.debitCents <= 0 ||
          entry.creditCents !== entry.debitCents || entry.debitAccount === entry.creditAccount) {
        return { valid: false, firstInvalidIndex: index };
      }
      const debitBalance = simulated.get(entry.debitAccount) ?? 0;
      if (debitBalance < entry.debitCents) return { valid: false, firstInvalidIndex: index };
      simulated.set(entry.debitAccount, debitBalance - entry.debitCents);
      simulated.set(entry.creditAccount, (simulated.get(entry.creditAccount) ?? 0) + entry.creditCents);
      totalDebitCents += entry.debitCents;
      totalCreditCents += entry.creditCents;
      prevHash = hash;
    }
    const same = [...balances].every(([key, value]) => simulated.get(key) === value) &&
      [...simulated].every(([key, value]) => balances.get(key) === value);
    return { valid: same && totalDebitCents === totalCreditCents,
      journalEntries: journal.length, totalDebitCents, totalCreditCents,
      headDigest: prevHash, mode: 'SYNTHETIC_IN_MEMORY_NOT_EXTERNAL_ANCHORED' };
  };
  return Object.freeze({ payment, wallet: snapshot, approve: decidePayment, settle,
    refundForCancellation, journal: () => structuredClone(journal), verify });
}
