# 后续复审问题修复（D39–D41 / F1–F3）

## 已完成的修复

- **F1 / D39**：渲染失败必定阻止发布，包括 `--skip-validation`；在生成别名/辅助元数据前拒绝，
  关闭并清理 `.part`，保留旧 ZIP，恢复 GC 阈值。没有新增默认 best-effort 行为。
- **F2 / D40**：mono 去除全部标题中文子节点、中文专用语域标签及英文例句中明确的 NOT 中文注解；
  双语内容保留。不按 `switch_siblings` 一刀切，不静默清除其它未知中文。
- **F3 / D41**：保护撇号缩写的三类节点接缝；词组、词族和标签仍按原规则分隔，不全局禁用空格。

## 验证结果

| 项目 | 结果 |
|---|---|
| 自包含快速回归 | 14 组全部通过；覆盖真实渲染异常、CLI、同 key 记录、诊断上限、bank 已刷入、GC/旧包保留及语言/分隔正反例。 |
| 双语全量构建 | 退出码 0，245,933 行（64,659 内容 + 181,274 别名），25 个 term bank；空记录、渲染错误、悬挂链接均为 0。 |
| mono 全量构建 | 同样 245,933 行，退出码 0；零 CJK、空记录、渲染错误、悬挂链接。不是只运行四词样本。 |
| 完整行比较 | 两种新包的非 glossary 字段及别名目标与基线一致；双语正文仅在 70 条记录中去掉 74 个撇号内空格，其余字符完全相同。 |
| 历史断词案例 | 本轮 36 个缩写案例 + 前轮 16 个后缀案例，52 个全部恢复。 |
| 源码/包一致性 | 45 条内容样本逐字节复现，0 不一致；旧脚本跳过的别名没有算作复现通过。 |
| 独立结构、词头与列表 | 双语/mono 结构通过；词头污染 0；孤儿 li 和非法列表子节点 0。 |
| 旧回归 | A1/A6 门禁、A2–A5 候选集、词头分隔、22 条内联/CSS 声明一致性与 CSS 回退检查均通过。 |
| 浏览器契约 | 原始 SC 生成器 + Chrome：亮/暗主题、无 CSS 源编号与标记、字重均通过，R2/R3 无回退。 |

9 项包检查的退出码与日志在 `yomitan_fixed/verified/post_checks.json`；完整行比较在
`verification.json`；浏览器结果在 `browser_contract_result.json` / `browser_contract.log`。

两种构建并行执行：双语约 958.7 秒、mono 约 942.2 秒（包含校验）。这不是空载性能基准。

### 验证工具订正

初版差异分类器的弯撇号在写脚本时被错误替换成了 `?`，导致 58 条误报。
**生产代码和词典内容没有发生此替换。** 已改用 ASCII 写法 `chr(0x2019)`，增加直/弯撇号正例、
问号与正常词间空格负例，并重新完成全量对照，失败数为 0；没有放宽正文字符守恒断言。

## 新包（旧正式包未覆盖）

| 模式 | 路径 | 字节数 |
|---|---|---:|
| 双语 | `yomitan_fixed/verified/bilingual/LDOCE5pp_Yomitan_2026.09.13.zip` | 63,737,603 |
| mono | `yomitan_fixed/verified/mono/LDOCE5pp_Yomitan_2026.09.13_EN.zip` | 54,116,529 |

SHA-256：
- 源码：`5343520b762db09bb43d8191d6e789f95db94952338c4985c8dae886ff8fcc6f`
- 双语：`8544ed4c6677f7c8e1cdc17a3222dc69b40be3d3b0857feefecb2ccfe73d77e1`
- mono：`73662eabaa3985eb9843026ca55a440838c12d286d6247fa7565cd93dcaa840e`

`yomitan_full/` 中旧 09.13 包仍为 `5edae5d9…53f8fc`，不要把它当作这轮修复成品。
首次长跑被中断，`yomitan_fixed/bilingual/` 与 `yomitan_fixed/mono/` 的 `.part` 仅为现场中间文件，
不得导入；成功结果仅在上表的 `verified/` 子目录。

## 复现

```powershell
& .\venv\Scripts\python.exe -X utf8 converter/regress_review_followup.py
# 重建必须指定新目录，不覆盖已有验收结果：
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13_followup/build_fixed.py bilingual --output yomitan_fixed/new-run/bilingual
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13_followup/build_fixed.py mono --output yomitan_fixed/new-run/mono
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13_followup/run_fixed_checks.py --root yomitan_fixed/new-run
& .\venv\Scripts\python.exe -X utf8 -u converter/regress_render_contract.py 'yomitan_fixed/new-run/bilingual/LDOCE5pp_Yomitan_2026.09.13.zip'
```

ZIP 文件名使用实际构建日期，日期改变时应使用新目录内的真实文件名。
构建脚本会保留 UTF-8 日志与源码/产物哈希；校验脚本支持断点续跑已成功的检查。

**边界：** 未自动发布到 Release、未做真实扩展导入/交互验收，未重跑完整官方 JSON Schema；
不把已通过的内嵌/独立结构检查和浏览器局部渲染等同于这些未执行的检查。
复审前的 `REPORT.md` 与原 JSON 保留为历史证据，没有用修后结果覆盖。
