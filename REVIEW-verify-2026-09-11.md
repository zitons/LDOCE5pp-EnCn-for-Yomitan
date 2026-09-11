# 外部改动审查报告（2026-09-11）

> 审查对象：提交 `5e343c4`「修复 D10-D19」，作者为另一会话的 AI。
> 审查方式：**不复述对方结论，全部独立复算**。用到的基线是 `bb98431`（T9 修复之前的提交）。
> 结论一句话：**改动方向正确、产量可信、事故恢复忠实；但发现 1 处未修完的真实缺陷（479 词条）、1 处门禁误报（已由我修好）、若干文档与仓库卫生问题。**

---

## 1. 最重要的事：源文件曾被截断，恢复可信

**事故**：用 `io.open(p, "w", newline="\\n")`（`\n` 是两个字面字符，非法参数）改写源码时，`io.open` 在参数校验失败**之前**已把 `converter/ldoce2yomitan.py` 截断为 0 字节；`__pycache__` 也随之失效。丢失范围 = HEAD 之后**所有未提交**改动（T9 + 本轮 T10/D10/D11/D13/D14/D17…）。

**恢复方式**：从 `git HEAD` 取原始字节，按记录逐条重放补丁，写入改为原子写（临时文件 + `os.replace`），每条编辑带 `assert` 计数校验。

**我的独立验证（三条，互相独立）**：

| 验证 | 方法 | 结果 |
|---|---|---|
| T9 是否逐字节还原 | 自取基线 `bb98431` + 我当初那 5 处 T9 编辑，重算 md5 | `67e7ed25230da99922ff6b54e459aadb`，前 12 位 = 对方引用的 `67e7ed25230d` ✅ |
| 代码 ↔ 产物（行） | `audit3_reproduce.py` 抽样重渲染，与交付 zip 逐字节比对 | **45/45 一致，0 差异** ✅ |
| 代码 ↔ 产物（元文件） | 交付包内 `styles.css` / `tag_bank_1.json` 与当前 `generate_css()` / `build_tag_bank()` 输出比对 | **逐字节相同**（CSS 19,599 B；tag 1,421 B）✅ |

➡️ **恢复是忠实的，当前代码就是产出交付包的代码。** 上面第 2、3 条同时覆盖了本轮所有 CSS 改动（T9 / D11 / D13 / D14 的样式），因为它们全在 `styles.css` 里。

**预防措施确实落地**（不是写在文档里而已）：5 个新增补丁脚本 `_fix_after_recovery / _fix_opp_baretext / _fix_opp_children / _fix_opp_precedence / _patch_validator` **全部**走 `_apply_patch.apply()`（assert 在写之前）；全仓已无 `newline="\\n"` 误用。

---

## 2. 声称的修复，逐项核对

| 项 | 对方声称 | 我的核验 | 判定 |
|---|---|---|---|
| D10 频率等级被 6 标签上限截断 | 140 行自我矛盾 | 旧包实测：`term_meta_bank` 5,971 行 vs `definitionTags` 5,831 次 = **恰好 140**（S1 882/880、W2 950/909、W3 1139/1086…）；新包 **5,971 = 5,971 完全自洽** | ✅ |
| D11 词族丢 `span.opp` | 3,528 处 | 源端 bs4 逐条统计 = **3,528**（1,725 个词条，与包内 `ld-wf-opp` 覆盖的 1,725 词条吻合） | ✅ |
| D13 LDOCE Online 面板 | 618 个词条 | 包内含 `ld-panel-online` 的 entry 行 = **618** | ✅ |
| D14 GRAM 丢方括号/限定词 | 508/1,501 | 6,000 个 GRAM span 与"源文本剔除 `portrait` 子树"的参考实现比对：**零差异**；1,500 词条抽样中 552 条输出变化、全部是补回 `[` `]` 与限定词（如 `countable` → `[singular, uncountable]`） | ✅ |
| D17 变形列表丢区域标签/注解 | 58/2,389 | `backpedal` → `backpedalled · backpedalling · British English · backpedaled · backpedaling · American English`；`age` → `… aging · or · ageing · British English`：**顺序与源逐一吻合** | ✅（但**未修完**，见 §3 R1） |
| D16 校验器漏检复合 class | 需 `[data-sc-class~=]` | 逻辑正确：复合值（如 `ld-sense ld-sense-n`）只能被属性子串选择器命中，`collect_sc_classes()` 分开收集"整值 token / 复合值内 token"，后用 `used_compound - defined_substr` 报错。新包 `audit4` 显示 `CSS used=109 defined=125 missing=[]` | ✅ |
| T10 双词族面板 | — | `close` 现在**只有 1 个** `ld-panel-wf`（原 2 个）；包级 diff 显示 `ld-panel-wf` 恰好 **-38** | ✅ |

**另外**：`audit9` 文本守恒缺口由 **1.738% → 1.592%**（更好，无新增丢失）。

---

## 3. 发现的问题

### R1【中·真实缺陷】D17 未修完：479 个词条的变形标签里 `portrait` 缩写仍在泄漏

同一类 bug 他们为 GRAM 修掉了（D14，引入 `_no_portrait_text()`），但 **`Inflections` 里的 `infllab` 标签没走那条路径** —— 该标签嵌在形态 span **内部**，`push_form()` 直接用 `child.get_text()`，把 `landscape` 与 `portrait` 一起吞下。

实测（当前代码 + 当前包）：

```
abide  → 'past tense pst abode'                                  ← 应为 'past tense abode'
bad    → 'comparative comp worse · superlative supl worst'        ← 应为 'comparative worse · superlative worst'
ante   → 'past tense pst and past participle pp anted · or · …'
be     → 'past tense pst was · were · past participle pp been …'  ← 超高频词
```

| 指标 | 值 |
|---|---|
| 含 `Inflections` 的词条 | 2,808 |
| 输出里确实泄漏缩写（以独立词计）的词条 | **479** |
| 泄漏的缩写取值 | `pst` 310、`pp` 309、`supl` 167、`comp` 166、`3rd` 16 |

**根因定位**：`render_inflections()` 的 `push_form(child.get_text(" ", strip=True))`；源结构为
`<span class="PTandPP"><span class="infllab"><span class="landscape">past tense</span><span class="portrait">pst</span> and …</span>anted</span>`。

**修法建议**：对含 `infllab` 的形态 span，用 `_no_portrait_text()` 处理标签部分（工具已存在，1 处改动），并把标签渲染为**已定义但从未使用**的 `ld-infl-lab`（见下）。改完需重跑全量。

**附带线索**：CSS 里 `[data-sc-class="ld-infl-lab"]` 有定义，包内出现 **0 次** —— 本该由它承载这个标签，说明作者想到了但没接线。

### R2【低·门禁误报】`audit8` 报 10 例不一致 —— 已由我修好

`render_head` 会把 `ld-infl` 的**子节点内联**进词头，于是 D17 新增的 `ld-infl-ann` / `ld-infl-region` 夹在两个 `ld-infl-form` 之间，`audit8` 的 `squash()` 得到 `INFL / ld-infl-ann / INFL`，而源里只有 1 个 `Inflections` 元素 → 报 10 例假阳性（`addendum`/`age`/`ante`/`appendix`/`aquarium`…）。

**我修改了 `converter/audit8_head_order.py` 的 `our_tokens()`**：把这三个类视为 INFL 串的一部分（`continue`）。重跑 8,000 抽样：

```
顺序完全一致 = 7931   顺序不一致 = 0   Head 块数量不符 = 0   exit=0
```

➡️ **产物无问题，是门禁模型没跟上新类。**（我改的是审计工具，未动转换器。）

### R3【文档】T10 段落自相矛盾，且有过期陈述

`TYPOGRAPHY.md` 的 T10 一节同时写着三种状态：

- "**倾向 A** … 本项目原则是内容忠实优先，故**未擅自改动**"
- "**当前状态：已修复（2026-09-11，方案 A，用户拍板）**" ← "用户拍板"我无法确认（在我这边的会话里用户从未表态），建议注明决策来源
- "**落地状态**：代码已改，**尚未进包** —— 09.11 交付包仍是改前状态，需一次全量重建才会生效" ← **过期且错误**：实测交付包**已生效**（`close` 只有 1 个面板）

同类：`REVIEW.md` 里 D10/D11/D13/D14/D17 的标题仍带"**（代码层，待重建）**"，但包已重建、这些改动都已进包（我用包内计数逐项证实）。

建议：统一改成"已进包（2026.09.11）"。**已执行**（见 §6）。

### R4【仓库卫生】一次性脚本与日志大量入库

本次提交新增 **31 个 `.log`**、**7 个 `_` 前缀恢复脚本**、以及约 **30 个探针脚本**（还包含我的截图与 `full_build8.log`）。建议：

- `.log` 与 `_*.py` 不入库（`.gitignore` 里已加 `converter/_*.log`，但普通 `.log` 与 `_*.py` 仍被提交）；
- 探针脚本归到 `converter/probe/` 或加一行用途说明，避免 `converter/` 从 20 个文件膨胀到 60+。

### R5【非问题，仅记录】`TAG_LIMIT=8` 不会截断 POS

`pos_tags_rules()` 改为 `pos_part[:TAG_LIMIT - len(freq_part)] + freq_part`。核验包内每行 POS 标签个数分布：`{0:23888, 1:31698, 2:6822, 3:1987, 4:264}`，**上限仅 4** ⇒ `room` 永不生效，POS 行为零变化。改动是精准的。

### R6【纠正我自己】D11 的 3,528 我一开始算错了

我第一次按"包内 `ld-wf-opp` 节点数"去比对，得到 3,508 与对方不符；改用源端统计后得 **3,528**，与声明一致。**是我的口径错了**，不是对方的问题。（差 20 是 20 个 `span.opp` 处理后无输出。）

---

## 4. 未能验证的部分（诚实边界）

1. **真机导入** —— 依然是最大缺口。本轮所有结论均为"结构合法 + 官方 schema + 能重渲染"，**不等于** Yomitan 扩展里 UI 正确。
2. **`ld-panel-online` 的交互**：新面板依赖 `<details>`，折叠时是否与 Yomitan 的样式冲突未在真浏览器里量过（T1 那轮的教训：这类事不打开浏览器就不靠谱）。
3. **D14 的视觉后果**：GRAM 从 `countable` 变成 `[countable]`，影响 37% 的词条；文案正确，但**行宽是否变挤**没有实拍验证。
4. 事故恢复的**其余部分**（D10-D19）只有行为验证 + 包级一致，没有像 T9 那样的"md5 逐步复现"证据 —— 因为工作区版本从未入库，不存在可比对的中间值。

---

## 5. 建议的下一步（按优先级）

| 优先级 | 动作 | 代价 |
|---|---|---|
| **P0** | 修 R1（479 词条的 `pst`/`pp`/`comp`/`supl` 泄漏），顺带把标签接到 `ld-infl-lab` | 约 15 行 + 1 次全量重建（~11 分钟） |
| **P1** | 修 R3 文档（T10 三处矛盾、5 个"待重建"标题） | 纯文档 |
| **P2** | R4 仓库清理（`.log`/`_*.py` 出库） | 纯清理 |
| **P3** | 真机导入验收（唯一的最终判据） | 需人工 |


---

## 6. 修复执行记录（2026-09-11 晚，用户："修吧"）

### 已实施

| 项 | 内容 | 验证 |
|---|---|---|
| **R1**（D20） | `render_inflections()`：新增 `text_no_portrait()` + `label_and_form()`，把 `span.infllab` / `span.italic` 标签从形态中拆出并走 `_no_portrait_text()`；**接线 `ld-infl-lab`**（此前定义了却从未输出） | 单点 `be`/`bad`/`ante`/`abide`/`appendix`/`adieu`/`awake`/`angry`；**全量 2,808 个含 `Inflections` 的词条 → 0 泄漏**（原 479 词条 / 968 处） |
| **R1b** | `push_annot()` strip 集合 `"() "` → `" ,;.()"`（`LINKWORD` 自带列表分隔逗号，与我们的 `·` 重复） | `be` → `… · first person singular · am · …` |
| **R1c**（D21） | `_pick_landscape()` 在**存在 landscape** 时委托 `_no_portrait_text()`，保留并列 POS（`Algeria` = `noun, adjective`） | 104,837 个 POS span 中 **168 个** 的 `ld-pos` 文本改变，**全部为内容恢复，0 空白差异** |
| **R2** | `audit8_head_order.py` 的 `our_tokens()` 把 `ld-infl-ann`/`ld-infl-region`/`ld-infl-lab` 并入 INFL 串 | 8,000 抽样：**不一致 0 / 数量不符 0 / exit 0** |
| **R3**（D22） | `TYPOGRAPHY.md` T10 三处矛盾订正（含"尚未进包"这条过期陈述）；`REVIEW.md` 五个"（代码层，待重建）"标题改为"已修复并进包" | 逐处 `assert` 命中数后写入 |
| **R4**（D22） | `.gitignore` 覆盖 `*.log` 与 `converter/_*.py`（保留被 D15 引用的 `_apply_patch.py`/`_restore_all.py`）；46 个日志与 5 个一次性补丁脚本 `git rm --cached` | `git check-ignore` 逐项复核；文件仍在磁盘 |

改动全部经 `_apply_patch.apply()`（原子写 + assert 计数），md5 链：`c393cc02f7 → 138eb4d350 → 534d18559d → 61c698b7cd`。

### 尚未做（需要用户）

- **Release 附件仍是旧包**。D20/D21 修复后重新构建了 `LDOCE5pp_Yomitan_2026.09.11.zip`（sha256 前 8 位
  `15aaa3b8`，60,198,033 B），而 GitHub Release 上挂的仍是 `082fc555…` 那一版 —— 需要重新上传才能让
  下载入口与文档一致。
- 那个在对话里出现过的 GitHub token **必须吊销**后才能上传新附件；请提供新 token 或自行上传。

### 我这次的两次自我纠错（记录在案）

1. 我用"包内 `ld-wf-opp` 节点数"比对 D11 的 3,528，误判对方数字有误 —— 实际是我的口径错（源端 span 数才是 3,528）。
2. 我用"按花括号切规则"的粗糙正则读 `LM5style.css`，漏掉 `@media` 包裹，一度得出"原版显示缩写、隐藏完整标签"的**相反结论**，差点要否掉 D14。补上 `@media` 上下文后确认 D14 方向正确。
