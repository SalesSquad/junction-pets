export type CompanyRole = 'challenge' | 'technology' | 'main' | 'collaborator';
export type Pet = {
  schemaVersion: 1; id: string; slug: string; version: string;
  displayName: string; company: {name:string;slug:string;role:CompanyRole;website:string};
  tagline:string; introduction:string; welcome:string; accent:string; artIndex:number;
  capabilities:Array<{id:string;title:string;description:string;kind:string;inputs:string[];outputs:string[];requiresConnection:boolean}>;
  starterPrompts:string[];
  sources:Array<{id:string;title:string;url:string;publisher:string;checkedAt:string;summary:string}>;
  sourceEvidence:{roster:string;roleVerified:boolean;notes:string};
  availability:{content:string;runtime:string;companyEndorsed:boolean};
};
export type Catalogue = {schemaVersion:1;collection:{id:string;title:string;sourceRevision:string;contentSha256:string};pets:Pet[]};
export type HostConfig = {canonicalOrigin:string;locale:string;runtimeStatus:'unverified'|'verified';publishedSlugs:string[];verifiedAt:string|null};
export type RoleFilter = 'all' | 'challenge' | 'technology' | 'more';
