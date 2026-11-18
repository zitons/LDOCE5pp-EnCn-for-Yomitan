"""Find dedicated-entry selection hiding same-spelling phrasal-verb bodies."""
import argparse
import json
import sqlite3
from pathlib import Path
from benchmark_phrase_versions import norm, read_package
from benchmark_phrase_source_examples import definitions


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--build',required=True)
    args=ap.parse_args()
    build=Path(args.build)
    package=json.loads((build/'build_report.json').read_text(encoding='utf8'))['package']
    bodies,_,_=read_package(package)
    db=sqlite3.connect('file:'+str(build/'extraction.sqlite')+'?mode=ro',uri=True)
    dedicated={p for p, in db.execute("SELECT DISTINCT phrase FROM occurrences WHERE kind IN ('key','compound-key')")}
    affected=[]
    for phrase,record_id,defs in db.execute("SELECT phrase,record_id,defs FROM occurrences WHERE kind='phrvbhwd'"):
        key=' '.join(phrase.replace('\u2194',' ').split())
        if key not in dedicated or key not in bodies:
            continue
        actual=set(definitions(bodies[key][5]))
        expected={norm(d).strip(' .') for d in json.loads(defs)}
        if expected-actual:
            affected.append({'phrase':key,'record_id':record_id,'source_definitions':len(expected),
                             'current_definitions':len(actual),'missing_definitions':sorted(expected-actual)})
    db.close()
    out=build/'diagnosis';out.mkdir(exist_ok=True)
    (out/'source_sense_shadowing.json').write_text(json.dumps(affected,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'source_body_candidates':len(affected),'phrases':sorted({x['phrase'] for x in affected})}))


if __name__=='__main__':main()
