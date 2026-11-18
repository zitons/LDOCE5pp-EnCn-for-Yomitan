# Fushi 短语查询缺口（r4 实测）

2026-11-18。使用原版 fushidicts DLL、真实导入器和隔离测试库。包 SHA256：`d42a44f54c6559d5d6857ebba2e13df3605563b5f1b7b14039d4cb87f2b2ee96`。

54 例探针中，52 例的规范目标存在且可直接查询；扫描长度 16 / 128 时完整目标命中 22 / 34。另 2 例缺少完整源模式。固定探针不是全词典覆盖率；扫描长度由测试主动指定，不代表所有 UI 调用的默认值。

## 可考虑改进引擎的 18 例

这些案例均已验证源规范目标存在。短前缀命中不算成功，完整命中到其他短语（如 take away）也不算成功。

| 输入 | 预期目标 | 类型 |
|---|---|---|
| give Mary a hand | give (somebody) a hand | generic_object |
| give your brother a hand | give (somebody) a hand | generic_object |
| pull Mary's leg | pull somebody's leg | generic_possessive |
| break Mary's heart | break somebody's heart | generic_possessive |
| cross Mary's mind | cross somebody's mind | generic_possessive |
| get on Mary's nerves | get on somebody's nerves | generic_possessive |
| take Mary's breath away | take somebody's breath away | particle_semantic_collision |
| pick the man in red up | pick up | particle_boundary |
| gave Mary a hand | give (somebody) a hand | generic_object |
| caught the thief red-handed | catch somebody red-handed | generic_object |
| pulled John's leg | pull somebody's leg | generic_possessive |
| broke the girl's heart | break somebody's heart | generic_possessive |
| at the taxpayer's expense | at somebody's expense | generic_possessive |
| put her foot firmly down | put your foot down | inserted_modifier |
| gave him a helping hand | give (somebody) a hand | inserted_modifier |
| made up her own mind | make up your mind/make your mind up | inserted_modifier |
| his leg was being pulled | pull somebody's leg | passive_or_reordered |
| the hatchet was buried | bury the hatchet/bury your differences | passive_or_reordered |

可以研究受约束的宾语/所有格槽位、宾语内部小品词边界、有限修饰插入、被动和调序匹配。应限制候选数量并保留具体习语目标，避免只返回较泛的短语动词。这里没有实施引擎修改或发起 PR。

## 源范围与旧报告更正

`drove his mother up the wall`、`drove her up the wall` 所期待的 `drive somebody up the wall` 没有被提取为完整规范词条；当前词典有 `up the wall`。两例单列为 source_pattern_absent，不能据此归因于通用槽位引擎。

`took the kids by surprise` 和 `took them by surprise` 在 128 时均能命中正确目标 `take somebody/something by surprise`。旧探针错将查询别名 `take somebody by surprise` 当作规范目标，误报为失败。因此本次 128 命中数由 32 修正为 34，词典包没有变化。

## 扫描与复数

12 例在扫描长度 16 时失败、128 时成功，包括 put her foot down 和 hanging by a thread。应先核对扫描配置。

2,353 个复数查询在 16 / 128 时完整目标命中 2,048 / 2,340；57 个可分动词查询为 19 / 32。余下 13 个“复数”标签查询并非都是普通复数：包括 mercators projection 等所有格去标点写法、源仅标 singular 的 tour de force，以及源明确写 films noirs 而比较集要求 films noir。不可将差额全当作词形错误。

机器报告位于工程根目录的 `yomitan_phrases/2026.11.18-r4/engine_gaps/`：gap_probes.json、gap_probes.tsv、remaining_for_engine.tsv。后者还包含扫描限制及缺少源模式的案例，应结合 diagnosis / generic_engine_candidate 列使用。批量测试见同级的 coverage_report.json、coverage.tsv。

复跑脚本为实施工作区的 `converter/audit_fushidicts_gaps.py`，参数为 `--revision r4 --package <r4.zip> --import-dir <隔离导入目录> --output <报告目录> --dll <原版DLL> --transforms <Fushi transforms目录>`。
