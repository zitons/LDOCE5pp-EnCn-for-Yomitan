"""Verify that an alias-rule upgrade retains previous query support."""
import argparse
import json
import re
import zipfile
from pathlib import Path


def keys(path):
    result=set()
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not re.fullmatch(r'term_bank_\d+\.json',name):continue
            for row in json.loads(z.read(name)):
                if row[2]=='source-context':continue
                value=' '.join(row[0].casefold().split())
                if ' ' in value:result.add(value)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('previous');ap.add_argument('current');ap.add_argument('output')
    args=ap.parse_args();out=Path(args.output)
    old=keys(args.previous);new=keys(args.current)
    assert not old-new,sorted(old-new)
    previous=json.loads((Path(args.previous).parent/'comparison/support_report.json').read_text(encoding='utf8'))
    current=json.loads((Path(args.current).parent/'comparison/support_report.json').read_text(encoding='utf8'))
    assert len(new)==current['dictionaries']['ldoce6']['normalized_useful_query_keys']
    result={'normalization':'casefold and whitespace only; source contexts excluded',
        'previous_queries':len(old),'current_queries':len(new),'added_queries':len(new-old),'lost_queries':0,
        'previous_only5':previous['query_overlap']['only5'],'current_only5':current['query_overlap']['only5'],
        'newly_covered_5_queries':previous['query_overlap']['only5']-current['query_overlap']['only5'],
        'current_only6':current['query_overlap']['only6'],'current_shared':current['query_overlap']['shared'],
        'scope':'Query aliases only; canonical phrase extraction unchanged. Not a proof of linguistic correctness for every alias.'}
    (out/'upgrade_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'added_multiword_queries.txt').write_text('\n'.join(sorted(new-old))+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
