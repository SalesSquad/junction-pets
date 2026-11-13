import type {Catalogue, Pet} from './types';

type Tool = {
  name: string;
  title: string;
  description: string;
  inputSchema: object;
  annotations: {readOnlyHint: boolean; untrustedContentHint: boolean};
  execute(input: unknown): unknown | Promise<unknown>;
};
type ModelContext = {registerTool(tool: Tool, options: {signal: AbortSignal}): void | Promise<void>};
type CatalogDocument = {modelContext?: ModelContext};
type Registration = {supported: boolean; dispose(): void};
type Options = {
  document?: CatalogDocument;
  catalogue: Catalogue;
  getSelectedSlug(): string | null;
  selectCompanion(slug: string): Promise<void>;
  onError?(code: string): void;
};

const registrations = new WeakMap<ModelContext, Registration>();
const slugPattern = /^junction-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const roles = ['all', 'challenge', 'technology', 'main', 'collaborator'];

function inputObject(value: unknown, allowed: string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || ![Object.prototype, null].includes(Object.getPrototypeOf(value))
    || Reflect.ownKeys(value).some(key => typeof key !== 'string' || !allowed.includes(key))) {
    throw new Error('invalid_input');
  }
  return value as Record<string, unknown>;
}

function petSummary(pet: Pet) {
  return {
    slug: pet.slug,
    name: pet.displayName,
    company: pet.company.name,
    role: pet.company.role,
    version: pet.version,
    declaredCapabilityCount: pet.capabilities.length,
    taskExecution: 'unavailable_in_catalog',
  };
}

/** Public catalog tools only. This module never imports the private ops or Node task registry. */
export function registerCatalogTools(options: Options): Registration {
  const context = options.document?.modelContext;
  if (!context || typeof context.registerTool !== 'function') return {supported: false, dispose() {}};
  // React retries and repeated setup must not register duplicate page-scoped tools.
  if (registrations.has(context)) return {supported: true, dispose() {}};

  const lifecycle = new AbortController();
  const registration = {
    supported: true,
    dispose() {
      lifecycle.abort();
      if (registrations.get(context) === registration) registrations.delete(context);
    },
  };
  registrations.set(context, registration);
  const requireActive = () => {
    if (lifecycle.signal.aborted) throw new Error('catalog_tools_inactive');
  };
  const findPet = (value: unknown) => {
    const input = inputObject(value, ['slug']);
    if (typeof input.slug !== 'string' || input.slug.length > 100 || !slugPattern.test(input.slug)) throw new Error('invalid_input');
    const pet = options.catalogue.pets.find(p => p.slug === input.slug);
    if (!pet) throw new Error('companion_not_found');
    return pet;
  };
  const slugSchema = {
    type: 'object', properties: {slug: {type: 'string', pattern: '^junction-[a-z0-9]+(?:-[a-z0-9]+)*$', maxLength: 100}},
    required: ['slug'], additionalProperties: false,
  };
  const tools: Tool[] = [
    {
      name: 'list_junction_companions',
      title: 'List Junction companions',
      description: 'Read the public companion collection, optionally filtered by company/name and partner role. Profiles describe authored capabilities; task execution and adoption are unavailable here.',
      inputSchema: {
        type: 'object', properties: {query: {type: 'string', maxLength: 120}, role: {type: 'string', enum: roles}, limit: {type: 'integer', minimum: 1, maximum: 34}},
        additionalProperties: false,
      },
      annotations: {readOnlyHint: true, untrustedContentHint: true},
      execute(value) {
        requireActive();
        const input = inputObject(value, ['query', 'role', 'limit']);
        if ((input.query !== undefined && (typeof input.query !== 'string' || input.query.length > 120))
          || (input.role !== undefined && (typeof input.role !== 'string' || !roles.includes(input.role)))
          || (input.limit !== undefined && (typeof input.limit !== 'number' || !Number.isInteger(input.limit) || input.limit < 1 || input.limit > 34))) throw new Error('invalid_input');
        const query = ((input.query as string | undefined) ?? '').trim().normalize('NFKD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('en');
        const found = options.catalogue.pets.filter(pet =>
          (input.role === undefined || input.role === 'all' || pet.company.role === input.role)
          && `${pet.company.name} ${pet.displayName} ${pet.tagline}`.normalize('NFKD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('en').includes(query));
        return {companions: found.slice(0, (input.limit as number | undefined) ?? 34).map(petSummary), total: found.length, selectedSlug: options.getSelectedSlug()};
      },
    },
    {
      name: 'read_junction_companion',
      title: 'Read companion capabilities',
      description: 'Read one public companion profile, declared capabilities and cited sources. These are authored profile descriptions, not executable tools, live connections or company endorsement.',
      inputSchema: slugSchema,
      annotations: {readOnlyHint: true, untrustedContentHint: true},
      execute(value) {
        requireActive();
        const pet = findPet(value);
        return {
          ...petSummary(pet), introduction: pet.introduction,
          capabilities: pet.capabilities.map(capability => ({id: capability.id, title: capability.title, description: capability.description, requiresConnection: capability.requiresConnection, execution: 'unavailable_in_catalog'})),
          sources: pet.sources.map(source => ({title: source.title, url: source.url, checkedAt: source.checkedAt})),
          companyEndorsed: false,
        };
      },
    },
    {
      name: 'select_junction_companion',
      title: 'Select a companion profile',
      description: 'Select and visibly open an existing companion profile in this catalog, clearing filters. Completes only catalog navigation; does not adopt, activate, connect or execute the companion.',
      inputSchema: slugSchema,
      annotations: {readOnlyHint: false, untrustedContentHint: true},
      async execute(value) {
        requireActive();
        const pet = findPet(value);
        await options.selectCompanion(pet.slug);
        requireActive();
        if (options.getSelectedSlug() !== pet.slug) throw new Error('selection_not_completed');
        return {slug: pet.slug, selected: true, profileVisible: true, taskExecution: 'unavailable_in_catalog'};
      },
    },
  ];
  const failed = () => {
    registration.dispose();
    options.onError?.('catalog_tool_registration_failed');
  };
  for (const tool of tools) {
    if (lifecycle.signal.aborted) break;
    try { void Promise.resolve(context.registerTool(tool, {signal: lifecycle.signal})).catch(failed); }
    catch { failed(); }
  }
  return registration;
}
