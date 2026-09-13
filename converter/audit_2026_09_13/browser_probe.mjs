// Actual Yomitan generator + isolated, headless Chrome. No extension/UI claims.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {JSDOM, VirtualConsole} from '../../scgen_test/node_modules/jsdom/lib/api.js';
import {StructuredContentGenerator} from '../../scgen_test/js/display/structured-content-generator.js';
const out=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(out,'../..');
const payload=JSON.parse(fs.readFileSync(path.join(out,'sample_payload.json'),'utf8'));
const css=fs.readFileSync(path.join(root,'yomitan_full/styles.css'),'utf8');
const sample=payload.find(x=>x.word==='act');
if(!sample) throw Error('act missing from sample_payload.json');
const dom=new JSDOM('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>',{virtualConsole:new VirtualConsole()});
const win=dom.window; globalThis.location=win.location;
class Fake { prepareLink(n,h){n.setAttribute('href',h);} prepareScripts(){} prepareHTML(){} loadMedia(){} openMediaInTab(){} }
const gen=new StructuredContentGenerator(new Fake(),win.document,win);
const modes=['light','dark','dark-control','no-css'];
for(const mode of modes){
    const section=win.document.createElement('section');
    section.dataset.mode=mode;
    if(mode!=='no-css') section.className='styled';
    section.style.cssText=`--text-color:${mode==='light'||mode==='no-css'?'#000000':'#d4d4d4'};background:${mode==='light'||mode==='no-css'?'#ffffff':'#1e1e1e'};color:var(--text-color);padding:16px`;
    const content=gen.createStructuredContent(sample.content,'review');
    if(mode==='dark-control') for(const n of content.querySelectorAll('[style]')) if(['green','dodgerblue'].includes(n.style.color)) n.style.removeProperty('color');
    section.append(content);win.document.body.append(section);
}
const style=win.document.createElement('style');
style.textContent=`body{margin:0;font:16px/1.5 sans-serif}.styled{${css}}`;
win.document.head.append(style);
const script=win.document.createElement('script');
script.textContent=String.raw`
const rgb=c=>{const cv=document.createElement('canvas');cv.width=cv.height=1;const ctx=cv.getContext('2d');ctx.fillStyle=c;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data].slice(0,3)};
const lum=a=>a.map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);
const contrast=(a,b)=>{a=lum(a);b=lum(b);return +((Math.max(a,b)+.05)/(Math.min(a,b)+.05)).toFixed(3)};
const result={userAgent:navigator.userAgent,colorMix:CSS.supports('color','color-mix(in srgb,red,blue)'),modes:{}};
for(const section of document.querySelectorAll('section[data-mode]')){
    const bg=rgb(getComputedStyle(section).backgroundColor);
    const fields={};
    for(const cls of ['ld-defcn','ld-excn','ld-pos','ld-gram','ld-field']){
        const n=section.querySelector('[data-sc-class="'+cls+'"]');if(!n)continue;
        const walker=document.createTreeWalker(n,NodeFilter.SHOW_TEXT);let t;
        while((t=walker.nextNode())&&!t.textContent.trim()){}
        const leaf=t?t.parentElement:n;
        const color=getComputedStyle(leaf).color;
        fields[cls]={inlineColor:n.style.color,color,contrast:contrast(rgb(color),bg),text:leaf.innerText.slice(0,65)};
    }
    const lists=[...section.querySelectorAll('[data-sc-class="ld-senselist"]')];
    const ol=lists.find(ol=>{const ns=[...ol.querySelectorAll('[data-sc-class="ld-snum"]')].filter(n=>n.closest('[data-sc-class="ld-senselist"]')===ol);return ns.length===4&&ns[0].textContent.trim()==='7'});
    const nums=ol?[...ol.querySelectorAll('[data-sc-class="ld-snum"]')].filter(n=>n.closest('[data-sc-class="ld-senselist"]')===ol):[];
    result.modes[section.dataset.mode]={fields,numbering:ol?{start:ol.start,listStyle:getComputedStyle(ol).listStyleType,sourceNumbers:nums.map(n=>n.textContent.trim()),chipSizes:nums.map(n=>getComputedStyle(n).fontSize),chipWidths:nums.map(n=>+n.getBoundingClientRect().width.toFixed(2)),nativeOrdinals:[...ol.children].map((li,i)=>li.value||ol.start+i)}:null};
}
const pre=document.createElement('pre');pre.id='review-result';pre.textContent=JSON.stringify(result);document.body.prepend(pre);
`;
win.document.body.append(script);
const html=path.join(out,'browser_probe.html');fs.writeFileSync(html,dom.serialize(),'utf8');
const chrome='C:/Program Files/Google/Chrome/Application/chrome.exe';
const profile=path.join(out,'.chrome-'+Date.now());
const r=spawnSync(chrome,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-extensions','--disable-background-networking','--disable-sync','--user-data-dir='+profile,'--dump-dom',pathToFileURL(html).href],{encoding:'utf8',timeout:90000,maxBuffer:20*1024*1024,windowsHide:true});
fs.writeFileSync(path.join(out,'browser_stderr.log'),r.stderr||String(r.error||''),'utf8');
if(r.status!==0){console.error(r.stderr||r.error);process.exit(r.status||2)}
const rendered=new JSDOM(r.stdout,{virtualConsole:new VirtualConsole()});
const result=rendered.window.document.querySelector('#review-result');
if(!result)throw Error('Chrome did not produce the measurement element; see browser_stderr.log');
const parsed=JSON.parse(result.textContent);
fs.writeFileSync(path.join(out,'browser_results.json'),JSON.stringify(parsed,null,2)+'\n','utf8');
console.log(JSON.stringify(parsed,null,2));
