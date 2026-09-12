"""Read-only corpus audit: independent DOM POS extraction and inflection content.

Run from repo root with venv/Scripts/python.exe converter/audit_2026_09_12/source_probe.py.
Only writes evidence alongside this script, using the project's atomic writer.
"""
import collections
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'converter'))
import ldoce2yomitan as M
import _apply_patch as patch
from bs4 import BeautifulSoup
from lxml import html


def write_json(name, data):
    patch.P = str(OUT / name)
    patch.write_atomic(json.dumps(data, ensure_ascii=False, indent=2))


def cls(e):
    return set((e.get('class') or '').split())


def text(e, skip_portrait=True):
    parts = []
    if e.text:
        parts.append(e.text)
    for ch in e:
        if isinstance(ch.tag, str) and not (skip_portrait and 'portrait' in cls(ch)):
            parts.append(text(ch, skip_portrait))
        if ch.tail:
            parts.append(ch.tail)
    return ''.join(parts)


def sc_text(n):
    if isinstance(n, str):
        return n
    if isinstance(n, list):
        return ''.join(map(sc_text, n))
    if isinstance(n, dict):
        return sc_text(n.get('content', ''))
    return ''


start = time.time()
stats = collections.Counter()
findings = collections.defaultdict(list)
fixtures = {}
pos_all = []
source_entries = collections.Counter()
forms = collections.Counter()
renderer = M.LdoceRenderer(M.TermIndex())
fixed_words = {'A','the','andante','Algeria','4-F','bad','be','age','backpedal',
               'run','love','heart','buy','lie','lay','rise','arise','child','children',
               'good','well','understand','read','foot','woman','mouse','sleep','thought'}
for record_i, (key, content) in enumerate(M.iter_records(ROOT / 'extract/LDOCE5++ V 2-15.mdx.txt')):
    key = M.strip_invisible(key).strip()
    kind, _ = M.classify_record(key, content)
    stats['records_' + kind] += 1
    if kind != 'entry':
        continue
    source_entries[key] += 1
    if key in fixed_words:
        fixtures.setdefault(key, []).append(content)
    dom = html.fromstring(content)
    spans = dom.iter('span')
    labels = []
    candidate_headings = []
    for el in spans:
        c = cls(el)
        if 'lm5pp_POS' in c:
            labels.append(text(el))
        if c & {'HEADING','SECHEADING','boxheader','spokensectheader'} and M.CJK_RE.search(text(el)):
            candidate_headings.append({'classes': sorted(c), 'text': M.collapse_ws(text(el))[:300]})
        if 'Inflections' not in c:
            continue
        stats['inflection_spans'] += 1
        for child in el:
            forms.update(cls(child))
        pron_nodes = [ch for ch in el if 'PronCodes' in cls(ch) or 'PRON' in cls(ch)]
        if not pron_nodes:
            continue
        stats['inflections_with_direct_pronunciation'] += 1
        stats['direct_pronunciation_spans'] += len(pron_nodes)
        bs = BeautifulSoup(html.tostring(el, encoding='unicode', with_tail=False), M.HTML_PARSER)
        infl = bs.find('span', class_='Inflections')
        got = sc_text(renderer.render_inflections(infl))
        lost = []
        for p in pron_nodes:
            prons = [M.collapse_ws(text(ch)).strip() for ch in p.iter('span') if 'PRON' in cls(ch)]
            if not prons:
                prons = [M.collapse_ws(text(p)).strip().strip('/')]
            missing = [s for s in prons if s and s not in got]
            if missing:
                lost.extend(missing)
                stats['pronunciation_spans_missing_in_render'] += 1
        if lost:
            findings['inflection_pronunciation'].append({'word':key,'record':record_i,
                'source':M.collapse_ws(text(el)),'rendered':got,'missing':lost})
    p, f = M.extract_tags(content)
    actual = M.pos_tags_rules(p, f)
    reference = M.pos_tags_rules(labels, f)
    if actual != reference:
        stats['pos_mismatch_records'] += 1
        stats['pos_rule_mismatch_records'] += actual[1] != reference[1]
        item = {'word':key,'record':record_i,'actual':actual,'reference':reference,'labels':labels}
        pos_all.append(item)
        if len(pos_all) <= 12:
            print('POS', key, actual, '=>', reference, flush=True)
    if candidate_headings:
        findings['mono_heading_candidates'].append({'word':key,'record':record_i,'headings':candidate_headings})
    if stats['records_entry'] % 10000 == 0:
        print('scanned entries', stats['records_entry'], 'seconds', round(time.time()-start,1), flush=True)

findings['pos'] = pos_all
stats['unique_entries'] = len(source_entries)
stats['pos_mismatch_words'] = len({x['word'] for x in pos_all})
stats['inflection_pronunciation_missing_words'] = len({x['word'] for x in findings['inflection_pronunciation']})
stats['mono_heading_candidate_words'] = len({x['word'] for x in findings['mono_heading_candidates']})
summary = {'source':str(ROOT/'extract/LDOCE5++ V 2-15.mdx.txt'),
           'converter_sha256':hashlib.sha256((ROOT/'converter/ldoce2yomitan.py').read_bytes()).hexdigest(),
           'stats':dict(stats),'inflection_direct_child_classes':dict(forms),
           'elapsed_seconds':round(time.time()-start,2)}
write_json('source_summary.json', summary)
write_json('source_findings.json', dict(findings))
write_json('fixtures.json', fixtures)
print(json.dumps(summary, ensure_ascii=False, indent=2))
print('evidence', OUT)
