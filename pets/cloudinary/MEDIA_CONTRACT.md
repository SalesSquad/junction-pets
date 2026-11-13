# Offline responsive-media plan

`planResponsiveMedia(jsonText)` in `responsive-media.mjs` checks a supplied,
fictional image specification and returns a deterministic plan. It is **not** a
Cloudinary API client, transformation-URL generator, image editor or proof of
delivery. The allowlists below are this example's policy, not claims about
Cloudinary product limits or supported syntax.

Input must be a JSON string of at most 16,384 JavaScript string code units. A
JavaScript object, accessor, function or Proxy is not accepted. Normal JSON
parsing semantics apply; callers should serialize a single unambiguous record.
Every object rejects unknown fields and requires all documented fields:

- Root: `asset`, `variants`.
- Asset: `id`, `width`, `height`, `visibility`, `decorative`, `alt`, `metadata`.
  ID is a local `[a-z][a-z0-9-]{0,63}` label, never a URL or path. Width/height
  are integer pixels from 1 through 16,384. Visibility must be exactly `public`.
  Decorative must be a boolean. Decorative images require empty alt text;
  meaningful images require nonblank alt text, at most 500 code units.
- Metadata: only `credit`, a string of at most 200 code units. Alt/credit reject
  ASCII control characters. These labels must already be public and redacted;
  the checker **cannot identify secrets embedded inside allowed text values**.
  Unknown metadata fields, EXIF, GPS, signed URLs and account information are
  rejected instead of being passed through. Declared visibility and credit are
  unverified assertions, never authorization, license or authenticity proof.
- Variants: 1–18 records, each exactly `{width, format, quality}`. Width belongs
  to `[160,320,640,960,1280,1920]`, format to `avif|webp|jpeg`, quality is an
  integer 1–100. No width may exceed the supplied source width. Duplicate
  width/format pairs are rejected, including pairs with different quality.

Output height is the aspect-ratio-preserving nearest integer pixel (at least
one); plans exceeding 4,096 output pixels vertically are rejected. Only
`contain` is planned: no implicit crop, orientation change, upscaling or URL.
Variants sort by numeric width then ASCII format. Only supplied alt/credit
appear as public metadata. Every plan says `status: planned` and explicitly
retains `transformationExecuted`, `deliveryVerified`, `pixelsInspected` and
`rightsVerified` as false. Unknown fields attempting to override those flags
are rejected. Invalid input throws `TypeError` with a generic message that
does not echo supplied metadata. Output is data, not HTML; consumers must escape
it appropriately. A valid plan does not establish visual quality or accessibility.

Run `node --test tests/pet-cloudinary.test.mjs`. The example
`examples/responsive-media.json` contains invented data. No source image is
downloaded or generated and no model eval, host or provider is invoked.

Next development owner: `junction-dev-cloudinary`. After independent source
review, propose a separate fixture-backed comparison of expected versus
observed image dimensions and metadata. Keep observed results untrusted until
a separately authorized host binds actual artifacts and receipts. No live
transformation or provider spending is authorized by this document.
