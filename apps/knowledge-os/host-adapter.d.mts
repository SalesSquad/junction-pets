export type Module = 'knowledge_os' | 'graphify' | 'dam' | 'repo_control';
export type Scope = {actorId: string; projectId: string};
export type Dataset = {projectId: string; module: Module; digest: string; observedAt: string; coverage: 'partial' | 'complete_for_declared_source'};
export type HostDependencies = {
  /** Host must derive this from its trusted owner-private authentication, never request JSON or a browser flag. */
  authorize?: (request: Request) => Promise<{actorId: string; audience: 'owner-private'} | null>;
  readProject?: (scope: Scope) => Promise<unknown>;
  /** Explicit immutable selectors from the existing Node's source manifest; no implicit latest selection. */
  listDatasets?: (scope: Scope) => Promise<Dataset[]>;
  searchDataset?: (input: Scope & {module: Module; digest: string; query: string; limit: number}) => Promise<unknown>;
};
export const KNOWLEDGE_MODULES: readonly Module[];
export function createKnowledgeAppHandler(dependencies?: HostDependencies): (request: Request) => Promise<Response>;
