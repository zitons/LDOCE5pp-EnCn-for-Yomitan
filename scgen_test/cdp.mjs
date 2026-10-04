// Minimal CDP probe used by the packaging/rendering gates: open PAGE in the
// headless Chrome listening on the DevTools port, evaluate the expression in
// EXPR_FILE, print the JSON result.
//
//   node cdp.mjs <page-url> <expr-file>
//
// Prerequisite (see HANDOVER §5): a headless Chrome with --remote-debugging-port,
// e.g.
//   chrome --headless=new --disable-gpu --no-sandbox \
//          --remote-debugging-port=9333 --user-data-dir=<tmp> about:blank
// Override the endpoint with CDP_TARGET when it listens elsewhere.
//
// NOTE: this file is tracked in git on purpose -- 20+ gates depend on it, and
// while it was gitignored the whole family was unrunnable from a clean checkout
// (flagged in review on PR #2).
const TARGET = process.env.CDP_TARGET || 'http://127.0.0.1:9333';
const PAGE = process.argv[2];
if (!PAGE || !process.argv[3]) {
    console.error('usage: node cdp.mjs <page-url> <expr-file>');
    process.exit(2);
}

let list;
try {
    list = await (await fetch(`${TARGET}/json/new?${encodeURIComponent(PAGE)}`,
                              {method: 'PUT'})).json();
} catch (e) {
    console.error(`cannot reach a DevTools endpoint at ${TARGET}: ${e.message}\n` +
                  `start one with:\n` +
                  `  chrome --headless=new --disable-gpu --no-sandbox \\\n` +
                  `         --remote-debugging-port=9333 --user-data-dir=<tmp> about:blank`);
    process.exit(2);
}
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
const send = (method, params = {}) => new Promise((resolve) => {
    const mid = ++id;
    pending.set(mid, resolve);
    ws.send(JSON.stringify({id: mid, method, params}));
});
ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
await new Promise((r) => ws.addEventListener('open', r));
await send('Page.enable');
await send('Runtime.enable');
await new Promise((r) => setTimeout(r, 700));

const expr = (await import("node:fs")).readFileSync(process.argv[3], "utf8");
const res = await send('Runtime.evaluate', {expression: expr, returnByValue: true});
const ex = res.result?.exceptionDetails;
if (ex) {
    // Runtime.evaluate reports a thrown expression here rather than failing the
    // protocol call. Without this check the helper printed the fallback response
    // and still exited 0, so a malformed probe looked like a successful invocation
    // -- which is how a gate ended up dying later with a baffling TypeError instead
    // of pointing at its own broken expression.
    const desc = ex.exception?.description || ex.exception?.value || ex.text || '';
    console.error('the evaluated expression threw:\n' + desc);
    if (ex.lineNumber !== undefined) console.error(`  at expression line ${ex.lineNumber + 1}`);
    ws.close();
    process.exit(1);
}
const value = res.result?.result?.value;
if (value === undefined) {
    // not an exception, but no value either. Every gate's expression returns JSON,
    // so this means the probe itself is broken -- it must not look successful.
    console.error('the evaluated expression produced no value; raw result:\n' +
                  JSON.stringify(res.result, null, 1));
    ws.close();
    process.exit(1);
}
console.log(JSON.stringify(value, null, 1));
ws.close();
