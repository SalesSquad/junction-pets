export type PetSelection =
  | {kind: 'default'; slug: 'junction-mariadb'}
  | {kind: 'explicit'; slug: string}
  | {kind: 'invalid'};
export type PetChoice<T> = {pet: T | null; reason: null | 'invalid' | 'unknown' | 'filtered' | 'empty'};
export function readSelection(search: string): PetSelection;
export function resolveSelection<T extends {slug: string}>(
  all: readonly T[], filtered: readonly T[], selection: PetSelection
): PetChoice<T>;
export function petHref(currentHref: string, slug: string): string;
