/** Actual Yomitan English rules + actual full-bank metadata, in-memory lookup.
 * Uses the same conditionsMatch as Translator._matchEntriesToDeinflections.
 * Tests complete input strings; not an extension/IndexedDB integration test.
 * No source or package changes: counterfactual fixes only affect in-memory flags.
 */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {LanguageTransformer} from '../../yomitan-ext/js/language/language-transformer.js';
import {englishTransforms} from '../../yomitan-ext/js/language/en/english-transforms.js';

const {rows,pos_reference:posRef}=JSON.parse(readFileSync(new URL('./lookup_rows.json',import.meta.url),'utf8'));
const byWord=new Map();
const union=new Map();
for (const row of rows) {
    const [word,rules,targets]=row;
    if (!byWord.has(word)) byWord.set(word,[]);
    byWord.get(word).push(row);
    if (targets===null) {
        if (!union.has(word)) union.set(word,new Set());
        for (const r of rules.split(' ').filter(Boolean)) union.get(word).add(r);
    }
}
const lt=new LanguageTransformer();
lt.addDescriptor(englishTransforms);
function lookup(query,fix='none') {
    const hits=new Set();
    for (const candidate of lt.transform(query)) {
        for (const [word,raw,targets] of byWord.get(candidate.text)||[]) {
            let rules=raw.split(' ').filter(Boolean);
            if (fix==='alias-union' && targets!==null) {
                rules=[...new Set(targets.flatMap(t=>[...(union.get(t)||[])]))];
            }
            if (fix==='POS' && targets===null && word in posRef) rules=posRef[word].split(' ').filter(Boolean);
            const flags=lt.getConditionFlagsFromPartsOfSpeech(rules);
            if (!LanguageTransformer.conditionsMatch(candidate.conditions,flags)) continue;
            if (targets===null) hits.add(word);
            else {
                // Dictionary redirects use conditions=0 and resolve to content rows.
                for (const t of targets) if (union.has(t)) hits.add(t);
            }
        }
    }
    return [...hits].sort();
}
const cases=["bailout's","add-on's","bail-out's","programming's","amen's",'children','ran','improving'];
const results=cases.map(query=>({query,current:lookup(query),alias_union_only:lookup(query,'alias-union'),POS_only:lookup(query,'POS')}));
console.log(JSON.stringify({partsOfSpeechFilter:true,scope:'full-input exact candidates (no substring fallback)',results},null,2));
// These are genuine content rows in this dictionary, not redirect rows.
assert(lookup('children').includes('children'));
assert(lookup('ran').includes('ran'));
assert(lookup('improving').includes('improve'));
assert(!lookup("bailout's").includes('bail out'));
assert(lookup("bailout's",'alias-union').includes('bail out'));
assert(!lookup("amen's").includes('amen'));
assert(lookup("amen's",'POS').includes('amen'));
