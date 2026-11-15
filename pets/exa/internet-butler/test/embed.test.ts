import { test } from "node:test";
import assert from "node:assert/strict";
import { dictationNote, isEmbedded } from "../src/ui/embed.ts";

test("embedded: the marker in the address, or a page that is not its own top window", () => {
  const top = {};
  assert.equal(isEmbedded("?embed=collection", { self: top, top }), true);
  assert.equal(isEmbedded("?q=late+flight&run=1", { self: top, top }), false);
  assert.equal(isEmbedded("", { self: {}, top }), true);
  assert.equal(isEmbedded("", { self: top, get top(): unknown { throw new Error("blocked"); } }), true);
});

test("dictation note: inside a frame the microphone refusal says where dictation works", () => {
  assert.match(dictationNote("microphone permission was not given", true)!, /own tab/);
  assert.equal(dictationNote("microphone permission was not given", false), "microphone permission was not given");
  assert.equal(dictationNote("no-speech", true), "no-speech");
  assert.equal(dictationNote(undefined, true), undefined);
});
