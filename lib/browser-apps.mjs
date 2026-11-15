import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {agentCatalog, checkSolutions} from '../scripts/solution-workspace.mjs';

// An app is a slice of an existing solution, attached to one of its real pets.
// App names (for example Banker) do not create new companion identities.
export function validateAppBindings(catalog, pets, solutions) {
  if (catalog?.schemaVersion !== 1 || !Array.isArray(catalog.apps)) throw new Error('Invalid app catalog');
  const knownPets = new Map(pets.map(pet => [pet.slug, pet]));
  const knownSolutions = new Map(solutions.map(solution => [solution.id, solution]));
  for (const app of catalog.apps) {
    const pet = knownPets.get(app?.petSlug);
    if (!pet) throw new Error(`Unknown app pet: ${app?.petSlug}`);
    const solution = knownSolutions.get(app.solution);
    if (!solution) throw new Error(`Unknown app solution: ${app.solution}`);
    if (!solution.agentIds.includes(pet.id)) throw new Error(`App pet ${pet.slug} is not selected by solution ${solution.id}`);
  }
  return catalog.apps;
}

export async function loadBrowserApps(repo) {
  const [catalog, pets, solutions] = await Promise.all([
    readFile(join(repo, 'apps/companion-browser-apps/catalog.json'), 'utf8').then(JSON.parse),
    agentCatalog(repo), checkSolutions(repo),
  ]);
  return validateAppBindings(catalog, pets, solutions);
}
