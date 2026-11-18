"""Audit source coverage and export actual package examples for UI rendering."""
import argparse
import csv
import json
import sqlite3
import zipfile
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('build'); ap.add_argument('--baseline')
    args=ap.parse_args(); out=Path(args.build)
    db=sqlite3.connect(out/'extraction.sqlite')
    report=json.loads((out/'build_report.json').read_text(encoding='utf-8'))
    extract=json.loads((out/'extraction_report.json').read_text(encoding='utf-8'))
    expected={'records':52745,'phrasetext':71628,'lexunit':23148,'phrvbhwd':2392,'phrv':1230,'key':12966}
    assert all(extract[k]==v for k,v in expected.items()),extract
    actual={r[0] for r in db.execute('SELECT DISTINCT phrase FROM occurrences')}
    if args.baseline:
        with Path(args.baseline).open(encoding='utf-8-sig',newline='') as f:
            baseline={r['phrase_raw'] for r in csv.DictReader(f,delimiter='\t')}
        core={r[0] for r in db.execute("SELECT DISTINCT phrase FROM occurrences WHERE kind!='compound-key'")}
        assert core==baseline,{'missing':sorted(baseline-core),'extra':sorted(core-baseline)}
    probes=['hang by a thread','abandon ship','abandon yourself to something','camping gear/equipment',
            'do a 180','be hard on somebody','day after day/year after year etc','a hot date',
            "(hard/hot/close) on somebody's heels",'answer criticism/charges/accusations etc',
            'abandon','answer','act']
    entries={}; rowkeys=set(); sequences=set(); alias_count=0
    with zipfile.ZipFile(report['package']) as z:
        css=z.read('styles.css').decode('utf-8')
        for name in z.namelist():
            if not name.startswith('term_bank_'): continue
            for r in json.loads(z.read(name)):
                assert r[0] not in rowkeys,('duplicate key',r[0]); rowkeys.add(r[0])
                assert r[6] not in sequences,('duplicate sequence',r[6]); sequences.add(r[6])
                if r[4]<-5: alias_count+=1
                elif r[0] in probes and r[2] in {'phrase','source-context'}: entries[r[0]]=r[5][0]['content']
    assert 'hang by a thread' in entries
    assert alias_count==report['alias_entries']
    assert actual<=rowkeys,{'source_queries_missing':sorted(actual-rowkeys)}
    assert report['automatic_inflection_aliases'] is False
    assert report['finite_pronoun_aliases'] is False
    assert 'hanging by a thread' not in rowkeys
    assert "there's a good boy dog" not in rowkeys,'Ambiguous slash scope created a bogus phrase'
    assert 'hang up your hat boots etc' not in rowkeys,'Multiword slash boundary was lost'
    assert 'work up an appetite thirst sweat' not in rowkeys,'Repeated-article alternative was incorrectly expanded'
    positive=['hang by a thread','abandon ship','give (somebody) a hand',
              'self-explanatory','make up your mind','make your mind up']
    negative=['give him a hand','gave him a hand','how can me do something',
              'being to do something','a word in ear','re form',
              'Princess Di, Princess Diana, Lady Di','worked permit','gived him a hand',
              'kick out them','givens to doing','leaping of faith']
    # The original source really tags endear ... to ... as phrvbhwd. It is a
    # supported lookup core only in releases adopting source-phrasal heads.
    if report['alias_rules'].get('source_phrasal_argument_lookup_head'):
        assert db.execute("SELECT 1 FROM occurrences WHERE phrase=? AND kind='phrvbhwd'",
                          ('endear somebody to somebody',)).fetchone()
        positive.append('endear to')
    else:
        negative.append('endear to')
    assert all(k in rowkeys for k in positive),[k for k in positive if k not in rowkeys]
    assert not any(k in rowkeys for k in negative),[k for k in negative if k in rowkeys]
    entries=dict(sorted(entries.items(),key=lambda item:(item[0]!='abandon',item[0])))
    (out/'render_samples.json').write_text(json.dumps({'entries':entries,'css':css},ensure_ascii=False),encoding='utf-8')
    audit=dict(source_counts=extract,baseline_exact_match=bool(args.baseline),all_source_queries_retained=True,
               automatic_inflection_aliases=False,ambiguous_slash_negative_control=True,
               enhanced_positive_controls=positive,enhanced_negative_controls=negative,duplicate_keys=0,
               duplicate_sequences=0,package_rows=len(rowkeys),render_samples=len(entries))
    (out/'coverage_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
