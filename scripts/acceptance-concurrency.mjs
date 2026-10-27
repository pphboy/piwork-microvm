// Run on the same native host as the ready MicroVM. Each request uses a new
// connection, never retries, and has one deadline covering connection and body.
import http from 'node:http';
import { performance } from 'node:perf_hooks';
import { mkdir, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export function healthRequest(port, deadlineMs = 10000) {
  return new Promise(resolveResult => {
    const started = performance.now();
    let connectedMs = null, settled = false, timer;
    const finish = (category, extra = {}) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveResult({ category, connectMs: connectedMs === null ? null : +connectedMs.toFixed(3), elapsedMs: +(performance.now() - started).toFixed(3), ...extra });
    };
    const request = http.get({ hostname: '127.0.0.1', port, path: '/healthz', agent: false, headers: { Connection: 'close' } }, response => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', chunk => {
        body += chunk;
        if (body.length > 65536) { finish('httpError', { status: response.statusCode, error: 'response body exceeds 64 KiB' }); request.destroy(); }
      });
      response.on('end', () => {
        let healthy = false;
        try { healthy = JSON.parse(body).status === 'healthy'; } catch {}
        finish(response.statusCode === 200 && healthy ? 'success' : 'httpError', { status: response.statusCode });
      });
      response.on('error', error => finish('otherError', { error: error.code || error.message }));
      response.on('aborted', () => finish('otherError', { error: 'response aborted' }));
    });
    request.on('socket', socket => socket.once('connect', () => { connectedMs = performance.now() - started; }));
    request.on('error', error => finish(error.code === 'ECONNREFUSED' ? 'refused' : 'otherError', { error: error.code || error.message }));
    timer = setTimeout(() => { finish('timeout'); request.destroy(); }, deadlineMs);
  });
}

export function summarize(results) {
  const counts = { success: 0, refused: 0, otherError: 0, timeout: 0, httpError: 0 };
  for (const result of results) counts[result.category]++;
  return counts;
}

export async function measure(port, { batches = 5, width = 6, serial = 30, deadlineMs = 10000 } = {}) {
  const sequential = [];
  for (let i = 0; i < serial; i++) sequential.push(await healthRequest(port, deadlineMs));
  const concurrent = [];
  for (let batch = 0; batch < batches; batch++) {
    // Queue all six new requests synchronously before the event loop can run.
    concurrent.push(...await Promise.all(Array.from({ length: width }, () => healthRequest(port, deadlineMs))));
  }
  return { port, sequential: { counts: summarize(sequential), requests: sequential }, concurrent: { counts: summarize(concurrent), requests: concurrent } };
}

async function main() {
  const ports = [Number(process.env.PIWORK_ACCEPTANCE_PORT || 17891), Number(process.env.PIWORK_ACCEPTANCE_CORE_PORT || 17871)];
  if (ports.some(p => !Number.isInteger(p) || p < 1 || p > 65535) || ports[0] === ports[1]) throw new Error('UI and Core ports must be distinct valid ports');
  const report = { platform: process.platform, node: process.version, timestamp: new Date().toISOString(), endpoint: '/healthz', deadlineMs: 10000, retries: 0, connectionReuse: false, ui: await measure(ports[0]), core: await measure(ports[1]) };
  const out = resolve(process.env.PIWORK_ACCEPTANCE_OUT || join(import.meta.dirname, '../dist/acceptance'));
  await mkdir(out, { recursive: true, mode: 0o700 });
  const reportPath = join(out, `concurrency-${process.platform}-${ports.join('-')}.json`);
  await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n', { mode: 0o600 });
  for (const role of ['ui', 'core']) console.log(`${role} ${report[role].port}: serial ${JSON.stringify(report[role].sequential.counts)}, concurrent ${JSON.stringify(report[role].concurrent.counts)}`);
  console.log(`Evidence: ${reportPath}`);
  if (['ui', 'core'].some(role => report[role].sequential.counts.success !== 30 || report[role].concurrent.counts.success !== 30)) process.exitCode = 1;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) main().catch(error => { console.error(error.message); process.exitCode = 1; });
