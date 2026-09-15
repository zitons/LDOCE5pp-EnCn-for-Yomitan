# N1–N3 修复及完整验收（2026-09-14）

**本轮三项问题已修复，完整验收通过。** 原始问题与复现保留在 [REPORT.md](REPORT.md)，没有用修后结果覆盖修前证据。

未提交、未推送、未发布 Release，也未覆盖 `yomitan_full/` 的 09.13 成品。请使用下方新的验证包。

## 修复内容

### N1：空记录也必须阻止发布

- 被选中参与构建的源 entry 若渲染为空，按**源记录数**累计，不以唯一 key 集合替代。
- 非零 `empty_records` 与 `render_errors` 都在产出别名/辅助元数据前拒绝发布；`--skip-validation` 不绕过这一条件。
- 空记录诊断最多列出前 8 条，但总数不截断；空记录与异常混合发生时，两类问题都报告。
- 沿用统一的拒绝路径关闭、清理 `.part`、恢复 GC 阈值并保留旧 ZIP。
- 真 CLI 复测：普通缺失与同 key 第二条记录缺失均**退出 2，旧包仍为 2 行、哈希不变**。
- debug 未选中的空记录不会误伤正常调试构建。

### N2：保留两类漏网词内接缝

- 识别完整 `n't` / `n’t` 片段，保护 `did<span>n’t</span>` 等撇号之前的节点边界，包括直/弯撇号和不同大小写、节点方向。
- 对英文 e 结尾词干后单独链接的小写 `d` 保留连接，例如 `relieve + d`、`fertilize + d`；规则不是词条名称白名单。
- 明确的源空白、独立词性/语法标签、`vitamin D`、数字标签及 `model kits` / `games console` 等词组分隔保留。
- 双语、mono 都只改变以下 5 条内容行，每行删除一个错误插入的空格：
  `come`、`come as a surprise/relief/blow etc (to somebody)`、`in vitro fertilization`、`none`、`not`。
- 没有全局禁用行内分隔，也没有删除或重新生成词条正文。

### N3：无主题变量时继承宿主文字色

词典根规则从 `color:var(--text-color,#202124)` 改为 `color:var(--text-color,inherit)`。

- Yomitan 提供主题变量时，原有主题配色保持不变。
- Anki/其它宿主未定义此变量时，正文继承宿主文字色，不再硬编码成深色。
- 实际 Anki 导出作用域函数 + Chrome：暗色正文对比度 **1.036 → 11.247**，亮色为 **21.000**，双语/mono 同样通过。

## 验证工具也已加固

1. `regress_new_findings.py` 扩展到 14 个测试方法。分别在隔离的旧版模块和修后模块运行：
   旧版产生 **44 个预期断言失败、0 个工具错误**；修后 **14/14 通过**。与原 `regress_review_followup.py` 的 14 组一起，共 **28 组快速回归通过**。
2. `regress_render_contract.{py,mjs}` 新增“有 CSS、无 Yomitan 主题变量”的亮/暗宿主检查，断言真实继承和对比度。
3. 浏览器门禁现在读取**被测 ZIP 自己的 styles.css**，不再用当前 `generate_css()` 代替它：
   旧 09.13 ZIP 在新检查下确实退出 1，新 09.14 ZIP 通过，避免源码修好后给旧包错误放行。
4. 实际导入器探针增加 5 条正文修复以及 Anki 亮/暗继承的硬断言，不再只输出颜色供人工查看。
5. 严格新旧包比较器只允许已审查的节点间空格删除；节点种类、样式、属性、其它文本、字段和别名目标均不允许变化。比较器本身有正例与拒绝普通词间空格删除/标签改变的负例。
6. 各探针支持显式输入和独立输出，修后结果写入 `results/fixes/`，修前结果保留在原位置。

## 完整验收结果

| 检查 | 结果 |
|---|---|
| 28 组快速回归 | 全部通过；覆盖普通/同 key 空记录、bank 已刷入、GC/旧包保留、诊断上限、混合失败、mono 过滤后变空、debug 范围、CLI 退出码及接缝正反例。 |
| 旧非浏览器门禁 | 11 个脚本调用全部退出 0；旧内容、词头、列表、标记、CSS 与分隔回归通过。 |
| 双语全量构建 | 退出 0，245,933 行 = 64,659 内容行 + 181,274 别名行；空记录/渲染错误/悬挂链接 0。总耗时 970.9 秒。 |
| mono 全量构建 | 退出 0，同样 245,933 行；空记录/渲染错误/悬挂链接 0；全包零 CJK。总耗时 953.8 秒。 |
| 全部行字段及 SC 树比较 | 两种模式各仅 5 条记录删除 5 个空格；其它内容节点、属性、正文字符、行字段和所有别名目标完全不变。不是只做“去空白后相等”的比较。 |
| 辅助文件与 CSS | tag/term_meta 全部逐字节相同；index 仅 revision 更新；CSS 去除注释后仅根文字色 fallback 一处语义变化，包内 CSS 与当前源码一致。 |
| 官方 Schema 全量 | 两包全部 **491,866 条 term 行**及 index/tag/term_meta 全部通过实际 Yomitan AJV 校验器。 |
| 独立源 DOM | 全部 **64,659 条内容记录**元数据零差异；原 5 个真实断词候选消失，剩余 10 个与修前已排除的正常词间分隔完全相同，没有新增候选。 |
| 原与扩展浏览器契约 | Yomitan 亮/暗、无 CSS 源编号/标记、行内样式与字重、无主题变量的亮/暗正文全部通过。 |
| 实际导入器 + Chrome IndexedDB | 两包分别完整导入新的隔离 origin；每包真实存入 245,933 词条、5,971 频率、33 标签。采集到的导入/运行时异常均 0。 |
| 导入后查询与 DOM | 词形查询正例、5 条正文修复、查询链接参数/目标和 details 点击均通过；Anki 导出后的亮/暗继承有明确断言并通过。 |

两种构建同时执行，耗时不是空载基准。所有检查的包 SHA-256 与构建清单、最终文件一致。

## 新验证包

| 模式 | 文件 | 字节数 |
|---|---|---:|
| 双语 | [LDOCE5pp_Yomitan_2026.09.14.zip](../../yomitan_fixed/2026-09-14-n1-n3/bilingual/LDOCE5pp_Yomitan_2026.09.14.zip) | 63,737,646 |
| mono | [LDOCE5pp_Yomitan_2026.09.14_EN.zip](../../yomitan_fixed/2026-09-14-n1-n3/mono/LDOCE5pp_Yomitan_2026.09.14_EN.zip) | 54,116,572 |

包内 revision：`2026.09.14-review-fixes`。

SHA-256：

- 转换器：`242c5da3d369adf1b2938b0947dffcfadcfd9d89771d9ab32e65b52719ca9189`
- 双语：`334ef42fc1391f8550f227b6e5951069d90e2584a4946b067e2b9ccb340b8759`
- mono：`70e9e722507efda380ab9ff9ecf550822250f4f97b9abc77adc5452d3986e1da`

构建日志及单包清单在新包各自的目录中；汇总清单见
[`verification_manifest.json`](../../yomitan_fixed/2026-09-14-n1-n3/verification_manifest.json)。

## 复验

```powershell
& .\venv\Scripts\python.exe -X utf8 converter/audit_2026_09_14/regress_new_findings.py
& .\venv\Scripts\python.exe -X utf8 converter/regress_review_followup.py
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_14/verify_fixed.py
& .\venv\Scripts\python.exe -X utf8 converter/regress_render_contract.py yomitan_fixed/2026-09-14-n1-n3/bilingual/LDOCE5pp_Yomitan_2026.09.14.zip
```

需要重建时，`build_fixed.py` 必须使用新的 `--output` 目录；再用 `verify_fixed.py --root <新根目录>` 核对。
比较器固定验证本轮修复范围，后续扩大正文/样式变更时需要重新审核预期，不能随意放宽断言。

主要证据均位于 `results/fixes/`：`fast_regressions.json`、`publication/results.json`、
`full_comparison.json`、`official_schema.json`、`source_inventory.json`、`regressions/results.json`、
`native_contract_fixed.log`、`browser-import/results.json` 和 `verification_summary.json`。

## 保留边界

- 未运行完整扩展设置页/搜索弹窗或 Anki 客户端端到端验收。Chrome 中运行的是实际导入器、数据库、English transforms、SC 生成器和导出作用域函数，不冒充整个应用。
- 双语/mono 是同 title 的替代版本，导入检查使用隔离数据库；替换既有同名词典时按 Yomitan 的更新/移除后导入流程操作。
- `--limit` 仍是显式部分构建，必须使用独立输出目录；本轮未改变这项 CLI 命名策略。
- 未更新 GitHub Release、未读取凭据；历史发布配置与凭据吊销等外部事项不在本次三项修复范围内。
- 旧正式包哈希保持不变，仍包含本轮修复前的问题；不能把新源码的通过结果套用于旧 ZIP。