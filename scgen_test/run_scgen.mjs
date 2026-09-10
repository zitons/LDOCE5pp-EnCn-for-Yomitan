import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
import {StructuredContentGenerator} from './js/display/structured-content-generator.js';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
const {window} = dom;
globalThis.location = window.location;

class FakeContentManager {
    prepareLink (node, href) {
        node.setAttribute('href', href);
        node.dataset.prepared = 'true';
    }
    prepareScripts () {}
    prepareHTML () {}
    loadMedia () {}
    openMediaInTab () {}
}

const gen = new StructuredContentGenerator(new FakeContentManager(), window.document, window);

const payload = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const sampleWord = process.argv[3] || '';

let ok = 0;
let fail = 0;
let totalElements = 0;
let totalLinks = 0;
let classlessDetails = 0;
const fails = [];

for (const {word, content} of payload) {
    try {
        const el = gen.createStructuredContent(content, 'LDOCE5pp (LM5pp)');
        const html = el.outerHTML;
        if (word === sampleWord) {
            console.log('===== SAMPLE ' + word + ' =====');
            console.log(html.slice(0, 4000));
            console.log('... (' + html.length + ' chars total)');
        }
        const els = el.querySelectorAll('*').length;
        const links = el.querySelectorAll('a[data-external]').length + el.querySelectorAll('a:not([data-external])').length;
        totalElements += els;
        totalLinks += links;
        for (const d of el.querySelectorAll('details')) {
            if (!d.querySelector('summary')) { classlessDetails++; }
        }
        if (els < 3) { fails.push([word, 'degenerate DOM: ' + els + ' elements']); }
        ok++;
    } catch (e) {
        fail++;
        if (fails.length < 15) {
            fails.push([word, String(e && e.stack || e).split('\n').slice(0, 3).join(' | ')]);
        }
    }
}

console.log('real-generator: ok=' + ok + ' fail=' + fail + ' total=' + payload.length);
console.log('elements rendered=' + totalElements + ' links=' + totalLinks +
            ' details-without-summary=' + classlessDetails);
for (const [w, e] of fails) {
    console.log('ISSUE', JSON.stringify(w), e.slice(0, 300));
}
