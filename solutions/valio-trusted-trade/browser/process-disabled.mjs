/** Only the optional server OCR spawn boundary is unsupported; scanning parsers stay unchanged. */
export function spawn(){throw Object.assign(new Error('Server OCR is unavailable in the browser-local app. Use the original runtime.'),{code:'SERVER_OCR_UNAVAILABLE'});}
