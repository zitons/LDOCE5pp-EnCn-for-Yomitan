// Screenshot a page through CDP, using Node's built-in global WebSocket (no `ws`
// package -- see cdp.mjs for the same approach).
//   node cdp_shot.mjs <url> <out.png> [width]
// Waits for Page.loadEventFired plus two animation frames so layout and paint
// settle before capturing, and uses captureBeyondViewport so the whole entry is
// captured rather than just the first viewport.
const TARGET = process.env.CDP_TARGET || 'http://127.0.0.1:9333';
const PAGE = process.argv[2];
const OUT = process.argv[3];
const WIDTH = parseInt(process.argv[4] || '390', 10);

if (!PAGE || !OUT) {
    console.error('usage: node cdp_shot.mjs <page-url> <out.png> [width]');
    process.exit(2);
}

const fs = await import('node:fs');

let list;
try {
    list = await (await fetch(`${TARGET}/json/new?${encodeURIComponent(PAGE)}`,
                              {method: 'PUT'})).json();
} catch (e) {
    console.error(`cannot reach a DevTools endpoint at ${TARGET}: ${e.message}`);
    process.exit(2);
}

const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
const events = [];
const send = (method, params = {}) => new Promise((resolve) => {
    const mid = ++id;
    pending.set(mid, resolve);
    ws.send(JSON.stringify({id: mid, method, params}));
});
ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.method) events.push(msg.method);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});

await new Promise((r) => ws.addEventListener('open', r));
await send('Page.enable');
await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride',
           {width: WIDTH, height: 900, deviceScaleFactor: 1, mobile: false});

const nav = await send('Page.navigate', {url: PAGE});
if (nav?.result?.errorText) {
    console.error(`navigate failed: ${nav.result.errorText}`);
    process.exit(1);
}

// wait for load, then two frames
await new Promise((resolve) => {
    if (events.includes('Page.loadEventFired')) return resolve();
    const t = setTimeout(resolve, 8000);
    const onMsg = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.method === 'Page.loadEventFired') {
            clearTimeout(t);
            ws.removeEventListener('message', onMsg);
            resolve();
        }
    };
    ws.addEventListener('message', onMsg);
});
await send('Runtime.evaluate', {
    expression: 'new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(1))))',
    awaitPromise: true, returnByValue: true,
});

const shot = await send('Page.captureScreenshot',
                        {format: 'png', captureBeyondViewport: true});
if (!shot?.result?.data) {
    console.error('screenshot failed:', JSON.stringify(shot).slice(0, 300));
    process.exit(1);
}
fs.writeFileSync(OUT, Buffer.from(shot.result.data, 'base64'));
console.log(`screenshot ${OUT} (${fs.statSync(OUT).size} B)`);
ws.close();
