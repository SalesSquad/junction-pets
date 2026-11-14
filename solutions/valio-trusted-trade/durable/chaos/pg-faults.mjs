/**
 * Node-postgres emits EventEmitter `error` on checked-out Client instances
 * when their server disappears. A Pool idle-error listener does not cover
 * a checked-out transaction. Guard BOTH event sources; never mistake an
 * unrelated SQL failure for an authorized SIGKILL disconnect.
 */
const EXPECTED_CODES=new Set(['57P01','57P02','57P03','08000','08001','08003',
  '08006','08P01','ECONNRESET','EPIPE','ECONNREFUSED','ENOENT']);
const EXPECTED_MESSAGES=[
  /connection terminated unexpectedly/i,
  /connection terminated/i,
  /server closed the connection unexpectedly/i,
  /terminating connection due to administrator command/i,
  /read ECONNRESET/i,
  /write EPIPE/i
];

export function isExpectedCrashDisconnect(error){
  const code=String(error?.code||'');
  const message=String(error?.message||'');
  return EXPECTED_CODES.has(code)||EXPECTED_MESSAGES.some(re=>re.test(message));
}

export function guardPgPool(pool,{expectedCrash=()=>false,onFault=()=>{}}={}){
  if(!pool||typeof pool.on!=='function')throw new TypeError('Pool must expose EventEmitter on().');
  const listen=(origin,error)=>{
    const fault={origin,code:String(error?.code||'UNKNOWN'),
      expected:Boolean(expectedCrash())&&isExpectedCrashDisconnect(error)};
    onFault(fault);
  };
  // Required to handle errors on checked-out Client while a transaction is
  // awaiting its parameterized query. pg-pool removes its idle listener there.
  pool.on('connect',client=>client.on('error',err=>listen('client',err)));
  // Required for idle clients; pg-pool forwards those to Pool's error event.
  pool.on('error',err=>listen('pool',err));
  return pool;
}
