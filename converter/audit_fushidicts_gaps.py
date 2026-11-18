"""Probe a real imported dictionary; prefix hits are not phrase recognition."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from probe_fushidicts import Engine

CASES = [
    ('generic_object', 'give Mary a hand', 'give (somebody) a hand'),
    ('generic_object', 'gave him a hand', 'give (somebody) a hand'),
    ('generic_object', 'give your brother a hand', 'give (somebody) a hand'),
    ('generic_object', 'give him a hand', 'give (somebody) a hand'),
    ('generic_object', 'give a hand', 'give (somebody) a hand'),
    ('head_inflection_without_particle', 'gave a hand', 'give (somebody) a hand'),
    ('head_inflection_without_particle', 'giving a hand', 'give (somebody) a hand'),
    ('generic_possessive', "pull Mary's leg", "pull somebody's leg"),
    ('generic_possessive', 'pull his leg', "pull somebody's leg"),
    ('head_inflection_without_particle', 'pulled his leg', "pull somebody's leg"),
    ('generic_possessive', "break Mary's heart", "break somebody's heart"),
    ('generic_possessive', 'break her heart', "break somebody's heart"),
    ('generic_possessive', "cross Mary's mind", "cross somebody's mind"),
    ('generic_possessive', 'cross my mind', "cross somebody's mind"),
    ('generic_possessive', "get on Mary's nerves", "get on somebody's nerves"),
    ('generic_possessive', 'get on my nerves', "get on somebody's nerves"),
    ('deictic_possessive', 'keep his head', 'keep your head'),
    ('deictic_possessive', 'put her foot down', 'put your foot down'),
    ('deictic_possessive', 'make up his mind', 'make up your mind/make your mind up'),
    ('particle_semantic_collision', "take Mary's breath away", "take somebody's breath away"),
    ('particle_semantic_collision', 'take my breath away', "take somebody's breath away"),
    ('positive_particle', 'picked John up', 'pick up'),
    ('positive_particle', 'picked it up', 'pick up'),
    ('positive_particle', 'took it all out', 'take something out'),
    ('positive_particle', 'look the word up', 'look up'),
    ('particle_boundary', 'pick the man in red up', 'pick up'),
    ('particle_boundary', 'pick Mary up', 'pick up'),
    ('scanner', 'hang by a thread', 'hang by a thread'),
    ('scanner', 'hanging by a thread', 'hang by a thread'),
    ('scanner', 'hang up your football boots', 'hang up your hat/football boots/briefcase etc'),
    ('scanner', 'keep your head above water', 'keep your head above water'),
    ('generic_object', 'gave Mary a hand', 'give (somebody) a hand'),
    ('generic_object', 'caught the thief red-handed', 'catch somebody red-handed'),
    ('generic_object', 'caught him red-handed', 'catch somebody red-handed'),
    ('generic_object', 'took the kids by surprise', 'take somebody/something by surprise'),
    ('generic_object', 'took them by surprise', 'take somebody/something by surprise'),
    ('generic_object', 'drove his mother up the wall', 'drive somebody up the wall'),
    ('generic_object', 'drove her up the wall', 'drive somebody up the wall'),
    ('generic_possessive', "pulled John's leg", "pull somebody's leg"),
    ('generic_possessive', "broke the girl's heart", "break somebody's heart"),
    ('generic_possessive', "behind Mary's back", "behind somebody's back"),
    ('generic_possessive', 'behind her back', "behind somebody's back"),
    ('generic_possessive', "at the taxpayer's expense", "at somebody's expense"),
    ('deictic_possessive', 'made up her mind', 'make up your mind/make your mind up'),
    ('deictic_possessive', 'kept his head above water', 'keep your head above water'),
    ('deictic_possessive', 'put his foot down', 'put your foot down'),
    ('inserted_modifier', 'hanging only by a thread', 'hang by a thread'),
    ('inserted_modifier', 'put her foot firmly down', 'put your foot down'),
    ('inserted_modifier', 'gave him a helping hand', 'give (somebody) a hand'),
    ('inserted_modifier', 'made up her own mind', 'make up your mind/make your mind up'),
    ('head_inflection_without_particle', 'leaps of faith', 'leap of faith'),
    ('head_inflection_without_particle', 'points of order', 'point of order'),
    ('passive_or_reordered', 'his leg was being pulled', "pull somebody's leg"),
    ('passive_or_reordered', 'the hatchet was buried', 'bury the hatchet/bury your differences'),
]

ARBITRARY = ('Mary', 'John', 'your brother', 'the man in red', 'the thief', 'the kids', 'his mother', "the girl's", "the taxpayer's")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision', default='r3')
    ap.add_argument('--package', required=True)
    ap.add_argument('--import-dir', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--dll', required=True)
    ap.add_argument('--transforms', required=True)
    args = ap.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    dll = Path(args.dll)
    transforms = Path(args.transforms)
    phrases = Path(args.package).parent / 'phrases.tsv'
    with phrases.open(encoding='utf-8-sig', newline='') as fh:
        source = {row['phrase']: row for row in csv.DictReader(fh, delimiter='\t')}
    engine = Engine(dll, args.package, args.import_dir,
                    [transforms / 'en.json', transforms / 'en_irregular.json'])
    try:
        cases = []
        for category, text, canonical in CASES:
            queries = {str(scan): engine.lookup(text, scan) for scan in (16, 128)}
            direct = engine.lookup(canonical, 128)
            cases.append({
                'category': category, 'input': text, 'input_codepoints': len(text),
                'expected_canonical': canonical, 'canonical_in_source_phrases': canonical in source,
                'canonical_direct_query': direct,
                'canonical_direct_full_hit': any(r['matched'] == canonical and r['expression'] == canonical for r in direct),
                'results': queries,
                'full_match_any': {s: any(r['matched'] == text for r in rows) for s, rows in queries.items()},
                'full_match_expected': {s: any(r['matched'] == text and r['expression'] == canonical for r in rows)
                                        for s, rows in queries.items()},
            })
        for case in cases:
            passed = case['full_match_expected']['128']
            category = case['category']
            if passed:
                case['diagnosis'] = ('scan_window_limit' if not case['full_match_expected']['16'] else 'positive_control')
                case['dictionary_scope'] = '目标入口已存在；无需新增相同别名。' if category == 'scanner' else '现有能力已成功；仍保留独立词典入口覆盖。'
            else:
                case['diagnosis'] = ('head_inflection_requires_phrasal_word' if category == 'head_inflection_without_particle' else
                                     'particle_boundary_inside_object' if category == 'particle_boundary' else
                                     'modifier_insertion' if category == 'inserted_modifier' else
                                     'passive_or_reordered' if category == 'passive_or_reordered' else
                                     'full_input_other_phrase_only' if case['full_match_any']['128'] else 'no_generic_slot_substitution')
                arbitrary = (case['category'] in ('inserted_modifier', 'passive_or_reordered') or any(s in case['input'] for s in ARBITRARY))
                case['dictionary_scope'] = ('可为这一个固定字面写法增加别名，但无法穷举任意名字或名词短语。'
                                            if arbitrary else '有限代词或所有格写法可通过明确的词典别名补充；待新包复测。')
                if category == 'head_inflection_without_particle':
                    case['dictionary_scope'] = '词典内可加动词头的有限实际词形入口；单加原形或代词别名不保证引擎能还原动词头。'
            source_valid = case['canonical_in_source_phrases'] and case['canonical_direct_full_hit']
            if not source_valid:
                case['diagnosis'] = 'source_pattern_absent'
                case['dictionary_scope'] = '完整目标未提取成规范词条，不能据此归因于引擎；需先核对源义项和提取范围。'
            case['engine_followup_candidate'] = source_valid and not passed and (case['category'] in ('inserted_modifier', 'passive_or_reordered') or any(s in case['input'] for s in ARBITRARY))
        report = {
            'revision': args.revision,
            'scope': 'Unmodified native DLL, real importer and native lookup; isolated imported phrase dictionary only, no app data or UI.',
            'dll_sha256': hashlib.sha256(dll.read_bytes()).hexdigest(),
            'import': engine.info, 'scans': [16, 128],
            'criteria': 'A shorter prefix such as give is not a phrase hit. A full-input hit on take away is not a hit on take somebody\'s breath away.',
            'source_references': {
                'head_inflection_gate': 'C:/workspace/fushi/native/fushidicts/fushidicts_src/deinflector.cpp:426',
                'object_removal': 'C:/workspace/fushi/native/fushidicts/fushidicts_src/deinflector.cpp:451',
                'first_phrasal_word_boundary': 'C:/workspace/fushi/native/fushidicts/fushidicts_src/deinflector.cpp:460',
                'candidate_lookup': 'C:/workspace/fushi/native/fushidicts/fushidicts_src/lookup.cpp:154',
                'scanner_contract': 'C:/workspace/fushi/native/fushidicts/fushidicts_src/scan/word_scan.hpp:9',
            },
            'limitations': [f'固定的{len(CASES)}例探针不是所有短语的覆盖率抽样。',
                            '仅导入本次短语包，未运行Flutter UI或用户安装词典组合。',
                            '16与128为主动传入的扫描长度；不假定全部UI调用都使用16。',
                            '这里只记录行为和归因，未修改Fushi、未实现通用匹配、未发PR。'],
            'reproduce_argv': [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()),
                               '--revision', args.revision, '--package', str(Path(args.package).resolve()),
                               '--import-dir', str(Path(args.import_dir).resolve()), '--output', str(output.resolve()),
                               '--dll', str(dll.resolve()), '--transforms', str(transforms.resolve())],
            'summary': {'cases': len(cases),
                        'source_valid_cases': sum(c['canonical_in_source_phrases'] and c['canonical_direct_full_hit'] for c in cases),
                        'source_pattern_absent': sum(c['diagnosis'] == 'source_pattern_absent' for c in cases),
                        'full_expected_16': sum(c['full_match_expected']['16'] for c in cases),
                        'full_expected_128': sum(c['full_match_expected']['128'] for c in cases)},
            'cases': cases,
        }
        (output / 'gap_probes.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        fields = ['category','input','expected_canonical','source_exists','canonical_query_ok','scan16_expected','scan128_expected','scan16_full_any','scan128_full_any','scan128_actual']
        with (output / 'gap_probes.tsv').open('w', encoding='utf8', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, delimiter='\t')
            writer.writeheader()
            for case in cases:
                writer.writerow(dict(zip(fields, [case['category'], case['input'], case['expected_canonical'],
                    case['canonical_in_source_phrases'], case['canonical_direct_full_hit'],
                    case['full_match_expected']['16'],case['full_match_expected']['128'],
                    case['full_match_any']['16'],case['full_match_any']['128'],
                    json.dumps(case['results']['128'], ensure_ascii=False)])))
        with (output / 'remaining_for_engine.tsv').open('w', encoding='utf-8-sig', newline='') as fh:
            names = ['input', 'expected_canonical', 'diagnosis', 'dictionary_scope', 'canonical_exists', 'scan16_expected', 'scan128_expected', 'scan128_actual', 'generic_engine_candidate']
            writer = csv.DictWriter(fh, fieldnames=names, delimiter='\t')
            writer.writeheader()
            for case in cases:
                if case['full_match_expected']['16'] and case['full_match_expected']['128']:
                    continue
                writer.writerow(dict(zip(names, [case['input'], case['expected_canonical'], case['diagnosis'],
                    case['dictionary_scope'], case['canonical_direct_full_hit'], case['full_match_expected']['16'],
                    case['full_match_expected']['128'], json.dumps(case['results']['128'], ensure_ascii=False),
                    case['engine_followup_candidate']])))
        print(json.dumps({'output':str(output),'cases':len(cases),'full_expected_16':sum(c['full_match_expected']['16'] for c in cases),
                          'full_expected_128':sum(c['full_match_expected']['128'] for c in cases)},ensure_ascii=False))
    finally:
        engine.close()


if __name__ == '__main__':
    main()
