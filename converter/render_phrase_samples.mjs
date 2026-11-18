// Exercise the installed Yomitan structured-content generator, not a mock DOM builder.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [environmentRoot,payloadPath,outputPath]=process.argv.slice(2);
const {JSDOM}=await import(pathToFileURL(path.join(environmentRoot,'scgen_test/node_modules/jsdom/lib/api.js')));
const {StructuredContentGenerator}=await import(pathToFileURL(path.join(environmentRoot,'scgen_test/js/display/structured-content-generator.js')));
const input=JSON.parse(fs.readFileSync(payloadPath,'utf8'));
const dom=new JSDOM('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>',{url:'https://dictionary.local/'});
globalThis.location=dom.window.location;
class ContentManager {
    prepareLink(node,href){node.setAttribute('href',href);}
    prepareScripts(){} prepareHTML(){} loadMedia(){} openMediaInTab(){}
}
const gen=new StructuredContentGenerator(new ContentManager(),dom.window.document,dom.window);
const results={};
for(const [phrase,content] of Object.entries(input.entries)){
    const article=dom.window.document.createElement('article');
    article.dataset.phrase=phrase;
    article.append(gen.createStructuredContent(content,'LDOCE6 English Phrases'));
    if(article.querySelector('script,iframe,img,audio'))throw new Error(`Unexpected media/script: ${phrase}`);
    if(!article.textContent.trim())throw new Error(`Empty render: ${phrase}`);
    results[phrase]={text:article.textContent,links:[...article.querySelectorAll('a')].map(n=>n.getAttribute('href'))};
    dom.window.document.body.append(article);
}
const hang=results['hang by a thread'];
if(!hang?.text.includes('very dangerous situation')||!hang.text.includes('his life hanging by a thread'))throw new Error('hang by a thread lost its meaning/example');
if(!hang.links.some(h=>h.includes('query=hang')))throw new Error('Missing source link');
if(input.entries.abandon){
    const heads=[...dom.window.document.querySelectorAll('article[data-phrase="abandon"] [data-sc-class="l6p-entryhead"]')];
    if(heads.length!==2)throw new Error('abandon lost a homonym');
    for(const head of heads){
        if((head.textContent.match(/\babandon\b/g)||[]).length!==1)throw new Error('Duplicate abandon headword');
        if(head.querySelector('[data-sc-class="l6p-homnum"]')?.style.verticalAlign!=='super')throw new Error('Homonym number not superscript');
    }
    if(!heads[0].textContent.replace(/\s+/g,' ').startsWith('abandon 1 /'))throw new Error('Metadata separators lost');
    results.abandon.heads=heads.map(h=>h.textContent);
}
const style=dom.window.document.createElement('style');
style.textContent=`body{font:16px/1.5 system-ui;margin:2em auto;max-width:850px;padding:1em}article{padding:1em 0;border-bottom:1px solid #aaa}${input.css}`;
dom.window.document.head.append(style);
fs.writeFileSync(outputPath,dom.serialize());
fs.writeFileSync(outputPath+'.json',JSON.stringify({entries:Object.keys(results).length,results},null,2));
console.log(JSON.stringify({entries:Object.keys(results).length,output:outputPath}));
