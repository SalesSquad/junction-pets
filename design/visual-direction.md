# Junction catalogue visual direction

Work ID: JUNCTION-PETS-20261111. The implementation follows the generated
`catalog-concept.png` reference. Mascots are newly generated original characters;
they do not claim to recover the inaccessible previous artwork or represent an
official company endorsement.

## Composition and design tokens

- Background `#fafaf8`, white artwork, ink `#171c1c`, secondary `#626b6c`,
  separators `#dce2df`, teal `#176b63` and pale selected teal `#e5f1ed`.
- DM Sans with a system sans fallback; deliberate 16 px controls, 20 px list labels,
  56–64 px page title, 36–44 px selected-pet tagline, 24 px section titles.
- Header with Chibi identity, Junction and My Chibi; single wide catalogue title.
- Open two-column composition: search/filter/company list left; art + pet story,
  capability rows, starter prompts and official sources right.
- Under 850 px, use the same sections in one column with a labelled native company
  selector. No hidden sideways-scrolling primary content.
- A single 6×6 atlas supplies characters using CSS background positions. No raster
  editing, rerendering, slicing or inferred original art. Stable artIndex 0–33 is
  bound to the verified roster. Last two cells are unused.
- Thin line icons are code-native, same 1.8 px stroke and 20 px view box.
- Motion: short state transitions only; respect reduced motion.

## Visible copy and functional additions

Primary copy: `chibi.pet`, `Junction`, `My Chibi`, `Junction companions`,
`Meet the companies. Find your companion.`, `Search companies`, `All`,
`Challenge`, `Technology`, `More`, `Meet your pet`, `Show QR code`,
`What we can work on`, `Start with a question`, `Official sources`.

Pet names, capability text and prompts come from verified package content. The
necessary package-download links and honest release status are added below the
primary controls; these are intentional functional additions to the reference.
The QR dialog is generated from the validated host URL, never decorative art.
The catalogue does not create an account, adopt, activate or simulate a reply.

## Asset production

Built-in Image Gen created `catalog-concept.png` and
`apps/catalog/public/assets/company-mascots.png` on 11 November 2026. Prompts are
retained in `generation-prompts.json`. The asset source is the output bytes, copied
without changing pixels. Character identity is independent original artwork.
