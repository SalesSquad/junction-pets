/** Build-controlled mount prefix, e.g. / for preview and /junction/ in Chibi. */
export function publicAsset(path:string):string {
  return `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`;
}
