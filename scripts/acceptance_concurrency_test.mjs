import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { healthRequest, measure, summarize } from './acceptance-concurrency.mjs';

async function server(handler) {
  const instance = http.createServer(handler);
  await new Promise(resolve => instance.listen(0, '127.0.0.1', resolve));
  return instance;
}
function close(instance) { return new Promise(resolve => instance.close(resolve)); }

test('each batch creates six new connections, and failures are counted', async () => {
  let active = 0, maximum = 0;
  const sockets = new Set();
  const instance = await server((request, response) => {
    assert.equal(request.headers.connection, 'close');
    sockets.add(request.socket.remotePort);
    maximum = Math.max(maximum, ++active);
    setTimeout(() => { active--; response.end('{"status":"healthy"}'); }, 10);
  });
  try {
    const result = await measure(instance.address().port, { serial: 3, batches: 2, width: 6, deadlineMs: 1000 });
    assert.equal(result.sequential.counts.success, 3);
    assert.equal(result.concurrent.counts.success, 12);
    assert.equal(sockets.size, 15);
    assert.equal(maximum, 6);
    assert.deepEqual(summarize([{category:'refused'},{category:'timeout'},{category:'otherError'},{category:'httpError'}]), {success:0,refused:1,otherError:1,timeout:1,httpError:1});
  } finally { await close(instance); }
});

test('refusal, incomplete body deadline and unexpected HTTP responses stay distinct', async () => {
  const refused = await server((_req, res) => res.end());
  const port = refused.address().port;
  await close(refused);
  assert.equal((await healthRequest(port, 500)).category, 'refused');
  const hanging = await server((_req, res) => { res.writeHead(200); res.write('{'); });
  try { assert.equal((await healthRequest(hanging.address().port, 30)).category, 'timeout'); }
  finally { hanging.closeAllConnections(); await close(hanging); }
  const bad = await server((_req, res) => { res.writeHead(503); res.end('{"status":"healthy"}'); });
  try { assert.equal((await healthRequest(bad.address().port, 500)).category, 'httpError'); }
  finally { await close(bad); }
});
