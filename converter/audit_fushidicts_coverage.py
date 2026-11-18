"""Measure full-query native hits for the remaining LDOCE5++ plural queries."""
import argparse
import csv
import json
from pathlib import Path
from probe_fushidicts import Engine


def norm(s):return ' '.join(s.casefold().replace('↔',' ').split())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dll',required=True);ap.add_argument('--package',required=True)
    ap.add_argument('--output',required=True);ap.add_argument('--transforms',required=True)
    ap.add_argument('--queries',required=True)
    args=ap.parse_args();out=Path(args.output);tf=Path(args.transforms)
    engine=Engine(args.dll,args.package,out,[tf/'en.json',tf/'en_irregular.json'])
    with Path(args.queries).open(encoding='utf-8-sig',newline='') as f:
        inputs=[r for r in csv.DictReader(f,delimiter='\t') if r['feature'] in {'08_regular_plural','05_separable_particle_reordering'}]
    rows=[]
    try:
        for i,r in enumerate(inputs):
            q=r['query'];targets=r['targets'].split(' | ')
            expected={norm(t) for t in targets}
            for target in targets:
                expected.update(norm(x['expression']) for x in engine.lookup(target,128) if norm(x['matched'])==norm(target))
            hit={}
            for scan in [16,128]:
                hit[scan]=any(norm(x['matched'])==norm(q) and norm(x['expression']) in expected for x in engine.lookup(q,scan))
            rows.append([q,r['targets'],r['feature'],int(hit[16]),int(hit[128])])
            if (i+1)%500==0:print(f'queried {i+1}/{len(inputs)}',flush=True)
    finally:engine.close()
    with (out/'coverage.tsv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter='\t');w.writerow(['query','targets','category','hit16','hit128']);w.writerows(rows)
    report={cat:{'queries':len(group),'full_target_hit16':sum(r[3] for r in group),'full_target_hit128':sum(r[4] for r in group)}
        for cat in sorted({r[2] for r in rows}) if (group:=[r for r in rows if r[2]==cat])}
    (out/'coverage_report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
