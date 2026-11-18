# Fushi 短语查询缺口（r5）

2026-11-18；替代 r4 清单。使用原版 DLL、真实导入器和隔离词典库，不修改引擎。

54 个定向案例中，52 个源规范目标有效；扫描长度 16 / 128 时命中 8 / 11。41 个有源目标但未命中的案例集中列在下面；另 2 个缺少完整源模式。固定案例不代表全词典覆盖率，16/128 为测试主动指定的扫描配置。

## 集中汇报：41 个引擎未命中的输入

这些例子不再通过词典中的人称枚举、词形组合或任意删除成分来补。短前缀命中或命中别的短语不算成功。

| 输入 | 预期源规范目标 | 类型 |
|---|---|---|
| give Mary a hand | give (somebody) a hand | generic_object |
| gave him a hand | give (somebody) a hand | generic_object |
| give your brother a hand | give (somebody) a hand | generic_object |
| give him a hand | give (somebody) a hand | generic_object |
| gave a hand | give (somebody) a hand | head_inflection_without_particle |
| giving a hand | give (somebody) a hand | head_inflection_without_particle |
| pull Mary's leg | pull somebody's leg | generic_possessive |
| pull his leg | pull somebody's leg | generic_possessive |
| pulled his leg | pull somebody's leg | head_inflection_without_particle |
| break Mary's heart | break somebody's heart | generic_possessive |
| break her heart | break somebody's heart | generic_possessive |
| cross Mary's mind | cross somebody's mind | generic_possessive |
| cross my mind | cross somebody's mind | generic_possessive |
| get on Mary's nerves | get on somebody's nerves | generic_possessive |
| get on my nerves | get on somebody's nerves | generic_possessive |
| keep his head | keep your head | deictic_possessive |
| put her foot down | put your foot down | deictic_possessive |
| make up his mind | make up your mind/make your mind up | deictic_possessive |
| take Mary's breath away | take somebody's breath away | particle_semantic_collision |
| take my breath away | take somebody's breath away | particle_semantic_collision |
| took it all out | take something out | positive_particle |
| pick the man in red up | pick up | particle_boundary |
| hang up your football boots | hang up your hat/football boots/briefcase etc | scanner |
| gave Mary a hand | give (somebody) a hand | generic_object |
| caught the thief red-handed | catch somebody red-handed | generic_object |
| caught him red-handed | catch somebody red-handed | generic_object |
| took the kids by surprise | take somebody/something by surprise | generic_object |
| took them by surprise | take somebody/something by surprise | generic_object |
| pulled John's leg | pull somebody's leg | generic_possessive |
| broke the girl's heart | break somebody's heart | generic_possessive |
| behind Mary's back | behind somebody's back | generic_possessive |
| behind her back | behind somebody's back | generic_possessive |
| at the taxpayer's expense | at somebody's expense | generic_possessive |
| made up her mind | make up your mind/make your mind up | deictic_possessive |
| kept his head above water | keep your head above water | deictic_possessive |
| put his foot down | put your foot down | deictic_possessive |
| put her foot firmly down | put your foot down | inserted_modifier |
| gave him a helping hand | give (somebody) a hand | inserted_modifier |
| made up her own mind | make up your mind/make your mind up | inserted_modifier |
| his leg was being pulled | pull somebody's leg | passive_or_reordered |
| the hatchet was buried | bury the hatchet/bury your differences | passive_or_reordered |

可研究的通用能力：宾语与所有格槽位、反身代词/所有格与主语关系、动词头还原、宾语内部小品词边界、修饰插入，以及被动/调序。这里仅汇报行为，没有实现或承诺这些引擎功能。

## 另外两类问题

3 个案例在扫描长度 16 时失败、128 时成功，应先核对扫描配置。`drove his mother up the wall`、`drove her up the wall` 所期待的完整源模式未被提取，单列为 source_pattern_absent，不能归因于槽位匹配。

2,353 个复数查询在 16 / 128 时命中 2,048 / 2,340，和 r4 相同；删除自动复数展开没有降低这组真实查询的命中数。57 个可分动词查询命中 15 / 25。

报告均在工程根目录 `yomitan_phrases/2026.11.18-r5/`：engine_gaps/gap_probes.json、engine_gaps/gap_probes.tsv、engine_gaps/remaining_for_engine.tsv、coverage_report.json 和 coverage.tsv。remaining_for_engine.tsv 同时保留扫描限制和源模式缺失，应结合 diagnosis / generic_engine_candidate 列使用。

复跑脚本：实施工作区的 `converter/audit_fushidicts_gaps.py`；参数为 `--revision r5 --package <r5.zip> --import-dir <隔离目录> --output <报告目录> --dll <原版DLL> --transforms <transforms目录>`。
