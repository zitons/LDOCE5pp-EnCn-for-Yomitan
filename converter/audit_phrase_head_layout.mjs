// Actual Chrome layout checks at narrow/wide widths, both themes and without CSS.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';

const [pagePath,outputPath,screenshotPath]=process.argv.slice(2);
const endpoint=process.env.CDP_TARGET||'http://127.0.0.1:9337';
const page=await (await fetch(`${endpoint}/json/new?about:blank`,{method:'PUT'})).json();
const ws=new WebSocket(page.webSocketDebuggerUrl);
let id=0; const pending=new Map();
const send=(method,params={})=>new Promise((resolve,reject)=>{
    const mid=++id; pending.set(mid,{resolve,reject});ws.send(JSON.stringify({id:mid,method,params}));
});
ws.addEventListener('message',ev=>{const m=JSON.parse(ev.data);if(pending.has(m.id)){
    const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);
}});
await new Promise(r=>ws.addEventListener('open',r));
await send('Page.enable');await send('Runtime.enable');
await send('Page.navigate',{url:pathToFileURL(pagePath).href});
const evaluate=async expression=>{
    const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);
    return r.result.value;
};
await evaluate('new Promise(r => {if(document.readyState === "complete")r(true);else addEventListener("load",()=>r(true),{once:true});})');
const records=[];
for(const width of [360,900])for(const mode of ['light','dark','no-css']){
    await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate(`(() => {
      for(const style of document.querySelectorAll('style'))style.disabled=${mode==='no-css'};
      document.body.style.backgroundColor=${JSON.stringify(mode==='dark'?'#171717':'#ffffff')};
      document.body.style.color=${JSON.stringify(mode==='dark'?'#e5e7eb':'#111111')};
      document.body.style.setProperty('--text-color',${JSON.stringify(mode==='dark'?'#e5e7eb':'#111111')});
    })()`);
    await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
    const record=await evaluate(`(() => {
      const article=document.querySelector('article[data-phrase="abandon"]');
      return {width:innerWidth,heads:[...article.querySelectorAll('[data-sc-class="l6p-entryhead"]')].map(h=>{
        const word=h.querySelector('[data-sc-class="l6p-hwd"]'),num=h.querySelector('[data-sc-class="l6p-homnum"]');
        return {text:h.innerText.replace(/\\s+/g,' ').trim(),wordTop:word.getBoundingClientRect().top,
          numberTop:num.getBoundingClientRect().top,numberSize:parseFloat(getComputedStyle(num).fontSize),
          wordSize:parseFloat(getComputedStyle(word).fontSize),verticalAlign:getComputedStyle(num).verticalAlign,
          overflow:h.scrollWidth-h.clientWidth,color:getComputedStyle(h).color};
      })};
    })()`);
    record.mode=mode;
    if(record.heads.length!==2)throw new Error('Missing homonym');
    for(const h of record.heads){
        if((h.text.match(/\babandon\b/g)||[]).length!==1)throw new Error(`Duplicate headword ${mode}/${width}`);
        if(h.overflow>1)throw new Error(`Header overflow ${mode}/${width}`);
        if(h.verticalAlign!=='super'||h.numberSize>=h.wordSize||h.numberTop>h.wordTop+1)throw new Error(`Homonym number layout ${mode}/${width}: ${JSON.stringify(h)}`);
    }
    if(!record.heads[0].text.startsWith('abandon 1 /'))throw new Error(`Missing separators ${mode}/${width}`);
    records.push(record);
}
fs.writeFileSync(outputPath,JSON.stringify({passed:true,cases:records},null,2));
// End in the styled light theme for the review screenshot.
await evaluate("document.querySelectorAll('style').forEach(s=>s.disabled=false);document.body.style.backgroundColor='#fff';document.body.style.color='#111';document.body.style.setProperty('--text-color','#111');scrollTo(0,0)");
await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
const shot=await send('Page.captureScreenshot',{format:'png',clip:{x:0,y:0,width:900,height:700,scale:1}});
fs.writeFileSync(screenshotPath,Buffer.from(shot.data,'base64'));
ws.close();
console.log(JSON.stringify({passed:true,cases:records.length,screenshot:screenshotPath}));
