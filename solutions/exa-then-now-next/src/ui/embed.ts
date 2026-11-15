/**
 * The butler shown inside another page. The Chibi.pet companion collection opens it in the Exa companion's app
 * view: a frame on another origin, marked with ?embed=collection. The host already shows the name and a close
 * button, so the embedded page drops its own title (styles.css, html.embed).
 *
 * A frame on another origin does not get the clipboard or the microphone unless the host delegates them, and
 * Chibi's app frame delegates nothing. Copying falls back to the selection command, which needs no delegation;
 * dictation cannot work there, so its note says to open the butler in its own tab.
 */
export function isEmbedded(search: string, win: { self: unknown; top: unknown }): boolean {
  if (new URLSearchParams(search).get("embed") === "collection") return true;
  try {
    return win.self !== win.top;
  } catch {
    return true; // reading `top` can throw in a sandboxed frame
  }
}

export const embedded = typeof window !== "undefined" && isEmbedded(location.search, window);

/** Why dictation failed, in words that fit where the page is shown. */
export const dictationNote = (error: string | undefined, inFrame = embedded): string | undefined =>
  error && inFrame && /microphone|not-allowed|service-not-allowed/i.test(error)
    ? "the microphone is not available inside this frame: open the butler in its own tab to dictate"
    : error;

/** Copy text, also where the async clipboard is not delegated (a frame on another origin). */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* not permitted here: use the selection command */
  }
  const box = document.createElement("textarea");
  box.value = text;
  box.setAttribute("readonly", "");
  box.style.cssText = "position:fixed;top:0;left:0;opacity:0";
  document.body.append(box);
  box.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  box.remove();
  return ok;
}
