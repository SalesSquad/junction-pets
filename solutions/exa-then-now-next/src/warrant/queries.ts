/**
 * Citation-completion queries. Exa's model was trained to predict the link that follows a
 * passage, so the compiler writes the sentence a careful author would write just before
 * citing the source and lets Exa complete the citation. Templates make the queries
 * reproducible, so a receiver can replay them and compare result overlap.
 */

export interface PremiseSpec {
  /** One factual sentence in the register of the source, naming the instrument and the rule. */
  premise: string;
  /** e.g. "Regulation (EC) No 261/2004" */
  instrument: string;
  /** e.g. "regulation", "directive", "Act" */
  sourceKind: string;
  /** e.g. "An air carrier is not obliged to pay compensation" — the obligation and who could escape it. */
  exemptionLead?: string;
}

export interface CompiledQueries {
  support: string;
  rebuttal: string;
  temporal: string;
}

export function citationQueries(p: PremiseSpec): CompiledQueries {
  return {
    support: `${p.premise} The official text of the ${p.sourceKind}:`,
    rebuttal: `${p.exemptionLead ?? `The obligations in ${p.instrument} do not apply`} in certain exceptional cases set out in ${p.instrument}. The court defined these exceptions in its judgment:`,
    temporal: `${p.instrument} has been amended or replaced by new legislation. The new rules apply from:`,
  };
}

/** Extract "shall apply from <date>" style application dates from fetched legal text. */
export function applicationDate(text: string): string | null {
  const months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
  const m = text.match(/(?:shall|will)\s+apply\s+from\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})/i);
  if (!m) return null;
  const month = months.indexOf(m[2]!.toLowerCase());
  if (month < 0) return null;
  return `${m[3]}-${String(month + 1).padStart(2, "0")}-${m[1]!.padStart(2, "0")}`;
}
