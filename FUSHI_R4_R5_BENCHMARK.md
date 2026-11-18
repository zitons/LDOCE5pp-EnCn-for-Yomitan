# r4 / r5 Fushi 可行性对照实验

## 可行性结论

当前 r5 不能作为已验证的 r4 替代方案。独立样本按较宽的同文释义覆盖口径，r4 为 1,455/2,000 (72.75%)，r5 为 958/2,000 (47.90%)。删除策略造成实际用法回退，不能用规范词条控制组的 100% 掩盖。

r4 也不能原样视为正确最终版：10 个负例中错误接受指定目标 5 个，r5 为 1 个；being to do something 在两版均错误接受，说明有的宽泛还原发生在引擎层，并非仅来自词典别名。

本轮仅验证，不改生成规则、不发布新包。后续应优先依据来源例句和规则分层保留可靠通用展开；将槽位/词形确实无法处理的输入集中给引擎评估，不能再次全恢复或全关闭。

本轮只比较冻结词典包，不修改生成规则或补回别名。所有预期目标来自冻结的规范词条 ID，未用待测引擎返回结果定义答案。

## 测试范围与口径

- 同一原版 DLL、相同英文 transforms、各自隔离导入目录；两版查询使用相同输入与结果上限。
- 扫描长度分别为 16、128 和 full（max(128, 输入码点长度)）。完整输入组要求完整匹配；例句上下文组要求命中已定位的短语片段及其规范目标。
- 命中 give 等短前缀不算成功；完整匹配到另一个习语也不算成功。统计前 32 个结果内命中及第一位命中。
- 别名回放衡量索引覆盖，不等于语法正确率：r4 自身存在不合理生成入口，不能把它们全当作应保留项。
- 自然例句片段从两版索引的并集定位，并非独立标注语料；这种选择可能偏向 r4，不能外推为日常阅读的总体命中率。
- 23,506 个去重源例句中，15,244 个可定位；8,262 个未定位例句另存 unmatched_source_examples.jsonl，不算成功，也不混入定位后的分母。
- 58 个受控正例测试词形、代词、所有格、人名、可分结构、插入修饰及被动语序；10 个负例检查已知错误构式和错误目标。另 2 个缺少源规范目标的原探针单列。

## 各组命中数（严格规范目标 ID）

| 测试组 | 扫描 | r4 | r5 | r4成功而r5失败 | r5成功而r4失败 |
|---|---|---:|---:|---:|---:|
| 原始规范短语 | 16 | 18,926/32,889 (57.55%) | 18,926/32,889 (57.55%) | 0 | 0 |
| 原始规范短语 | 128 | 32,889/32,889 (100.00%) | 32,889/32,889 (100.00%) | 0 | 0 |
| 原始规范短语 | full | 32,889/32,889 (100.00%) | 32,889/32,889 (100.00%) | 0 | 0 |
| 两版保留的入口 | 16 | 15,275/33,912 (45.04%) | 15,275/33,912 (45.04%) | 0 | 0 |
| 两版保留的入口 | 128 | 33,912/33,912 (100.00%) | 33,912/33,912 (100.00%) | 0 | 0 |
| 两版保留的入口 | full | 33,912/33,912 (100.00%) | 33,912/33,912 (100.00%) | 0 | 0 |
| r5 删除的入口 | 16 | 90,926/306,454 (29.67%) | 9,075/306,454 (2.96%) | 81,851 | 0 |
| r5 删除的入口 | 128 | 306,454/306,454 (100.00%) | 20,522/306,454 (6.70%) | 285,932 | 0 |
| r5 删除的入口 | full | 306,454/306,454 (100.00%) | 20,522/306,454 (6.70%) | 285,932 | 0 |
| 源例句中的短语片段 | 16 | 12,421/15,244 (81.48%) | 8,093/15,244 (53.09%) | 4,328 | 0 |
| 源例句中的短语片段 | 128 | 15,244/15,244 (100.00%) | 9,490/15,244 (62.25%) | 5,754 | 0 |
| 源例句中的短语片段 | full | 15,244/15,244 (100.00%) | 9,490/15,244 (62.25%) | 5,754 | 0 |
| 源例句中的短语及后文 | 16 | 12,384/15,244 (81.24%) | 8,079/15,244 (53.00%) | 4,305 | 0 |
| 源例句中的短语及后文 | 128 | 15,187/15,244 (99.63%) | 9,474/15,244 (62.15%) | 5,713 | 0 |
| 源例句中的短语及后文 | full | 15,187/15,244 (99.63%) | 9,474/15,244 (62.15%) | 5,713 | 0 |
| 受控实际用法 | 16 | 22/58 (37.93%) | 8/58 (13.79%) | 14 | 0 |
| 受控实际用法 | 128 | 35/58 (60.34%) | 12/58 (20.69%) | 23 | 0 |
| 受控实际用法 | full | 35/58 (60.34%) | 12/58 (20.69%) | 23 | 0 |
| 负例控制（命中预期目标反而是错误） | 16 | 2/10 (20.00%) | 0/10 (0.00%) | 2 | 0 |
| 负例控制（命中预期目标反而是错误） | 128 | 5/10 (50.00%) | 1/10 (10.00%) | 4 | 0 |
| 负例控制（命中预期目标反而是错误） | full | 5/10 (50.00%) | 1/10 (10.00%) | 4 | 0 |

负例行的命中表示错误接受指定目标，不能当作正向成绩；这 10 例也不能估计全词典误报率。

## 删除入口按规则分组（full 窗口）

| 类别 | r4 | r5 |
|---|---:|---:|
| comma_order | 4,465/4,465 (100.00%) | 0/4,465 (0.00%) |
| constituent_omission | 8,339/8,339 (100.00%) | 0/8,339 (0.00%) |
| declared_variant | 162/162 (100.00%) | 0/162 (0.00%) |
| grouped_slash | 150/150 (100.00%) | 0/150 (0.00%) |
| noun_inflection | 6,483/6,483 (100.00%) | 5,575/6,483 (85.99%) |
| orthography | 3,321/3,321 (100.00%) | 0/3,321 (0.00%) |
| other | 565/565 (100.00%) | 0/565 (0.00%) |
| pos_slash | 5,172/5,172 (100.00%) | 5/5,172 (0.10%) |
| pronoun_substitution | 60,017/60,017 (100.00%) | 213/60,017 (0.35%) |
| verb_inflection | 217,780/217,780 (100.00%) | 14,729/217,780 (6.76%) |

分类按优先级去重；例如代词与动词词形的交叉组合计入 verb_inflection，大小写副本继承原入口的规则。

## 真实例句上下文回退样例

| 输入（从短语起点开始） | 预期规范目标 | r5 实际返回 |
|---|---|---|
| all by himself. | (all) by yourself | (all) by himself [all by himself]; all [all] |
| on my own for four years now. | (all) on your own | on [on] |
| on his own. | (all) on your own | on [on] |
| all on his own. | (all) on your own | all [all] |
| on my own, thanks. | (all) on your own | on [on] |
| to myself. | (all) to yourself | to [to] |
| go to the stake for it. | (be prepared to) go to the stake for/over something | go [go] |
| allied to the field of psychology. | (be) allied to/with something | allied [allied]; ally [allied] |
| in the tradition of Picasso and Matisse. | (be) in the tradition of somebody/something | in [in] |
| felt like a fish out of water in my new school. | (be/feel) like a fish out of water | felt [felt]; feel [felt] |
| courtesy of Blenheim Palace | (by) courtesy of somebody | courtesy [courtesy]; court [courtesy] |
| courtesy of Nicole's ice skate. | (by) courtesy of something | courtesy [courtesy]; court [courtesy] |
| came under the umbrella of the State Department. | (come/work etc) under the umbrella of something | come [came] |
| get ten out of ten for effort, Simon. | (get) ten out of ten (for something) | (get) ten out of ten (for something) [get ten out of ten]; get out [get ten out]; get [get] |
| goes hand in hand with madness. | (go) hand in hand | go in [goes hand in]; go [goes] |

## 第一位命中与耗时

| 测试组（full） | r4 第一位 | r5 第一位 |
|---|---:|---:|
| 原始规范短语 | 32,889/32,889 (100.00%) | 32,889/32,889 (100.00%) |
| 两版保留的入口 | 33,587/33,912 (99.04%) | 33,588/33,912 (99.04%) |
| r5 删除的入口 | 305,640/306,454 (99.73%) | 20,504/306,454 (6.69%) |
| 源例句中的短语片段 | 14,836/15,244 (97.32%) | 9,442/15,244 (61.94%) |
| 源例句中的短语及后文 | 14,356/15,244 (94.17%) | 9,302/15,244 (61.02%) |
| 受控实际用法 | 31/58 (53.45%) | 12/58 (20.69%) |

耗时为本次查询混合的原生 FFI 调用（含 JSON 解码开销），不含 memoization 命中；按案例交替两版调用先后顺序。它不代表 Flutter UI 延迟。

- r4: 799,853 次调用，均值 0.918 ms，P50 0.540 ms，P95 2.554 ms，P99 3.918 ms。
- r5: 799,853 次调用，均值 0.846 ms，P50 0.491 ms，P95 2.435 ms，P99 3.843 ms。

## 使用结论的边界

不得以全部 r4 别名的高命中率证明其语言正确，也不得以少数探针代表全部缺口。先根据规则分层和真实例句差异决定哪些通用展开值得保留，再做下一版；本实验不自动恢复或删除任何入口。

完整机器报告 report.json；冻结输入 cases.jsonl.gz；逐次结果 results.jsonl.gz；两版差异 regressions.tsv；文件哈希和参数 manifest.json。

## 独立源例句抽样（不按别名能否定位选样）

从全部 23,506 个去重源例句固定随机抽取相同的 2,000 个（seed=20261118），逐词起点查询。命中片段至少两词。此处称例句查回率，没有人工金标准边界，未命中不全是引擎错误。

| 评分口径 | 扫描 | r4 | r5 | 只有r4成功 | 只有r5成功 |
|---|---|---:|---:|---:|---:|
| 严格目标 ID | 16 | 1,167/2,000 (58.35%) | 753/2,000 (37.65%) | 414 | 0 |
| 严格目标 ID | 128 | 1,390/2,000 (69.50%) | 873/2,000 (43.65%) | 517 | 0 |
| 允许来源释义覆盖 | 16 | 1,230/2,000 (61.50%) | 832/2,000 (41.60%) | 398 | 0 |
| 允许来源释义覆盖 | 128 | 1,455/2,000 (72.75%) | 958/2,000 (47.90%) | 497 | 0 |

来源释义覆盖口径接受同一规范 ID，或另一个短语词条包含目标的全部同文释义，且至少一条释义不少于 8 词。排除普通 source-context 父词条；这是保守的来源文本代理，不声称人工证明语义等价。所有放宽依据在 independent_source_definition_coverage/definition_coverage_evidence.json。

严格 ID 可能低估实用查回，例如 all by himself 返回 (all) by himself 而非 (all) by yourself。不能把严格 ID 差异一律叫作丢失释义；较宽口径仍显示显著的成对回退。

## 较宽口径仍回退的源例句样例

| 源例句 | 预期短语 | r4匹配片段 |
|---|---|---|
| I never throw clothes away. | throw something away | throw clothes away |
| Leaving the car unlocked is just an open invitation to thieves. | be an open invitation for/to somebody | an open invitation to |
| She fancies herself as another Madonna. | fancy yourself (as) something | fancies herself as |
| Susan looked after us very well. She's an excellent cook. | look after somebody/something | looked after us |
| He seized the opportunity to put the ball away. | put somebody/something away | put the ball away |
| I did ask a few questions, but nothing came of it. | come of something | came of it |
| the government's plans to shake up the educational system | shake somebody/something up | shake up |
| A forum was set up to deal with all issues appertaining to Everton Park. | appertain to something | appertaining to |
| Bernard's wife kicked him out. | kick somebody out | kicked him out |
| I felt completely out of my depth at the meeting. | be out of your depth | out of my depth |
| Thousands of men were rounded up and jailed. | round somebody/something up | rounded up |
| We have to drive down costs. | drive something down | drive down |
| a country boy who made good in New York | make good | made good |
| He ended his days in prison. | end your days | ended his days |
| Cliff couldn't stand up to bullying. | stand up to somebody/something | stand up to |

## 工程位置与复跑

产物均位于工程根目录 `_tmp/r4-r5-fushi-benchmark/`。主报告 report.json；输入 cases.jsonl.gz；逐次评分 results.jsonl.gz；差异 regressions.tsv；两组独立抽样报告在 independent_source_examples/ 和 independent_source_definition_coverage/。两组抽样输入 SHA256 相同，所有词典包 SHA256 在实验后再次核验未变。

在实施工作区运行以下命令，可重跑相同口径：

```powershell
$r = 'C:\workspace\ldoce'
$py = "$r\venv\Scripts\python.exe"
$r4 = "$r\yomitan_phrases\2026.11.18-r4\LDOCE6_Phrases_2026.11.18-r4.zip"
$r5 = "$r\yomitan_phrases\2026.11.18-r5\LDOCE6_Phrases_2026.11.18-r5.zip"
$dll = "$r\_tmp\fushi-engine-build\Release\fushidicts_ffi.dll"
$tf = 'C:\workspace\fushi\fushi\assets\transforms'
$out = "$r\_tmp\r4-r5-fushi-benchmark"
& $py -X utf8 converter/benchmark_phrase_versions.py --r4 $r4 --r5 $r5 --dll $dll --transforms $tf --output $out
& $py -X utf8 converter/benchmark_phrase_source_examples.py --r4 $r4 --r5 $r5 --dll $dll --transforms $tf --output "$out\independent_source_examples"
& $py -X utf8 converter/benchmark_phrase_source_examples.py --r4 $r4 --r5 $r5 --dll $dll --transforms $tf --output "$out\independent_source_definition_coverage" --allow-source-definition-coverage
& $py -X utf8 converter/summarize_phrase_benchmark.py $out
```
