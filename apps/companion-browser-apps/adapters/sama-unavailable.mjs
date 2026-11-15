// These endpoints require services and credentials that are not part of this
// static research demonstration. Never send note or claim data to another API.
export async function unavailable() {
  return new Response(JSON.stringify({error:'Live model and source verification are unavailable in this browser demonstration.'}),{
    status:503,headers:{'Content-Type':'application/json; charset=utf-8'}
  });
}
