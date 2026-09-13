// Render-contract measurements: real Yomitan generator (jsdom) -> real Chrome.
// Driven by converter/regress_render_contract.py, which supplies the payload and
// the stylesheet and then asserts on the JSON printed here.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {JSDOM, VirtualConsole} from '../scgen_test/node_modules/jsdom/lib/api.js';
import {StructuredContentGenerator} from '../scgen_test/js/display/structured-content-generator.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const scratch = path.join(here, '_rc');
fs.mkdirSync(scratch, {recursive: true});
const payloadPath = process.argv[2];
const cssPath = process.argv[3];
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
const css = fs.readFileSync(cssPath, 'utf8');

const dom = new JSDOM('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>',
                      {virtualConsole: new VirtualConsole()});
const win = dom.window;
globalThis.location = win.location;
class Fake {
    prepareLink(n, h) { n.setAttribute('href', h); }
    prepareScripts() {} prepareHTML() {} loadMedia() {} openMediaInTab() {}
}
const gen = new StructuredContentGenerator(new Fake(), win.document, win);

// light + dark exercise the theme palette (the R3 regression); no-css exercises
// what an Anki export / plain-HTML host actually sees.
const modes = ['light', 'dark', 'no-css'];
for (const mode of modes) {
    const section = win.document.createElement('section');
    section.dataset.mode = mode;
    const light = (mode === 'light' || mode === 'no-css');
    if (mode !== 'no-css') section.className = 'styled';
    section.style.cssText =
        `--text-color:${light ? '#000000' : '#d4d4d4'};` +
        `background:${light ? '#ffffff' : '#1e1e1e'};color:var(--text-color);padding:16px`;
    for (const [word, sc] of Object.entries(payload)) {
        const holder = win.document.createElement('div');
        holder.dataset.word = word;
        holder.append(gen.createStructuredContent(sc, 'LDOCE5pp (LM5pp)'));
        section.append(holder);
    }
    win.document.body.append(section);
}
const style = win.document.createElement('style');
style.textContent = `body{margin:0;font:16px/1.5 sans-serif}.styled{${css}}`;
win.document.head.append(style);

const script = win.document.createElement('script');
script.textContent = String.raw`
const rgb = c => { const cv=document.createElement('canvas'); cv.width=cv.height=1;
  const ctx=cv.getContext('2d'); ctx.fillStyle=c; ctx.fillRect(0,0,1,1);
  return [...ctx.getImageData(0,0,1,1).data].slice(0,3); };
const lum = a => a.map(x => { x/=255; return x<=.04045 ? x/12.92 : ((x+.055)/1.055)**2.4; })
  .reduce((s,x,i) => s + x*[.2126,.7152,.0722][i], 0);
const contrast = (a,b) => { a=lum(a); b=lum(b);
  return +((Math.max(a,b)+.05)/(Math.min(a,b)+.05)).toFixed(2); };
// first visible text leaf inside a node: inline styles land on descendants, so
// reading the wrapper's own colour would miss the declaration we care about
const leafOf = n => { const w=document.createTreeWalker(n,NodeFilter.SHOW_TEXT); let t;
  while ((t=w.nextNode()) && !t.textContent.trim()) {}
  return t ? t.parentElement : n; };
const out = { userAgent: navigator.userAgent,
              colorMix: CSS.supports('color','color-mix(in srgb,red,blue)'), modes: {} };
const CLASSES = ['ld-pos','ld-gram','ld-defcn','ld-excn','ld-field','ld-grouptitle'];
for (const section of document.querySelectorAll('section[data-mode]')) {
  const bg = rgb(getComputedStyle(section).backgroundColor);
  const rec = {fields:{}, weights:{}, marks:{}, lists:[], defMarginBottom:null};
  const host = section.querySelector('[data-word="act"]') || section;
  for (const cls of CLASSES) {
    const n = section.querySelector('[data-sc-class="'+cls+'"]');
    if (!n) continue;
    const leaf = leafOf(n), cs = getComputedStyle(leaf);
    rec.fields[cls] = { inline: n.style.color || null, computed: cs.color,
                        contrast: contrast(rgb(cs.color), bg),
                        text: (leaf.textContent||'').trim().slice(0,40) };
  }
  for (const cls of ['ld-nodew','ld-colloin','ld-collo']) {
    const n = section.querySelector('[data-sc-class="'+cls+'"]');
    if (n) rec.weights[cls] = { inline: n.style.fontWeight || null,
                                computed: getComputedStyle(n).fontWeight };
  }
  for (const cls of ['ld-mark','ld-snum','ld-empty']) {
    const n = section.querySelector('[data-sc-class="'+cls+'"]');
    rec.marks[cls] = n ? { display: getComputedStyle(n).display,
                           text: (n.textContent||'').trim().slice(0,12),
                           fontSize: getComputedStyle(n).fontSize,
                           width: +n.getBoundingClientRect().width.toFixed(2) } : null;
  }
  for (const ol of section.querySelectorAll('[data-sc-class="ld-senselist"]')) {
    const snums = [...ol.querySelectorAll('[data-sc-class="ld-snum"]')]
      .filter(n => n.closest('[data-sc-class="ld-senselist"]') === ol);
    const lis = [...ol.children].filter(c => c.tagName === 'LI');
    rec.lists.push({ listStyle: getComputedStyle(ol).listStyleType,
                     start: ol.start, items: lis.length,
                     sourceNumbers: snums.map(n => (n.textContent||'').trim()),
                     chipFontSizes: snums.map(n => getComputedStyle(n).fontSize),
                     chipWidths: snums.map(n => +n.getBoundingClientRect().width.toFixed(2)),
                     inlineListStyle: ol.style.listStyleType || null,
                     nested: [...ol.querySelectorAll('ul')].length });
  }
  const d = host.querySelector('[data-sc-class="ld-def"]');
  if (d) rec.defMarginBottom = getComputedStyle(d).marginBottom;
  out.modes[section.dataset.mode] = rec;
}
const pre = document.createElement('pre');
pre.id = 'contract-result';
pre.textContent = JSON.stringify(out);
document.body.prepend(pre);
`;
win.document.body.append(script);

const html = path.join(scratch, 'page.html');
fs.writeFileSync(html, dom.serialize(), 'utf8');
const chrome = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const r = spawnSync(chrome, ['--headless=new', '--no-sandbox', '--disable-gpu',
    '--no-first-run', '--no-default-browser-check', '--disable-extensions',
    '--disable-background-networking', '--disable-sync',
    '--user-data-dir=' + path.join(scratch, 'chrome-profile'),
    '--dump-dom', pathToFileURL(html).href],
    {encoding: 'utf8', timeout: 120000, maxBuffer: 40 * 1024 * 1024, windowsHide: true});
if (r.status !== 0) {
    console.error('chrome failed', r.status, (r.stderr || '').slice(0, 500));
    process.exit(r.status || 2);
}
const rendered = new JSDOM(r.stdout, {virtualConsole: new VirtualConsole()});
const node = rendered.window.document.querySelector('#contract-result');
if (!node) {
    console.error('chrome produced no measurement element');
    process.exit(3);
}
process.stdout.write(node.textContent);
