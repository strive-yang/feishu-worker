// Synthetic loopback-only compatibility checks for the get-uri -> basic-ftp override.
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const http = require('node:http');
const net = require('node:net');
const { performance } = require('node:perf_hooks');

// Resolve through the real MCP dependency chain, not an accidental top-level copy.
const larkRequire = createRequire(require.resolve('@larksuiteoapi/lark-mcp/package.json'));
const proxyRequire = createRequire(larkRequire.resolve('proxy-agent'));
const pacRequire = createRequire(proxyRequire.resolve('pac-proxy-agent'));
const uriRequire = createRequire(pacRequire.resolve('get-uri'));
const ftp = uriRequire('basic-ftp');
const { getUri } = pacRequire('get-uri');
const PAC = 'function FindProxyForURL(url, host) { return "DIRECT"; }';

async function read(stream) {
  const chunks = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString('utf8');
}

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return server.address().port;
}

async function closeServer(server) {
  if (!server.listening) return;
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
}

async function ftpFixture({ pasv = false, machineListing = false } = {}) {
  const servers = new Set();
  const sockets = new Set();
  const commands = [];
  function track(socket) {
    sockets.add(socket);
    socket.on('error', () => {});
    socket.on('close', () => sockets.delete(socket));
    return socket;
  }
  const control = net.createServer(raw => {
    const socket = track(raw);
    socket.setEncoding('utf8');
    socket.write('220 Local synthetic FTP fixture\r\n');
    let buffer = '';
    let dataConnection;
    let dataReady;
    let commandQueue = Promise.resolve();
    async function passive(mode) {
      const server = net.createServer(data => {
        track(data);
        dataConnection(data);
      });
      servers.add(server);
      dataReady = new Promise(resolve => { dataConnection = resolve; });
      const port = await listen(server);
      if (mode === 'EPSV') socket.write(`229 Entering Extended Passive Mode (|||${port}|)\r\n`);
      // Deliberately advertise another loopback IP, never an external host. v6
      // must retain the control host rather than opt back into FTP bounce risk.
      else socket.write(`227 Entering Passive Mode (127,0,0,2,${port >> 8},${port & 255})\r\n`);
    }
    async function transfer(payload) {
      socket.write('150 Opening data connection\r\n');
      const data = await dataReady;
      data.once('close', () => {
        if (!socket.destroyed) socket.write('226 Transfer complete\r\n');
      });
      data.end(payload);
    }
    async function handle(line) {
      const command = line.split(' ', 1)[0].toUpperCase();
      commands.push(command);
      if (command === 'USER') socket.write('331 Password required\r\n');
      else if (command === 'PASS') socket.write('230 Logged in\r\n');
      else if (command === 'FEAT') {
        socket.write('211-Features\r\n UTF8\r\n' +
          (machineListing ? ' MLST type*;size*;modify*;\r\n' : '') + '211 End\r\n');
      }
      else if (command === 'PWD') socket.write('257 "/"\r\n');
      else if (command === 'MDTM') {
        socket.write(line.includes('missing') ? '550 Not found\r\n' :
          machineListing ? '502 Use machine-readable listing fallback\r\n' : '213 20200101000000\r\n');
      } else if (command === 'EPSV') {
        if (pasv) socket.write('502 Use PASV fallback\r\n');
        else await passive('EPSV');
      } else if (command === 'PASV') await passive('PASV');
      else if (command === 'LIST') {
        await transfer(`-rw-r--r-- 1 owner group ${Buffer.byteLength(PAC)} Jan 1 2020 proxy.pac\r\n`);
      } else if (command === 'MLSD') {
        await transfer(`type=file;size=${Buffer.byteLength(PAC)};modify=20200101000000; proxy.pac\r\n`);
      } else if (command === 'RETR') await transfer(PAC);
      else if (command === 'QUIT') socket.end('221 Bye\r\n');
      else socket.write('200 OK\r\n');
    }
    socket.on('data', chunk => {
      buffer += chunk;
      let index;
      while ((index = buffer.indexOf('\r\n')) !== -1) {
        const line = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);
        commandQueue = commandQueue.then(() => handle(line)).catch(() => socket.destroy());
      }
    });
  });
  servers.add(control);
  const port = await listen(control);
  return {
    url: `ftp://127.0.0.1:${port}/proxy.pac`, commands,
    async close() {
      for (const socket of sockets) socket.destroy();
      await Promise.all([...servers].map(closeServer));
    }
  };
}

async function parserCheck() {
  const normal = '-rw-r--r-- 1 owner group 42 Jan 1 2020 file.txt';
  assert.equal(ftp.parseList(normal)[0].name, 'file.txt');
  // Bounded reproduction of GHSA-c475-qrg2-pj4r in a time-limited subprocess.
  const malformed = '-rw-r--r-- 1 ' + 'a '.repeat(32768) + '!';
  const start = performance.now();
  try { ftp.parseList(malformed + '\r\n' + normal + '\r\n'); } catch {
    // Rejecting an invalid listing is fine; stalling the event loop is not.
  }
  assert.ok(performance.now() - start < 1500, 'directory parsing exceeded the CPU regression bound');
}

async function ftpCheck(pasv, machineListing = false) {
  const fixture = await ftpFixture({ pasv, machineListing });
  try {
    const stream = await getUri(fixture.url, { timeout: 2000 });
    assert.equal(await read(stream), PAC);
    assert.ok(stream.lastModified instanceof Date);
    assert.ok(fixture.commands.includes('MDTM'));
    assert.ok(fixture.commands.includes('RETR'));
    if (machineListing) assert.ok(fixture.commands.includes('MLSD'));
    // Unix LIST intentionally has no reliable parsed modifiedAt in basic-ftp;
    // verify its public API separately rather than assuming get-uri can cache it.
    const client = new ftp.Client(2000);
    try {
      const url = new URL(fixture.url);
      await client.access({ host: url.hostname, port: Number(url.port) });
      assert.equal((await client.list())[0].name, 'proxy.pac');
    } finally {
      client.close();
    }
    if (pasv) assert.ok(fixture.commands.includes('PASV'));
    await assert.rejects(getUri(fixture.url, { cache: stream, timeout: 2000 }), { code: 'ENOTMODIFIED' });
    await assert.rejects(getUri(fixture.url.replace('proxy.pac', 'missing'), { timeout: 2000 }),
                         { code: 'ENOTFOUND' });
  } finally {
    await fixture.close();
  }
}

async function proxyCheck() {
  const { ProxyAgent } = larkRequire('proxy-agent');
  const { PacProxyAgent } = proxyRequire('pac-proxy-agent');
  const fixture = await ftpFixture();
  const origin = http.createServer((request, response) => response.end('loopback origin'));
  const originPort = await listen(origin);
  let proxied = false;
  const proxy = http.createServer((request, response) => {
    proxied = true;
    assert.equal(request.url, `http://127.0.0.1:${originPort}/check`);
    response.end('loopback proxy');
  });
  const proxyPort = await listen(proxy);
  const agents = [];
  async function request(agent, expected) {
    agents.push(agent);
    const stream = await new Promise((resolve, reject) => {
      const req = http.get(`http://127.0.0.1:${originPort}/check`, { agent }, resolve);
      req.once('error', reject);
      req.setTimeout(3000, () => req.destroy(new Error('loopback test request timed out')));
    });
    assert.equal(await read(stream), expected);
  }
  try {
    await request(new ProxyAgent({ getProxyForUrl: () => '' }), 'loopback origin');
    await request(new ProxyAgent({ getProxyForUrl: () => `http://127.0.0.1:${proxyPort}` }), 'loopback proxy');
    assert.ok(proxied);
    await request(new PacProxyAgent('data:application/x-ns-proxy-autoconfig,' + encodeURIComponent(PAC)),
                  'loopback origin');
    await request(new PacProxyAgent('pac+' + fixture.url, { timeout: 2000 }), 'loopback origin');
    assert.ok(fixture.commands.includes('RETR'));
  } finally {
    for (const agent of agents) agent.destroy();
    await fixture.close();
    await Promise.all([closeServer(origin), closeServer(proxy)]);
  }
}

async function main() {
  const scenario = process.argv[2];
  if (scenario === 'version') {
    assert.equal(uriRequire('basic-ftp/package.json').version, '6.2.3');
    assert.equal(pacRequire('get-uri/package.json').version, '6.0.5');
    assert.equal(larkRequire('proxy-agent/package.json').version, '6.5.0');
    assert.equal(larkRequire('./package.json').version, '0.5.1');
  } else if (scenario === 'parser') await parserCheck();
  else if (scenario === 'ftp') await ftpCheck(false);
  else if (scenario === 'listing') await ftpCheck(false, true);
  else if (scenario === 'pasv') await ftpCheck(true);
  else if (scenario === 'proxy') await proxyCheck();
  else throw new Error('Unknown test scenario');
  assert.equal(Object.keys(require.cache).filter(p =>
    /lark-mcp[\\/]dist[\\/](auth[\\/]|utils[\\/]logger\.js)/.test(p)).length, 0);
  console.log(`PASS: ${scenario}`);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
