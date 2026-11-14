// Fictional demonstration only. No sponsor rows, accounts or personal data were copied.
// Dates and balances are internally consistent with the two example accounts.
export const syntheticRows = [
  ['DEMO-CHECK', '2026-10-20', 'SALARY', '2400.00', '3100.00', 'salary'],
  ['DEMO-CHECK', '2026-10-21', 'RENT', '-850.00', '2250.00', 'card'],
  ['DEMO-CHECK', '2026-10-23', 'GROCERIES', '-105.25', '2144.75', 'card'],
  ['DEMO-CHECK', '2026-11-01', 'SALARY', '2400.00', '4544.75', 'salary'],
  ['DEMO-CHECK', '2026-11-02', 'RENT', '-875.00', '3669.75', 'card'],
  ['DEMO-CHECK', '2026-11-03', 'GROCERIES', '-59.70', '3610.05', 'card'],
  ['DEMO-CHECK', '2026-11-05', 'RESTAURANTS', '-32.40', '3577.65', 'card'],
  ['DEMO-CHECK', '2026-11-06', 'TAXIS', '-12.50', '3565.15', 'card'],
  ['DEMO-CHECK', '2026-11-07', 'COFFEE', '-4.80', '3560.35', 'card'],
  ['DEMO-CHECK', '2026-11-08', 'RESTAURANTS', '5.40', '3565.75', 'refund'],
  ['DEMO-CHECK', '2026-11-09', 'ELECTRICITY', '-82.30', '3483.45', 'direct-debit'],
  ['DEMO-CHECK', '2026-11-10', 'INTERNAL_TRANSFER', '-150.00', '3333.45', 'internal-transfer'],
  ['DEMO-SAVE', '2026-11-10', 'INTERNAL_TRANSFER', '150.00', '650.00', 'internal-transfer'],
  ['DEMO-CHECK', '2026-11-11', 'HOME_REPAIRS', '-75.00', '3258.45', 'card'],
  ['DEMO-CHECK', '2026-11-12', 'OTHER_MYSTERY', '-7.20', '3251.25', 'card'],
  ['DEMO-CHECK', '2026-11-13', 'RESTAURANTS', '-23.80', '3227.45', 'card'],
].map(([bank_account_id, tx_date, category, tx_amount_eur, balance_after_eur, transaction_type], index) => ({
  customer_id: 'FICTIONAL_DEMO_001',
  bank_account_id, tx_date,
  tx_timestamp: `${tx_date}T12:00:00Z`, category,
  tx_amount_eur, balance_after_eur, transaction_type,
  merchant_id: null, mcc_code: null, sourceLine: index + 2,
}));
