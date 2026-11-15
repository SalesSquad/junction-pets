/** Disposable child used only by persistent-http.test.mjs. Never targets an existing service. */
import { writeFileSync } from 'node:fs';
import { createPersistentTradeServer } from '../../src/server.mjs';

if (process.env.VALIO_PERSISTENT_TEST_CHILD === '1') {
  const [stateFile, markerFile, stopAt] = process.argv.slice(2);
  const server = createPersistentTradeServer({ stateFile, afterCommitBeforeRespond(request) {
    const order = stopAt === 'order' && request.method === 'POST' && request.url === '/api/orders';
    const payment = stopAt === 'payment' && request.method === 'POST' && request.url?.endsWith('/settlement');
    if (order || payment) {
      writeFileSync(markerFile, 'DURABLE_COMMIT_BEFORE_HTTP_ACK', { mode: 0o600, flag: 'wx' });
      // Parent observes this task-owned marker and SIGKILLs this exact child PID.
      // No HTTP response is flushed while this synchronous fault hook is blocked.
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 30000);
      throw Error('Lost-ACK child was not terminated within its bounded test window');
    }
  } });
  server.listen(0, '127.0.0.1', () => process.send?.({ type: 'ready', port: server.address().port }));
}
