// Validate EVERY bank with the exact precompiled AJV validators used by Yomitan.
// No modified schema, sampling, downloaded dependencies, or package writes.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import * as validators from '../../yomitan-ext/lib/validate-schemas.js';
import {ZipReader, Uint8ArrayReader, TextWriter, configure} from '../../yomitan-ext/lib/zip.js';
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
configure({useWebWorkers: false});
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const mapping = [
  [/^index\.json$/, 'dictionaryIndex'],
  [/^term_bank_\d+\.json$/, 'dictionaryTermBankV3'],
  [/^term_meta_bank_\d+\.json$/, 'dictionaryTermMetaBankV3'],
  [/^tag_bank_\d+\.json$/, 'dictionaryTagBankV3'],
];
for (const [, name] of mapping) if (typeof validators[name] !== 'function') throw new Error(`Missing validator ${name}`);
// Positive + negative controls ensure that the real validator is being invoked.
const sample = [['probe', '', '', '', 10, [{type: 'structured-content', content: {tag: 'span', content: 'word'}}], 0, '']];
if (!validators.dictionaryTermBankV3(sample)) throw new Error('Positive control rejected');
const bad = structuredClone(sample); bad[0][5][0].content.style = {display: 'none'};
if (validators.dictionaryTermBankV3(bad)) throw new Error('Illegal style negative control accepted');
const wrongSequence = structuredClone(sample); wrongSequence[0][6] = '0';
if (validators.dictionaryTermBankV3(wrongSequence)) throw new Error('Sequence type negative control accepted');
const result = {validator_sha256: sha(fs.readFileSync(path.join(root, 'yomitan-ext/lib/validate-schemas.js'))),
  controls: {valid: true, illegal_style_rejected: true, wrong_sequence_type_rejected: true}, packages: []};
const args = process.argv.slice(2);
let outputPath = path.join(here, 'results/official_schema.json');
if (args[0] === '--output') {
  if (args.length < 3) throw new Error('--output needs a filename and package paths');
  outputPath = path.resolve(args[1]); args.splice(0, 2);
}
if (!outputPath.startsWith(path.join(here, 'results') + path.sep)) throw new Error('Schema results must stay under audit results/');
const packages = args;
if (packages.length === 0) throw new Error('Provide explicit package paths');
for (const packageName of packages) {
  const started = performance.now(); const filename = path.resolve(packageName);
  const bytes = fs.readFileSync(filename);
  const rec = {path: filename, sha256: sha(bytes), bytes: bytes.length, files: [], failures: []};
  const reader = new ZipReader(new Uint8ArrayReader(new Uint8Array(bytes)));
  try {
    const entries = await reader.getEntries();
    if (new Set(entries.map(e => e.filename)).size !== entries.length) rec.failures.push({duplicate_zip_members: true});
    for (const entry of entries) {
      const matched = mapping.find(([pattern]) => pattern.test(entry.filename));
      if (!matched) continue;
      const [ , name] = matched; const validator = validators[name];
      const text = await entry.getData(new TextWriter(), {checkSignature: true});
      const data = JSON.parse(text); const ok = validator(data);
      rec.files.push({file: entry.filename, validator: name, rows: Array.isArray(data) ? data.length : null, ok});
      if (!ok) rec.failures.push({file: entry.filename, errors: structuredClone(validator.errors)});
      console.log(path.basename(filename), entry.filename, Array.isArray(data) ? data.length : 1, ok ? 'PASS' : 'FAIL');
    }
  } finally { await reader.close(); }
  rec.seconds = +(performance.now() - started).toFixed(1) / 1000;
  result.packages.push(rec);
  fs.mkdirSync(path.dirname(outputPath), {recursive: true});
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2) + '\n');
}
console.log('Schema failures:', result.packages.reduce((n, p) => n + p.failures.length, 0));
if (result.packages.some(p => p.failures.length)) process.exitCode = 1;