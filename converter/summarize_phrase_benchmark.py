"""Summarize paired native results without changing dictionary rules."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def pct(hit, total):
    return f'{hit:,}/{total:,} ({100*hit/total:.2f}%)' if total else '-'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('directory');args=ap.parse_args()
    out=Path(args.directory);r=json.loads((out/'report.json').read_text(encoding='utf8'))
    totals=defaultdict(Counter)
    for row in r['results']:
        for key in ('cases','hit','top1','wrong_full_only','any_full','prefix_only'):
            totals[row['group'],row['scan'],row['version']][key]+=row.get(key,0)
    names={'canonical':'原始规范短语','retained_alias':'两版保留的入口','removed_alias':'r5 删除的入口',
           'source_span':'源例句中的短语片段','source_context':'源例句中的短语及后文',
           'controlled_positive':'受控实际用法','negative_control':'负例控制（命中预期目标反而是错误）'}
    lines=['# r4 / r5 Fushi 可行性对照实验','',
           '本轮只比较冻结词典包，不修改生成规则或补回别名。所有预期目标来自冻结的规范词条 ID，未用待测引擎返回结果定义答案。','',
           '## 测试范围与口径','',
           '- 同一原版 DLL、相同英文 transforms、各自隔离导入目录；两版查询使用相同输入与结果上限。',
           '- 扫描长度分别为 16、128 和 full（max(128, 输入码点长度)）。完整输入组要求完整匹配；例句上下文组要求命中已定位的短语片段及其规范目标。',
           '- 命中 give 等短前缀不算成功；完整匹配到另一个习语也不算成功。统计前 32 个结果内命中及第一位命中。',
           '- 别名回放衡量索引覆盖，不等于语法正确率：r4 自身存在不合理生成入口，不能把它们全当作应保留项。',
           '- 自然例句片段从两版索引的并集定位，并非独立标注语料；这种选择可能偏向 r4，不能外推为日常阅读的总体命中率。',
           '- 23,506 个去重源例句中，15,244 个可定位；8,262 个未定位例句另存 unmatched_source_examples.jsonl，不算成功，也不混入定位后的分母。',
           '- 58 个受控正例测试词形、代词、所有格、人名、可分结构、插入修饰及被动语序；10 个负例检查已知错误构式和错误目标。另 2 个缺少源规范目标的原探针单列。','',
           '## 各组命中数（严格规范目标 ID）','',
           '| 测试组 | 扫描 | r4 | r5 | r4成功而r5失败 | r5成功而r4失败 |',
           '|---|---|---:|---:|---:|---:|']
    paired={(x['group'],x['scan'],x['state']):x['count'] for x in r['paired']}
    for group in names:
        for scan in ('16','128','full'):
            a,b=totals[group,scan,'r4'],totals[group,scan,'r5']
            lines.append(f"| {names[group]} | {scan} | {pct(a['hit'],a['cases'])} | {pct(b['hit'],b['cases'])} | {paired.get((group,scan,'r4_only'),0):,} | {paired.get((group,scan,'r5_only'),0):,} |")
    lines+=['','负例行的命中表示错误接受指定目标，不能当作正向成绩；这 10 例也不能估计全词典误报率。','',
            '## 删除入口按规则分组（full 窗口）','','| 类别 | r4 | r5 |','|---|---:|---:|']
    categories=sorted({x['category'] for x in r['results'] if x['group']=='removed_alias'})
    for cat in categories:
        a=next(x for x in r['results'] if x['group']=='removed_alias' and x['category']==cat and x['scan']=='full' and x['version']=='r4')
        b=next(x for x in r['results'] if x['group']=='removed_alias' and x['category']==cat and x['scan']=='full' and x['version']=='r5')
        lines.append(f"| {cat} | {pct(a['hit'],a['cases'])} | {pct(b['hit'],b['cases'])} |")
    lines+=['','分类按优先级去重；例如代词与动词词形的交叉组合计入 verb_inflection，大小写副本继承原入口的规则。','',
            '## 真实例句上下文回退样例','', '| 输入（从短语起点开始） | 预期规范目标 | r5 实际返回 |','|---|---|---|']
    samples=next((x['samples'] for x in r['differences'] if x['group']=='source_context' and x['scan']=='full' and x['state']=='r4_only'),[])
    for x in samples[:15]:
        actual='; '.join(z['expression']+' ['+z['matched']+']' for z in x['r5']['actual'][:3]) or '空'
        lines.append('| '+x['query'].replace('|',r'\|')+' | '+', '.join(x['targets']).replace('|',r'\|')+' | '+actual.replace('|',r'\|')+' |')
    lines+=['','## 第一位命中与耗时','','| 测试组（full） | r4 第一位 | r5 第一位 |','|---|---:|---:|']
    for group in ('canonical','retained_alias','removed_alias','source_span','source_context','controlled_positive'):
        a,b=totals[group,'full','r4'],totals[group,'full','r5']
        lines.append(f"| {names[group]} | {pct(a['top1'],a['cases'])} | {pct(b['top1'],b['cases'])} |")
    lines+=['','耗时为本次查询混合的原生 FFI 调用（含 JSON 解码开销），不含 memoization 命中；按案例交替两版调用先后顺序。它不代表 Flutter UI 延迟。','']
    for v,d in r['latency'].items():
        lines.append(f"- {v}: {d['native_calls']:,} 次调用，均值 {d['mean_ms']:.3f} ms，P50 {d['p50_ms']:.3f} ms，P95 {d['p95_ms']:.3f} ms，P99 {d['p99_ms']:.3f} ms。")
    lines+=['','## 使用结论的边界','',
            '不得以全部 r4 别名的高命中率证明其语言正确，也不得以少数探针代表全部缺口。先根据规则分层和真实例句差异决定哪些通用展开值得保留，再做下一版；本实验不自动恢复或删除任何入口。','',
            '完整机器报告 report.json；冻结输入 cases.jsonl.gz；逐次结果 results.jsonl.gz；两版差异 regressions.tsv；文件哈希和参数 manifest.json。','']
    independent=[]
    for directory,label in [('independent_source_examples','严格目标 ID'),('independent_source_definition_coverage','允许来源释义覆盖')]:
        path=out/directory/'report.json'
        if path.exists(): independent.append((directory,label,json.loads(path.read_text(encoding='utf8'))))
    if independent:
        lines+=['## 独立源例句抽样（不按别名能否定位选样）','',
                '从全部 23,506 个去重源例句固定随机抽取相同的 2,000 个（seed=20261118），逐词起点查询。命中片段至少两词。此处称例句查回率，没有人工金标准边界，未命中不全是引擎错误。','',
                '| 评分口径 | 扫描 | r4 | r5 | 只有r4成功 | 只有r5成功 |','|---|---|---:|---:|---:|---:|']
        for directory,label,d in independent:
            for scan in ('16','128'):
                a=next(x for x in d['results'] if x['version']=='r4' and x['scan']==scan)
                b=next(x for x in d['results'] if x['version']=='r5' and x['scan']==scan)
                pairs={x['state']:x['count'] for x in d['paired'] if x['scan']==scan}
                lines.append(f"| {label} | {scan} | {pct(a['hit'],a['cases'])} | {pct(b['hit'],b['cases'])} | {pairs.get('r4_only',0)} | {pairs.get('r5_only',0)} |")
        lines+=['','来源释义覆盖口径接受同一规范 ID，或另一个短语词条包含目标的全部同文释义，且至少一条释义不少于 8 词。排除普通 source-context 父词条；这是保守的来源文本代理，不声称人工证明语义等价。所有放宽依据在 independent_source_definition_coverage/definition_coverage_evidence.json。','',
                '严格 ID 可能低估实用查回，例如 all by himself 返回 (all) by himself 而非 (all) by yourself。不能把严格 ID 差异一律叫作丢失释义；较宽口径仍显示显著的成对回退。','']
        wide=next((d for _,_,d in independent if d['manifest'].get('definition_coverage_enabled')),None)
        if wide:
            a=next(x for x in wide['results'] if x['version']=='r4' and x['scan']=='128')
            b=next(x for x in wide['results'] if x['version']=='r5' and x['scan']=='128')
            conclusion=['## 可行性结论','',
                        f"当前 r5 不能作为已验证的 r4 替代方案。独立样本按较宽的同文释义覆盖口径，r4 为 {pct(a['hit'],a['cases'])}，r5 为 {pct(b['hit'],b['cases'])}。删除策略造成实际用法回退，不能用规范词条控制组的 100% 掩盖。",'',
                        'r4 也不能原样视为正确最终版：10 个负例中错误接受指定目标 5 个，r5 为 1 个；being to do something 在两版均错误接受，说明有的宽泛还原发生在引擎层，并非仅来自词典别名。','',
                        '本轮仅验证，不改生成规则、不发布新包。后续应优先依据来源例句和规则分层保留可靠通用展开；将槽位/词形确实无法处理的输入集中给引擎评估，不能再次全恢复或全关闭。','']
            lines[2:2]=conclusion
            lines+=['## 较宽口径仍回退的源例句样例','', '| 源例句 | 预期短语 | r4匹配片段 |','|---|---|---|']
            selected=[c for c in wide['cases'] if c['results']['r4']['128'] and not c['results']['r5']['128']]
            for c in selected[:15]:
                lines.append('| '+c['example'].replace('|',r'\|')+' | '+c['target'].replace('|',r'\|')+' | '+c['results']['r4']['128']['matched'].replace('|',r'\|')+' |')
            lines.append('')
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps({'groups':{g:{v:dict(totals[g,'full',v]) for v in ('r4','r5')} for g in names}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
