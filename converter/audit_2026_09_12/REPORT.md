# LDOCE5++ → Yomitan 当前版本审计（2026-09-12）

## 结论与实际审查范围

**审查对象包含当前构建实现，不只是构建后的 ZIP。** 本轮对当前源码进行了静态阅读、独立源数据探针、源码与交付包对比，以及真实 CLI 的隔离构建复现。

重点审查了：

- `build()`：Pass A 索引和别名规划、Pass B 渲染、同 key 多记录处理、元数据生成、ZIP 发布及校验失败处理。
- `LdoceRenderer`：词头、变形列表、释义、例句、折叠面板、词族、链接和 mono 分派。
- `extract_tags()` / `pos_tags_rules()`：词性和频率元数据提取、规则上限、规则继承。
- `validate_package()`：结构、链接、CSS 类、频率和 sequence 校验。
- 当前交付包是否反映上述实现，以及结构合法是否掩盖了语义缺陷。

结论是：**当前包结构检查通过，全量词条元数据及别名计划与当前实现一致，抽样重渲染一致；但存在 5 项功能/流程问题，另有 1 项序列号校验盲点。** 不应把这些通过项概括成“所有实现分支和内容都已验证正确”。

本轮没有重建正式双语包，也没有进行真实扩展安装和 UI 验收。未修改转换器、原始 MDX/MDD、正式 ZIP 或既有审计脚本。只在本审计目录新增报告、复现探针及本地证据。目录中的隔离测试 ZIP **不是交付物，请勿安装或发布**。

## 审计对象与版本

- Git：`2985637`；审计时产品代码无工作区差异。
- 转换器：`converter/ldoce2yomitan.py`，v1.1.0。
- 正式交付包：`yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip`，60,198,033 字节。
- 源数据：`extract/LDOCE5++ V 2-15.mdx.txt`。
- 转换器 SHA-256：`c5519d876b05c3d0464ac25432884e82042b15692374dd547e1e4e647ca3f1d7`。
- 正式 ZIP SHA-256：`15aaa3b8e821c1f741c008b55594a638fba45fb4034da3c5e3c41c56412442a3`。

上述两个哈希在审计后和修复本报告编码时均重新核对，保持不变。

## A1 [P1] 校验失败仍返回成功，失败包已覆盖合格包

**位置**：`converter/ldoce2yomitan.py:2636–2637, 2667–2682`。

`build()` 在校验之前就执行 `os.replace(zip_tmp, zip_path)`。发现校验错误后仅打印 `[FAIL]`，没有抛异常或返回失败状态；最后仍打印 `[OK] Dictionary package`，CLI 退出码为 **0**。

这会让依据退出码或最后一行 OK 判断结果的自动构建误发布失败产物，并失去上一份合格包。

**隔离构建实测**：

1. 从真实源数据取 `be`，在本轮隔离目录构建 mono 包：校验通过、退出码 0、包内无 CJK。
2. 同目录、同包名，改用真实 `age` 记录再次构建 mono 包。
3. 第二次日志明确包含 `term_bank_1.json: mono build contains CJK text`，但仍退出 0，并打印最后的 OK。
4. 两次 ZIP 路径相同、哈希不同，第二次包内确有中文。失败产物确实替换了合格产物。

该复现只使用 `isolated_mono_build/`，没有触碰正式交付目录。

证据：`build_be.log`、`build_age.log`、`targeted_results.json` 中的 `build_*` 和 `invalid_build_replaced_valid_zip`。

**建议**：先校验 `.part`，仅在无错误时发布到正式路径；失败时抛异常或返回非零退出码，不打印成功提示。通过 `try/finally` 保证 ZIP 关闭和 GC 阈值恢复。回归测试同时断言“失败退出码”和“旧合格包没有被替换”。

## A2 [P2] 同 key 多记录覆盖 rules，940 个别名丢失规则

**位置**：`converter/ldoce2yomitan.py:2524–2525, 2551–2554`。

全量包保留了 **269 个同表达式多记录**，但 `key_rules[k] = rules` 仅留下最后一条记录的规则。后续别名继承这个单值，而不是目标表达式全部内容行的规则并集。

对全部 **181,274 个别名**检查“目标内容行 rules 的并集”，发现 **940 行不完整**。目标行都存在，因此链接存在性校验抓不到此问题。

例：包内 `bail out` 两条内容行的 rules 分别为 `n v` 和 `v`，而别名 `bailout` 只有 `v`。启用默认 `partsOfSpeechFilter=true` 时，`bailout's → bailout` 的名词去词形候选被过滤。

用未修改的 Yomitan `LanguageTransformer` 和当前包全部元数据测试完整输入候选：

| 输入 | 当前规则 | 仅在内存中改为目标规则并集 |
|---|---|---|
| `bailout's` | 无完整输入命中 | `bail out` |
| `bail-out's` | 无完整输入命中 | `bail out` |
| `add-on's` | 无完整输入命中 | `add something ↔ on` |

这不等于真实 UI 一定什么都不显示：前缀回退或关闭词性筛选可能掩盖问题。但完整输入的候选链确实被错误规则切断。

证据：`package_results.json` 的 `alias_rules_not_union_of_target_rows`；`lookup_probe_verified.log`。

**建议**：按表达式稳定累积全部记录的 rules，别名再合并全部目标表达式的规则。添加多记录目标的回归用例。仅重放同一实现会复现同一覆盖错误，不能代替规则并集检查。

## A3 [P2] POS 正则被嵌套标签截断，显示修复没有覆盖元数据

**位置**：`converter/ldoce2yomitan.py:2064–2071`。

`POS_SCAN_RE` 使用 `(.*?)</span>`，遇到第一个内层闭合 span 就结束，无法提取完整的嵌套 `lm5pp_POS`。前一轮 D21 修的是词头显示 `_pick_landscape()`，而 `definitionTags` 和 `rules` 仍由旧正则提取。

本轮用独立 lxml DOM 遍历完整 POS，跳过 `portrait` 子树，再沿用现有映射和上限策略比较：

- **281 个词条**的元数据与完整 POS 的参考结果不一致；当前元数据已逐条在正式包中确认。
- 其中 **276 个词条缺少词性标签**。
- 其中 **203 个词条缺少至少一种去词形规则**。
- 281 不是全部都丢规则，也包括标签、顺序和上限截断造成的差异。

| 词条 | 当前包 | 完整 POS 的参考结果 |
|---|---|---|
| `andante` | tags=`noun adj`；rules=`n adj` | tags=`noun adj adv`；rules=`n adj adv` |
| `A` / `the` | 缺 `det` | 应保留 determiner 标签 |
| `above` | 缺 `prep` | 应保留 preposition 标签 |
| `amen` | tags 和 rules 均为空 | `noun` / `n` |

官方去词形器与当前包数据的完整输入测试中，`amen's` 当前无命中；仅在内存中补回 `amen` 的 `n` 后可命中。

证据：`source_findings.json` 的 `pos`、`targeted_content_findings.json` 的 `POS`、`lookup_probe_verified.log`。

**建议**：使用已有解析树或能追踪嵌套深度的扫描器读取完整 POS，统一排除 portrait；不再用非贪婪正则配对嵌套 span。同时验证显示文字、definitionTags 和 rules。

## A4 [P2] 变形列表丢掉文字音标，正式包至少影响 596 词条

**位置**：`converter/ldoce2yomitan.py:1149–1173`。

`render_inflections()` 的子元素分派只处理形态、GEO、LINKWORD/italic 等。`PronCodes` 不匹配这些分支；兜底虽遍历其内部 span，却只寻找形态类，因此其中的 `PRON` 和 `AMEVARPRON` 被丢弃。

源端直接调用 `render_inflections` 的探针发现 **609 词条、834 处发音块**有缺失。进一步将源 `.Head` 与正式包 `ld-head` 一一配对，检查对应词头中的音标，**保守确认至少 596 词条、816 个 PronCodes 发音块在交付包中缺失**，词头配对数量差异为 0。

正式影响范围采用后一种保守口径，统计单位是发音块，不是每个音标字符。

例：`bad` 的源头包含 `worse /wɜːs $ wɜːrs/`、`worst /wɜːst $ wɜːrst/`，当前包词头只剩 `comparative · worse · superlative · worst`；保留的 `/bæd/` 只是原形发音。`addendum → addenda /-də/` 和 `adman → admen /-men/` 也能复现。

**这是文字音标，不是音频资源**，不能用“SC 不支持 audio，已决定放弃音频”解释为有意删除。

证据：`source_summary.json`、`targeted_results.json`、`targeted_content_findings.json` 的 `inflection_IPA`。

**建议**：按源顺序保留变形列表中的 PronCodes/PRON/AMEVARPRON，复用现有音标样式，继续剥离音频按钮。检查形态与音标的归属、顺序，不只检查形态词是否存在。

## A5 [P2] mono 模式至少 243 个词条仍泄漏中文标题

**位置**：`converter/ldoce2yomitan.py:779–781, 1249–1255`。

`render_block_by_token()` 的标题分支以及 `render_box()` 的义项分组标题分支直接对整个标题调用 `get_text()`，把 `cn_txt` 拍平成普通字符串，绕过 mono 模式的中文子树过滤。

对全源中含中文分组或小标题的 **243 个候选词条**进行 mono 渲染，**243 个全部检出 CJK**。这是确认的下界，不是已经构建全库 mono 并证明只有这些词条。

- `age`：`– Meaning 5: a particular period of history 时代，世代`
- `bad`：`very bad 非常不好的`
- `run`：`animals running 动物跑`

真实 `age` 单记录的 CLI 构建已触发自带 mono 校验错误；与 A1 叠加后仍被标为成功。300 词冒烟包通过不能证明全量纯英文可交付。

证据：`targeted_content_findings.json` 的 `mono`、`targeted_results.json`、`build_age.log`。

**建议**：标题也经过 mode-aware 子树处理，按源类名剔除中文并保留英文，不用全局删除 CJK 字符掩盖分派问题。增加 `age/bad/run` 回归用例，修复后验证全量 mono。

## A6 [低优先级·门禁盲点] 重复 sequence 被当作合法连续序列

**位置**：`converter/ldoce2yomitan.py:2318–2323`。

校验只比较 `len(set(sequences)) == max(sequence) + 1`，没有与行数比较。隔离构造两条不同表达式、sequence 都为 `0` 的包，校验返回 `errors=[]`、`sequence_ok=1`。

**当前正式包没有此问题**：本轮独立验证了 `sorted(sequence) == list(range(245933))`。这是项目“唯一且从 0 连续”约束的回归防线缺口，不能描述为当前包已有重复序号。Format-3 Schema 也不代替这个更严格的项目约束。

证据：`duplicate_sequence.zip`；`targeted_results.json` 的 `duplicate_sequence_mutation`。

**建议**：同时检查唯一值数量等于行数、最小值为 0、最大值为行数减一，或比较完整目标集合；补充重复值和缺零的负例。

## 本轮实际通过的检查

| 检查 | 结果 |
|---|---|
| ZIP CRC 与重复成员名 | 无失败、无重复 |
| 全量行数 | 245,933 = 64,659 内容行 + 181,274 别名行 |
| 内容表达式 | 64,390 个唯一 key；269 个重复表达式分别保留 |
| 独立结构扫描 | SC tag/key、样式属性、href 无异常；链接和别名目标均存在；无内容行和别名行相互遮蔽 |
| 独立序列号检查 | 0..245932，唯一且连续 |
| 构建内嵌校验器 | 245,933 行通过；1,949,979 个 query 链接无悬挂 |
| 官方 Schema | index/tag/meta 全量；term 50,402 行（20% 分层抽样加极值），零失败；不是全量 term Schema |
| 频率元数据 | 5,971 行，与 definitionTags 中的频率码集合双向一致 |
| 源码与包元文件 | CSS 与当前 generate_css() 相同；tag bank 与当前 build_tag_bank() 相同 |
| 源码与包词条元数据 | 全部 64,659 内容行的表达式、tags、rules 和行序一致 |
| 源码与包别名计划 | 全部别名集合、规则和目标按当前实现重放一致；这不代表 A2 的语义正确 |
| 源码与包重渲染 | 1,096 行结构逐项一致，包含同 key 多记录的所有行、随机样本、极值及指定词；使用 sequence 区分记录 |
| 词头污染回归 | 64,659 内容行，零污染 |
| Yomitan 真 SC 生成器 | 1,096/1,096 成功；249,062 DOM 元素、57,568 链接、零个缺 summary 的 details |
| 去词形条件测试 | 官方英文变换器加当前全包元数据，复现 A2/A3；`improving → improve` 等对照成立 |

真生成器脚本副本与 `yomitan-ext/js/display/structured-content-generator.js` 的 SHA-256 相同：
`0cb3a0d65852ae30241a8da196acff6e2cedeab5ee1e7143d741116d8bee269d`。

重渲染比较是 JSON 行结构一致性，不是整个 ZIP 二进制逐字节可复现性测试。上述结果来自本轮重新执行，而不是引用旧审计日志。

## 验证边界和探针自身的修正

- 没有真实扩展安装或 IndexedDB 导入验收，没有真浏览器中的深浅主题、排版、折叠交互或 Anki 导出验收。
- jsdom 真生成器只证明生成器兼容性，不能证明浏览器 CSS 布局或整个扩展流程正确。
- 查词探针使用官方变换器、条件匹配方法和当前包元数据，在内存中模拟完整输入的精确候选查找，不覆盖前缀回退和真实数据库。
- `children` 和 `ran` 在本词典中有自己的内容行，不是必须重定向到 `child` 和 `run` 的别名。探针初版曾做了该错误断言，已依据当前包修正；最终结果见 `lookup_probe_verified.log`，而不是初版日志。
- 没有重建正式双语包，也没有生成并验收全量 mono；源码和正式包哈希不变。
- 旧文档中的计数、文件名和主题说明不是本轮依据。已有降级链接、源 key 卫生等旧问题没有重复算成新发现。

## 报告编码事故与修复

这份报告的第一版存在**真正的数据丢失，不是显示乱码**。复核原始字节得到：8,026 字节、非 ASCII 字节 0、中文字符 0、ASCII 问号 `?`（0x3F）2,929 个。

原因是生成报告的命令运行在 Windows PowerShell 5.1 中，`$OutputEncoding` 为 `us-ascii`，并使用替换式编码回退。中文 here-string 通过管道传给 Python 时已被替换；之后即便 `write_atomic()` 用 UTF-8 写入，也无法恢复被替换的内容。只设置 `PYTHONIOENCODING=utf-8` 不足以修复前面的 PowerShell 管道。

第一版已经不可逆丢字，不能靠重新解码或改编码声明恢复。本版从原报告内容重新生成：

1. 在产生管道数据之前设置严格 UTF-8 的 `$OutputEncoding`，同时明确 Python 的 UTF-8 解码。
2. 写入前验证必要中文段落和中文字符数量，拒绝成串替换问号。
3. 使用现有 `write_atomic()` 原子替换报告。
4. 写入后检查原始字节与输入的 UTF-8 编码逐字节相等，并严格解码回读。

另复核 `package_results.json`、`source_findings.json`、`targeted_results.json`、`targeted_content_findings.json` 和 `fixtures.json`：它们可严格按 UTF-8 解码并解析为 JSON，中文仍存在，关键计数与原审计一致；未发现同类全文件 ASCII 替换。转换器和正式 ZIP 哈希仍未变化。

## 复现命令

从仓库根目录运行。以下编码设置仅作用于当前 PowerShell 进程，不修改系统或用户配置。

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false, $true)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false, $true)
$env:PYTHONIOENCODING='utf-8:strict'
$env:PYTHONDONTWRITEBYTECODE='1'

& .\venv\Scripts\python.exe -u converter/audit2_schema.py yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip
& .\venv\Scripts\python.exe -u converter/audit4_structure.py yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip
& .\venv\Scripts\python.exe -u converter/audit5_headword.py yomitan_full/LDOCE5pp_Yomitan_2026.09.11.zip
& .\venv\Scripts\python.exe -u converter/audit_2026_09_12/source_probe.py
& .\venv\Scripts\python.exe -u converter/audit_2026_09_12/package_probe.py
& .\venv\Scripts\python.exe -u converter/audit_2026_09_12/targeted_probe.py
node scgen_test/run_scgen.mjs converter/audit_2026_09_12/generator_payload.json
& .\venv\Scripts\python.exe -u converter/audit_2026_09_12/export_lookup_rows.py
node converter/audit_2026_09_12/lookup_probe.mjs
```

`targeted_probe.py` 是当前缺陷的复现探针，其中断言预期 A1 仍存在；产品修复后应将对应断言改为负向回归测试。

证据 JSON、日志、提取记录、大体积生成器 payload 和隔离 ZIP 均保留本地并忽略入库，可用上述命令重新生成。

**建议顺序**：先修 A1 发布门禁，再修 A2/A3 的元数据和 A4/A5 的内容分派，补上 A6 负例；然后全量重建并重跑结构和语义检查，最后完成真实扩展导入与 UI 验收。
