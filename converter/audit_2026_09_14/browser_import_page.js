// Actual Yomitan importer + IndexedDB + generator. Runs on a fresh local origin.
import {DictionaryImporter} from '/js/dictionary/dictionary-importer.js';
import {DictionaryDatabase} from '/js/dictionary/dictionary-database.js';
import {StructuredContentGenerator} from '/js/display/structured-content-generator.js';
import {DisplayContentManager} from '/js/display/display-content-manager.js';
import {LanguageTransformer} from '/js/language/language-transformer.js';
import {englishTransforms} from '/js/language/en/english-transforms.js';
import {addScopeToCss, addScopeToCssLegacy} from '/js/core/utilities.js';
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const mode = new URL(location.href).searchParams.get('mode');
const result = {mode, userAgent: navigator.userAgent, checks: [], render: {}, runtime_errors: []};
window.__auditState = {stage:'starting'};
window.addEventListener('error', e => result.runtime_errors.push(String(e.error || e.message)));
window.addEventListener('unhandledrejection', e => result.runtime_errors.push(String(e.reason)));
function check(value, name) { result.checks.push({name, ok:!!value}); assert(value, name); }
function luminance(rgb) { return rgb.map(v => {v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0); }
function contrast(a,b) { const x=luminance(a),y=luminance(b);return +( (Math.max(x,y)+.05)/(Math.min(x,y)+.05)).toFixed(3); }
function rgb(text) { return (text.match(/[0-9.]+/g)||[]).slice(0,3).map(Number); }
try {
  const db = new DictionaryDatabase(); await db.prepare();
  check((await db.getDictionaryInfo()).length === 0, 'fresh IndexedDB, no preexisting dictionaries');
  window.__auditState={stage:'loading-package'};
  const archive = await (await fetch('/package.zip')).arrayBuffer();
  result.package_sha256 = [...new Uint8Array(await crypto.subtle.digest('SHA-256', archive))].map(n=>n.toString(16).padStart(2,'0')).join('');
  const importer = new DictionaryImporter({getImageDetails(){throw new Error('Unexpected media requirement');}}, p => { window.__auditState={stage:'importing', progress:p}; });
  const started=performance.now();
  const imported=await importer.importDictionary(db, archive, {prefixWildcardsSupported:true,yomitanVersion:'0.0.0.0'});
  result.import_seconds=+( (performance.now()-started)/1000).toFixed(1);
  result.import_errors=imported.errors.map(e=>String(e.stack||e));
  check(imported.errors.length===0 && imported.result?.importSuccess, 'official importer succeeded without errors');
  const title=imported.result.title; const dictionaries=new Set([title]);
  result.import_counts=imported.result.counts;
  result.db_counts=await db.getDictionaryCounts([title],true);
  check(result.db_counts.total.terms===245933, 'all 245933 rows persisted in IndexedDB');
  check(result.db_counts.total.termMeta===5971, 'all 5971 frequency rows persisted');
  check(result.db_counts.total.tagMeta===33, 'all 33 tag rows persisted');
  window.__auditState={stage:'lookup'};
  const transformer=new LanguageTransformer();transformer.addDescriptor(englishTransforms);
  async function lookup(query) {
    const transforms=transformer.transform(query); const candidates=new Map();
    for(const candidate of transforms) {if(!candidates.has(candidate.text))candidates.set(candidate.text,[]);candidates.get(candidate.text).push(candidate);}
    const rows=await db.findTermsBulk([...candidates.keys()],dictionaries,'exact'); const hits=new Set();const redirectTargets=[];
    for(const row of rows) {
      const flags=transformer.getConditionFlagsFromPartsOfSpeech(row.rules);
      if(!(candidates.get(row.term)||[]).some(c=>LanguageTransformer.conditionsMatch(c.conditions,flags)))continue;
      if(row.score>0)hits.add(row.term);
      else for(const d of row.definitions)if(Array.isArray(d))redirectTargets.push(d[0]);
    }
    if(redirectTargets.length)for(const row of await db.findTermsBulk([...new Set(redirectTargets)],dictionaries,'exact'))if(row.score>0)hits.add(row.term);
    return [...hits].sort();
  }
  result.lookups=[];
  for(const [query,expected] of [["bailout's",'bail out'],["amen's",'amen'],['children','children'],['ran','ran'],['improving','improve']]) {
    const hits=await lookup(query); result.lookups.push({query,expected,hits});check(hits.includes(expected),'lookup '+query+' -> '+expected);
  }
  const words=['act','come','come as a surprise/relief/blow etc (to somebody)','in vitro fertilization','none','not','need','for','approximate','hardly'];
  const rows=await db.findTermsBulk(words,dictionaries,'exact');
  result.sample_rows=rows.filter(r=>r.score>0).map(r=>({term:r.term,sequence:r.sequence,rules:r.rules}));
  let clickRequest=null;
  const manager=new DisplayContentManager({setContent(request){clickRequest=request;}});
  const generator=new StructuredContentGenerator(manager,document,window);
  const css=imported.result.styles;
  window.__auditState={stage:'rendering'};
  for(const environment of ['yomitan-light','yomitan-dark','anki-light','anki-dark','no-css-dark']) {
    const dark=environment.endsWith('dark');const section=document.createElement('section');
    section.dataset.auditEnvironment=environment;
    section.style.cssText=`padding:16px;margin:12px;max-width:620px;background:${dark?'#1e1e1e':'#ffffff'};color:${dark?'#d4d4d4':'#000000'};font:16px/1.5 Arial`;
    if(environment.startsWith('yomitan'))section.style.setProperty('--text-color',dark?'#d4d4d4':'#000000');
    const holder=document.createElement('div');holder.className='yomitan-glossary';
    const first=rows.find(r=>r.term==='act' && r.score>0); assert(first,'act row');
    holder.append(generator.createStructuredContent(first.definitions[0].content,title));section.append(holder);document.body.append(section);
    const scope=`[data-audit-environment="${environment}"] .yomitan-glossary`;
    if(!environment.startsWith('no-css')) {
      const style=document.createElement('style');style.textContent=environment.startsWith('anki')?addScopeToCssLegacy(css,scope):addScopeToCss(css,scope);document.head.append(style);
    }
    const root=holder.querySelector('[data-sc-class="ld"]'); const definition=holder.querySelector('[data-sc-class="ld-def"]');
    const computed=getComputedStyle(definition).color;
    result.render[environment]={root_color:getComputedStyle(root).color,definition_color:computed,background:getComputedStyle(section).backgroundColor,
      definition_contrast:contrast(rgb(computed),dark?[30,30,30]:[255,255,255]),text_color_variable:getComputedStyle(root).getPropertyValue('--text-color').trim(),
      sense_numbers:[...holder.querySelectorAll('[data-sc-class="ld-snum"]')].slice(0,16).map(n=>n.textContent.trim())};
  }
  for(const environment of ['anki-light','anki-dark']) {
    const colors=result.render[environment];
    check(colors.text_color_variable==='',environment+' really has no Yomitan theme variable');
    check(colors.definition_contrast>=4.3,environment+' exported CSS keeps readable body text');
    const expected=environment==='anki-dark'?'rgb(212, 212, 212)':'rgb(0, 0, 0)';
    check(colors.root_color===expected && colors.definition_color===expected,environment+' inherits host text color');
  }
  const firstDetails=document.querySelector('details');check(!!firstDetails,'details rendered');
  firstDetails.open=false;firstDetails.querySelector('summary').click();check(firstDetails.open,'summary click opens actual details');
  const link=document.querySelector('a[data-external="false"]');check(!!link,'internal query link rendered');
  const target=new URL(link.href).searchParams.get('query');link.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
  check(clickRequest?.params?.query===target && clickRequest.params.wildcards==='off','actual DisplayContentManager click preserves query and wildcard flag');
  const targetRows=await db.findTermsBulk([target],dictionaries,'exact');check(targetRows.length>0,'clicked query target exists in actual IndexedDB');
  result.link_check={target,rows:targetRows.length,request:clickRequest};
  const flat=n=>typeof n==='string'?n:Array.isArray(n)?n.map(flat).join(''):n&&typeof n==='object'?flat(n.content||''):'';
  result.split_word_examples=rows.filter(r=>['come','in vitro fertilization'].includes(r.term)).map(r=>({term:r.term,relieve_d:/\brelieve d\b/.test(flat(r.definitions)),fertilize_d:/\bfertilize d\b/.test(flat(r.definitions))}));
  const expectedRepairs=new Map([
    ['come',['relieved','relieve d']],
    ['come as a surprise/relief/blow etc (to somebody)',['relieved','relieve d']],
    ['in vitro fertilization',['fertilized','fertilize d']],
    ['none',['didn'+String.fromCharCode(0x2019)+'t get any','did n'+String.fromCharCode(0x2019)+'t get any']],
    ['not',['didn'+String.fromCharCode(0x2019)+'t know anybody','did n'+String.fromCharCode(0x2019)+'t know anybody']],
  ]);
  result.word_repairs=[];
  for(const [term,[correct,broken]] of expectedRepairs) {
    const matches=rows.filter(r=>r.term===term && r.score>0);
    const text=matches.map(r=>flat(r.definitions)).join(' ');
    const ok=matches.length>0 && text.includes(correct) && !text.includes(broken);
    result.word_repairs.push({term,ok,correct,broken});check(ok,'imported word repair '+term);
  }
  result.sample_has_cjk=rows.some(r=>/[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/.test(JSON.stringify(r.definitions)));
  if(mode==='mono')check(!result.sample_has_cjk,'imported mono sample contains no CJK');
  await db.close(); result.completed=true;
} catch(error) { result.completed=false; result.error=String(error.stack||error); }
window.__auditResult=result;window.__auditState={stage:'done',completed:result.completed};
console.log('AUDIT_RESULT',JSON.stringify(result));