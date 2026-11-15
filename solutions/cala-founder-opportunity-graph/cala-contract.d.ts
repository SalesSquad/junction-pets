export type EntityRef = Readonly<{id:string; url:string}>;
export type Discovery = {operation:'entity_search'; query:string} | {operation:'entity_lookup'; entity:EntityRef};
export type Introspection = {operation:'entity_introspection'; entity:EntityRef; discoveryReceipt:string};
export type Retrieval = {operation:'entity_retrieval'; entity:EntityRef; introspectionReceipt:string; fields:readonly string[]};
export type Source = {id:string; url:string; publishedAt:string|null; originId:string; excerpt:string};
export type FundingEvidence = {entity:EntityRef; issuer:EntityRef; economicRoundId:string|null; role:'INVESTOR'|'ISSUER'|'UNKNOWN'; lead:boolean|null; eventDate:string|null; amount:number|null; source:Source};
export type HostReadGrant = {hostVerified:true; allowedEntityIds:readonly string[]; expiresAt:string; secretStoreRef:string};
export declare const CALA_CONTRACT: Readonly<{version:string; sequence:readonly string[]; limits:Readonly<{timeoutMs:5000;maxResponseBytes:262144;maxEntities:25}>;authority:string}>;
export declare function requestCala(): Promise<{status:'REFUSED';reason:string;sequence:readonly string[];limits:typeof CALA_CONTRACT.limits}>;
