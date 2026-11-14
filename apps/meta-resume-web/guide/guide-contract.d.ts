/** Local metadata and user assertions only; no private-host authorization. */
export type ViewReason = 'close-up' | 'side' | 'overview';
export type FrameSource = 'phone-camera' | 'selected-image' | 'demo';
export interface GuideBinding {
  sessionId: string; generation: number; taskId: string | null;
  taskRevision: number; memoryEpoch: number;
}
export interface GuideRequest {
  requestId: string; itemId: string; reason: ViewReason; createdAtMs: number;
  expiresAtMs: number; frameWatermark: number; binding: GuideBinding;
}
export interface GuideItem {
  id: string; name: string; place: string | null; packed: boolean;
  /** User-confirmed task history, never current physical presence. */
  packedAtMs: number | null; packedSource: 'user' | null;
  userConfirmed: boolean; previouslyPacked: boolean;
}
export interface GuideTask {
  id: string; title: string; mode: 'teach' | 'pack';
  status: 'active' | 'paused' | 'completed'; items: GuideItem[];
}
export interface GuideMemory {
  itemId: string; name: string; place: string; confirmedAtMs: number; version: number;
  frameSha256: string | null; viewReason: ViewReason | null;
  association: 'user-confirmed-photo' | 'user-corrected-metadata';
  physicalIdentityVerified: false; currentPresenceVerified: false;
}
export interface SelectedContextEntry {
  id: string; title: string; summary: string; observedAtMs: number;
  /** Handoff export time is never inferred to be original image capture time. */
  timeBasis: 'captured' | 'handoff-export' | 'user-note';
}
export interface SelectedContextEnvelope {
  schema: 'lens.selected-context/v1'; selectionId: string;
  source: 'screenshotcontext' | 'manual'; selectedByUser: true;
  entries: SelectedContextEntry[];
}
export interface HistoricalContext extends SelectedContextEntry {
  selectionId: string; source: 'screenshotcontext' | 'manual'; historical: true;
}
export interface GuideFrameInput {
  requestId: string; binding: GuideBinding; bytes: Uint8Array | ArrayBuffer;
  sha256: string; mimeType: 'image/jpeg' | 'image/png' | 'image/webp';
  capturedAtMs: number; sequence: number; source: FrameSource;
}
export interface GuideFrame extends Omit<GuideFrameInput, 'bytes' | 'source'> {
  source: 'phone-camera';
  byteLength: number; distinguishingViewConfirmed: false;
  physicalIdentityVerified: false; currentPresenceVerified: false; actionAuthorized: false;
}
export interface GuideSnapshot {
  schema: 'lens.guide-state/v1'; sessionId: string; generation: number; revision: number;
  taskRevision: number; memoryEpoch: number; consent: { memory: boolean; capture: boolean };
  task: GuideTask | null; memories: GuideMemory[]; pending: GuideRequest | null;
  acceptedFrame: GuideFrame | null; frameWatermark: number; selectedContext: HistoricalContext[];
  physicalIdentityVerified: false; currentPresenceVerified: false; actionAuthorized: false;
}
export type GuideResult =
  | { ok: true; state: GuideSnapshot; replayed?: boolean; request?: GuideRequest; expired?: boolean }
  | { ok: false; state: GuideSnapshot; error: { code: string } };
export interface GuideSession {
  snapshot(): GuideSnapshot;
  setConsent(consent: { memory: boolean; capture: boolean }): GuideResult;
  beginTask(task: { title: string; mode: 'teach' | 'pack'; items: { id: string; name: string }[] }): GuideResult;
  requestView(request: { itemId: string; reason: ViewReason }): GuideResult;
  acceptFrame(frame: GuideFrameInput): Promise<GuideResult>;
  confirmMemory(value: { requestId: string; itemId: string; name: string; place: string; confirmed: true }): GuideResult;
  correctMemory(value: { itemId: string; name: string; place: string; confirmed: true }): GuideResult;
  forgetMemory(value: { itemId: string }): GuideResult;
  forgetAll(): GuideResult;
  reset(): GuideResult;
  confirmPacked(value: { requestId: string; itemId: string; confirmed: true }): GuideResult;
  pause(): GuideResult;
  resume(): GuideResult;
  cancelRequest(): GuideResult;
  expire(value?: { requestId?: string }): GuideResult;
  importSelectedContext(value: SelectedContextEnvelope | string): GuideResult;
  /** UI must also enforce cross-tab storage ownership/tombstones. */
  exportState(value?: { expectedMemoryEpoch?: number }): string | null;
}
export interface GuideOptions { now?: () => number; id?: () => string; }
export declare function createGuideSession(options?: GuideOptions): GuideSession;
/** Throws an Error with code INVALID_SAVE for malformed metadata. Restores no capture/pending frame. */
export declare function restoreGuideSession(serialized: string, options?: GuideOptions): GuideSession;
export declare function parseGuideMetadata(serialized: string): unknown;
export declare function isSafeGuideContextText(value: unknown, limit?: number): boolean;
export declare const GUIDE_LIMITS: Readonly<{ maxItems: 10; maxSaveBytes: 32768; maxFrameBytes: 2000000; freshnessMs: 30000 }>;
