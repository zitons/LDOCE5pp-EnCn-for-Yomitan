// Full import in real Chrome with isolated IndexedDB origins and a fresh profile.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));const root=path.resolve(here,'../..');
const out=path.resolve(process.argv[2] || path.join(here,'results/browser-import'));
if(!out.startsWith(path.join(here,'results')+path.sep))throw new Error('Browser artifacts must stay under audit results/');
fs.mkdirSync(out,{recursive:false});
const ext=path.join(root,'yomitan-ext');const servers=[];const results=[];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const modes=[
  ['bilingual',path.resolve(process.argv[3] || path.join(root,'yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip'))],
  ['mono',path.resolve(process.argv[4] || path.join(root,'yomitan_full/LDOCE5pp_Yomitan_2026.09.13_EN.zip'))],
];
for(const [mode,zip] of modes) {
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    if(pathname==='/') {res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end('<!doctype html><html><meta charset="utf-8"><title>Isolated dictionary audit</title><body><script type="module" src="/audit.js"></script></body></html>');return;}
    let file;
    if(pathname==='/package.zip')file=zip;
    else if(pathname==='/audit.js')file=path.join(here,'browser_import_page.js');
    else {file=path.resolve(ext,'.'+decodeURIComponent(pathname));if(!file.startsWith(ext+path.sep)){res.writeHead(403);res.end();return;}}
    if(!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
    const type={'.js':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css','.html':'text/html','.zip':'application/zip'}[path.extname(file)]||'application/octet-stream';
    res.writeHead(200,{'Content-Type':type,'Content-Length':fs.statSync(file).size});fs.createReadStream(file).pipe(res);
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  servers.push({mode,server,port:server.address().port});
}
const profile=path.join(out,'chrome-profile');
const chrome=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',[
  '--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-extensions',
  '--disable-background-networking','--disable-component-update','--disable-sync','--remote-debugging-port=0',
  '--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
const chromeLog=fs.createWriteStream(path.join(out,'chrome.log'));chrome.stderr.pipe(chromeLog);
let socket;let nextId=0;const pending=new Map();const events=[];
function send(method,params={}) {
  const id=++nextId;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout '+method));},60000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
}
try {
  const portFile=path.join(profile,'DevToolsActivePort');let port;
  for(let i=0;i<100;i++) {if(fs.existsSync(portFile)){port=+fs.readFileSync(portFile,'utf8').split('\n')[0];break;}if(chrome.exitCode!==null)throw new Error('Chrome exited '+chrome.exitCode);await sleep(200);}
  if(!port)throw new Error('No DevToolsActivePort; see chrome.log');
  const targets=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page=targets.find(t=>t.type==='page');if(!page)throw new Error('No Chrome page target');
  socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}}else if(m.method==='Runtime.exceptionThrown')events.push(m);};
  await send('Runtime.enable');await send('Page.enable');
  for(const {mode,port:originPort} of servers) {
    console.log('IMPORT',mode,'local origin port',originPort);
    await send('Page.navigate',{url:`http://127.0.0.1:${originPort}/?mode=${mode}`});
    let result;let lastStage='';
    for(let i=0;i<360;i++) {
      await sleep(5000);
      const response=await send('Runtime.evaluate',{expression:'JSON.stringify({state:window.__auditState,result:window.__auditResult})',returnByValue:true});
      if(!response.result?.value)continue;
      const data=JSON.parse(response.result.value);
      const stage=data.state?.stage||'loading';
      if(stage!==lastStage || i%12===0){console.log(mode,'stage',stage,data.state?.progress?.index||'');lastStage=stage;}
      if(data.result){result=data.result;break;}
    }
    if(!result)throw new Error('Import timed out for '+mode);
    results.push(result);fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({results,events},null,2)+'\n');
    console.log(mode,'completed',result.completed,'seconds',result.import_seconds,'error',result.error||'none');
    console.log('render',JSON.stringify(result.render));
    if(!result.completed)throw new Error(result.error||'Browser import assertions failed');
  }
} finally {
  fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({results,events},null,2)+'\n');
  if(socket?.readyState===1){try{await send('Browser.close');}catch{}socket.close();}
  if(chrome.exitCode===null)chrome.kill();
  for(const {server} of servers){server.closeAllConnections();server.close();}
  chromeLog.end();
}
console.log('Both actual browser imports and lookup/DOM checks completed.');