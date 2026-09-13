# R1–R3 与上轮审查遗留的修复报告（2026-09-13）

对 `REPORT.md` 三条 P2 回归的修复、以及 2026-09-12 复审开出的 7 条。缺陷编号在 `REVIEW.md`
登记为 D34–D38。**ACTIV 义项标签未加中文**（用户明确：源里查无对照就不加）。

## 基线与结果

| | 修复前（f120dbb） | 修复后 |
|---|---|---|
| 转换器 `converter/ldoce2yomitan.py` | `4ef239c1…` | 见 `git show HEAD:converter/ldoce2yomitan.py` |
| 交付包 | `…2026.09.12.zip` 63,649,164 B `bc067411…` | `…2026.09.13.zip` 63,737,688 B `5edae5d9131ab8261d80ba602bfc733642e3840c49bc37fe8d54c081fb53f8fc` |
| 行数 | 245,933（64,659 内容 + 181,274 别名） | 同左，**逐行一致**；sequence 连续唯一 |
| 全量构建 | 840 s | 824 s |
| CSS | 24,355 B，4 个 `!important` | 24,918 B，9 个 `!important` |

## 修复一览

| 编号 | 缺陷 | 修前 | 修后 |
|---|---|---|---|
| D34 (R1) | 分隔器拆词：`terrorist s`、`bank robber s`、`download ed`，`SUM1`→`SUM 1` | 15 词条/16 处断词 + 584 处/560 词条 | **0**（全量 650 处被删空格逐处对照源端，0 回归） |
| D35 (R2) | 无 CSS 时 UA 按 1..n 重编义项号 | 531 词条 / 572 列表 / 2,436 处 | **0**（`UA_MARKER_OFF`，三种列表生产者都挂） |
| D36 (R3) | 内联兜底色压过主题调色板 | 暗色 `ld-defcn` 3.25:1、亮色 `ld-pos` 3.24:1 | **6.48 / 6.97**，字重 700→600 |
| D37 | 中性色静态回退低于 ≥3.0 | 2.97 / 2.29（白）、2.83 / 2.26（暗） | 继承宿主文字色（可读性由构造保证） |
| D38 | 清理项（死代码、过时注释、文档编号/日期、过时工具） | — | 全部处理；1 条误报撤回 |

## D34 的弯路（值得记下）

第一版修法是"只在 `BODY_ATOM_CLASSES` 类边界插空格"。**它引入了新回归**：`coal mines`→
`coalmines`、`informal a)` 胶死。根因是 `merge_adjacent_text()` 会把"空白节点 + 紧随文本"直接
丢掉（`out[-1] = node`），源端空格从未进入 SC，旧代码靠字符启发式补回来；收窄启发式等于把
源端空格也丢了。

正确做法是两层：
1. `merge_adjacent_text()` **保留源端分隔**（把空白折叠进紧随的文本 run）；
2. `_seam_needs_space()` 只保留**一处**压制——`(元素, 裸字符串)` 且左侧元素非原子类。

其余与 09.12 完全一致（最小偏差）。`margin:1px 0` 是两值简写（下边距=1px），我在这上面
误判出一条假缺陷，真 Chrome 实测后撤回。

## 验证

- `diff_seams.py`：09.12 vs 09.13 逐行对齐，删 650 / 增 2,173 处空格。
- `check_glue.py`：删除的空格逐处对照**源端去标签文本**（`re.sub(r'<[^>]+>','',content)`），
  0 回归；648 处拼回的形在源端本就粘连（`MI5`/`G8`/`M25`/`V8`/`p53`…）。
- `check_split.py`：新增空格逐处对照源端，0 处无据（2,067 处源端确有空白，106 处为芯片分隔）。
- `regress_render_contract.py` + `regress_render_contract.mjs`：官方 `structured-content-generator`
  + 真 Chrome 双模式——有 CSS 时调色板胜出（`!important` 生效）、`ld-mark` 隐藏、`ld-snum` 可见、
  `ol` 无原生标记；无 CSS 时 UA 标记关闭、源编号可见、标记 span 可见、兜底色生效。
- `regress_inline_vs_css.py`：22 条行内兜底声明全部"等于类规则"或"类规则带 `!important`"；
  中性色静态回退两组对比度 ≥3.0。
- audit2/4/5/8/9 + regress_pos_cap/css_fallback/head_separation/list_validity/scheme_b 全部
  exit 0（见 `gates.log`）。
- `regress_content.py` 的 A3 断言改为"参考值 ⊆ 实际值"（D29 取消上限后 `after`/`down`/`last`
  合法新增了标签，旧精确相等断言报 12 个假失败——与 `REPORT.md` §旧 A3 断言一致）。

## 未做

- 真实 Yomitan 扩展导入验收（唯一未覆盖的最终验收）。
- mono 全量重建（A5 修复只影响该模式；候选集回归通过）。
