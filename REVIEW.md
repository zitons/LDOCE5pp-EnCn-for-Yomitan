# LDOCE5++ → Yomitan 转换器 · 实现审查报告

> 审查时间：2026-09-10 · 审查对象：`converter/ldoce2yomitan.py`（2058 行，唯一事实来源）及其交付物
> 方法：**不看文档结论，直接重跑并独立复算**。所有数字均可用文末命令复现。

---

## 0. 结论摘要

| 维度 | 评价 |
|---|---|
| 数据完整性 | **优秀**。245,933 行、零悬挂链接、零 SC 契约违规、序列号连续，全部经独立脚本复核（非转换器自带校验器） |
| 代码 ↔ 产物一致性 | **优秀**。抽样重渲染 45/45 逐字节一致，可判定当前代码就是产出该 zip 的代码 |
| Yomitan 兼容性 | **优秀**。真生成器（与 release 逐字节相同）渲染 405/405 通过 |
| 渲染保真度 | **有 1 处高severity + 1 处中等问题**：20,030 个词条（**31%**）的词头被标签文本污染（见 D0）；119,249 个纯中文释义未按文档设计走 `ld-defcn` 分支（见 D1） |
| 可维护性 | **偏差**。约 20 行死代码/不可达分支、若干"元素名当类名"的残留、头部注释与事实矛盾 |
| 文档与审计链 | **有 3 处不一致**（见 §5） |

**没有发现会导致导入失败、数据丢失或链接错乱的问题。** D0 是词头显示严重失真（31% 词条），D1 是中文释义排版降级——两者都是保真度缺陷，不是数据缺陷。

---

## 1. 独立复现的验证（我实际跑出来的）

新建脚本 `converter/audit3_reproduce.py`、`converter/audit4_structure.py`，刻意**不复用**转换器自带的 `validate_package`，用自己写的白名单与遍历独立复核。

### 1.1 代码能否复现已交付的 zip？

重放 Pass A（重建全键索引）→ 重放"别名预规划"→ 从源文件重渲染 63 条抽样（含 30 随机、6 个 `*-topic`、命名重点词、15 个别名）→ 与已交付 zip 的行逐字节对比。

```
reproducible rows: 45  mismatched: 0  (100% byte-identical)
```
（48 条词条中 45 条可比对，另 3 条为我抽样集内不存在的键；15 条别名行因我的迷你重渲染只覆盖 63 行、目标不在其中而无法复算，属抽样方法限制，非缺陷——别名目标已由 §1.3 的独立扫描验证。）

**结论：当前 `ldoce2yomitan.py` 与已交付 `LDOCE5pp_Yomitan_2026.09.10.zip` 完全同步。**

### 1.2 真 Yomitan 生成器渲染（L3 复现）

```
scgen_test/js/display/structured-content-generator.js  ← 与 yomitan-ext release 逐字节 IDENTICAL
stubbed: display-content-manager.js / text-utilities.js / anki-template-renderer-content-manager.js
```
```
real-generator: ok=405 fail=0 total=405
elements rendered=130837 links=29155 details-without-summary=0
```
输出中确认 `href="about:///search.html?query=better&wildcards=off" data-external="false"`，即内部链接重写发生点在生成器本体（`structured-content-generator.js:479-481`），不是被测的 Fake ContentManager。**HANDOVER §8 L3 的声明属实。**

### 1.3 独立结构扫描（不经转换器校验器）

```
rows=245933   seq unique=245933   range=0..245932   contiguous=True
SC key/tag violations: NONE          ← 用我自己写的白名单（span/div/ol/ul/li/details/summary 允许 style/title/open；
style prop violations: NONE              a 只允许 tag/content/href/lang；td/th 允许 colSpan/rowSpan）
<a> href malformed: 0
link targets=63647        not-a-row=0
redirect targets=52138    not-a-row=0
title attrs=15375         lang usage={'zh': 390784}
别名与词条同时成行的表达式: 0        ← 无"别名遮蔽真词条"
跨 score 的重复表达式: 0
CSS used=101 defined=118 missing=[]  unused=17
```

### 1.4 中文内容守恒

```
源 entry 记录中 cn_txt 出现次数 = 289,189
包内 ld-zh 166,872 + ld-defcn 34 + ld-excn 118,604 = 285,510   (98.7%)
```
差额 3,679（1.3%）落在**故意丢弃**的区域（`lm5pp_popup`/菜单/FrequenceBox/asset 头等）。**无系统性中文丢失。**

---

## 2. 缺陷清单

### D0【高】词头被标签文本污染 —— 影响 16,751 个词条（25.9%）✅ 已修复并验证

> 触发来源：用户实测反馈「查 `seeing` 显示 `see·ingspoken`」。
> **修复后实测：受污染词条 16,751 → 0，泄漏字符串 26,434 → 0**（`converter/audit5_headword.py` 回归门禁 exit 0）。
>
> *口径订正*：本节初稿写的"20,030 个词条"是**受污染的 Head 块数**；按词条去重后是 **16,751 条（25.9%）**——差值是同一词条有多个被污染词头的情况。

**位置**：`ldoce2yomitan.py:795-798`，`render_head()` 的兜底 `else` 分支

```python
else:
    text = sc_text(child.get_text(" ", strip=True))
    if text:
        hwd_nodes.append(text)     # ← 任何未识别的 Head 子元素，文本直接进词头
```

`hwd_nodes` 整体被包进 `span.ld-hwd-wrap`（CSS：`font-size:1.28em; font-weight:700`），所以标签文本会**以大号粗体、无分隔地粘在词头后面**。

**`seeing` 的源与产物**

```html
<!-- 源 -->
<span class="Head"><span class="HWD">see<span class="HYP"><span class="HYP">·</span></span>ing</span>
  <a class="PronCodes" href="sound://…"> /ˈsiːɪŋ/</a>
  <span class="lm5pp_POS"> conjunction</span>
  <span class="REGISTERLAB"> spoken</span>      ← 语体标签
  …
```
```json
// 产物
{"class":"ld-hwd-wrap","content":[
   {"class":"ld-hwd","content":["see",{"class":"ld-hyp","content":"·"},"ing"]},
   "spoken"]}                                    → 显示为 see·ingspoken
```

**根因的关键点**：泄漏进词头的 13 个 class 中，**有 12 个在 `CHIP_MAP` 里早就有现成映射（`ld-register`/`ld-geo`/`ld-lexvar`/…），只是 `render_head()` 从不查这张表**——它只认 HWD/HOMNUM/PronCodes/PRON/AMEVARPRON/lm5pp_POS/GRAM/LEVEL/FREQ/tooltip/Inflections 这 11 个。

| Head 直接子元素 class | 源中出现次数 | CHIP_MAP 既有映射 | render_head 行为 |
|---|---|---|---|
| `REGISTERLAB` | 6,837 | `ld-register` | ❌ 文本进词头 |
| `HYPHENATION` | 6,574 | **无映射** | ❌ 文本进词头 |
| `LEXVAR` | 4,835 | `ld-lexvar` | ❌（部分因 `suppressed` 被丢弃） |
| `GEO` | 3,864 | `ld-geo` | ❌ 文本进词头 |
| `Variant` | 3,227 | `ld-lexvar` | ❌ 文本进词头（链接被压平） |
| `FIELDXX` | 1,686 | `ld-fieldxx` | ❌ 文本进词头 |
| `AC` | 1,428 | `ld-gloss` | ❌ 文本进词头（`title` 丢失） |
| `HOMOPHONE` | 1,194 | `ld-homophone` | ❌ 文本进词头（链接被压平） |
| `FIELD` | 646 | `ld-field` | ❌ 文本进词头 |
| `AmEVariant` / `BrEVariant` | 525 / 369 | `ld-lexvar` | ❌ 文本进词头 |
| `PHRVBHWD` / `LINKWORD` | 48 / 36 | `ld-refhwd` / `ld-collo` | ❌ 文本进词头 |

（词库共 90,580 个 Head 块，其中 8,992 个是 `class="frequent Head"`。）

**影响面（包内实测）**

| 泄漏类别 | 字符串数 | 涉及词条 |
|---|---|---|
| 语体标签 `REGISTERLAB` | 5,248 | 4,904 |
| 地域标签 `GEO` | 5,170 | 4,162 |
| 音节切分 `HYPHENATION` | 4,731 | 4,655 |
| 其他（多为 `HOMOPHONE` 同音词串） | 3,477 | 2,848 |
| 异体/变体 `Variant`/`LEXVAR` | 2,663 | 2,484 |
| 学科标签 `FIELD`/`FIELDXX` | 2,552 | 2,047 |
| 学术词表标记 `AC`（AWL） | 1,428 | 1,258 |
| 商标标记 | 1,165 | 1,131 |
| **合计（去重后）** | **26,434 个字符串** | **20,030 个词条（30.98%）** |

**用户可见实例**

| 词条 | 现在显示 | 应为 |
|---|---|---|
| `seeing` | `see·ingspoken` | `see·ing` + 语体芯片「spoken」 |
| `18-wheeler` | `18-wheel·erAmerican English AmE` | `18-wheel·er` + 地域芯片「AmE」 |
| `2` | `2written informal` | `2` + 语体芯片「written」「informal」 |
| `3-D` | `3-D( also three-D )` | `3-D` + 变体芯片 |
| `abandon` | `¹abandon   AWL` | `abandon¹` + 学术词表芯片「AWL」 |
| `20th Century Fox` | `20th Century Foxtrademark` | `20th Century Fox` + 商标芯片 |

**三个次生缺陷（同源）**

1. **嵌套交叉引用被压平**：`HOMOPHONE` 是 `<span class="HOMOPHONE"><span class="neutral span"> → </span><a href="entry://are"> are</a>, …</span>`，兜底分支用 `get_text()` 把 `entry://` 链接压成纯文本 → 同音词交叉引用变成死文本（实测产物里出现 `"→ re , aka , her , of , or , er , o , eh , are"`）。`Variant`/`AmEVariant`/`BrEVariant` 内含的 `entry://` 链接同样丢失。
2. **`title` 属性丢失**：`<span class="AC" title="Academic Word list">AWL</span>` 的悬停提示被丢弃（对比 `LEVEL`/`FREQ` 分支是有保留 `title` 的）。
3. **空白噪声与 HOMNUM 顺序**：`abandon` 的 `ld-hwd-wrap` 实际内容是
   `[ld-sup "1", ld-hwd "a·ban·don", " ", " ", " ", "AWL"]`
   —— 3 个空格来自 `sc_text` 不 strip 的空白文本节点（与 D1 同源）；且 `hwd_nodes.insert(0, …)`（:766）把 HOMNUM 放到词头**前面**，而源 DOM 顺序是 `HWD → HOMNUM`，视觉上应为 `abandon¹` 而非 `¹abandon`。

**修复方向**

```python
# render_head() 兜底分支改为查已有映射表，而不是拍平文本
else:
    chip_cls = next((CHIP_MAP[t] for t in CHIP_PRIORITY if t in cls), None)
    if chip_cls is None:
        chip_cls = next((INLINE_MAP[t][0] for t in INLINE_MAP if t in cls), None)
    if chip_cls:
        inner = self._children_blocks(child)          # 保留嵌套 entry:// 链接
        if sc_has_text(inner):
            chips.append(sc("span", inner, cls=chip_cls,
                            title=strip_invisible(child.get("title") or "") or None))
    else:
        for c in cls:                                  # 让残余泄漏可见
            self.unknown_classes[c] += 1
        text = sc_text(child.get_text(" ", strip=True))
        if text:
            hwd_nodes.append(text)
```
外加：给 `CHIP_MAP` 补 `"HYPHENATION"`（其内容是与 HWD 重复的带音节点显示形式，建议丢弃或降级为 `title`）；`HOMNUM` 由 `insert(0, …)` 改为 `append`。**改完需重跑全量并重新核对词头。**

---

### D0b【中】`HYP` 元素被硬编码成中点 —— 27% 的音标重音符被破坏 ✅ 已修复并验证

**位置**：`ldoce2yomitan.py` 的 `hwd_collect()`（`render_head` 内）

```python
if "HYP" in ccls:
    out.append(sc("span", "\u00b7", cls="ld-hyp"))   # 丢弃了元素自身的字符
```

**实测分布**（全库 146,026 个 `HYP`）：

| 真实内容 | 数量 | 占比 |
|---|---|---|
| `·` 音节分隔点 | 106,672 | 73.0% |
| `ˈ` 主重音 | **21,451** | 14.7% |
| `ˌ` 次重音 | **17,903** | 12.3% |

原来一律替换成 `·`，导致 **39,354 个（27%）重音符被写成点**。可见实例：

| 词条 | 修复前 | 修复后 |
|---|---|---|
| `second class` | `·second ·class` | `ˌsecond ˈclass` |
| `'Twas the Night Before Christmas` | `·Night Before ·Christmas` | `ˌNight Before ˈChristmas` |

**修复**：读出元素自身文本（空则回落 `·`）。已修复并计入本轮全量构建。

---

### D1【中等】纯中文释义未走 `ld-defcn` 分支 —— 影响 119,249 处（99.97%）✅ 已修复并验证

> **修复后实测**：`ld-defcn` **34 → 119,283**（+119,249）；`ld-def` 与 `ld-zh` 同步各 −119,249；
> `ld-excn`（例句中文）保持不变。数字完全对得上，确认是"容器改名 + 消除多余 span"而非内容变动。


**位置**：`ldoce2yomitan.py:1291`，`render_def()` 内的 `text_outside()`

```python
def text_outside(node):
    if not isinstance(node, NavigableString):
        return False
    if not sc_text(str(node)):      # ← BUG：sc_text 只折叠空白、不 strip，" " 为真值
        return False
```

**触发条件**：源模式为语言切换对，中文 DEF 内部有前导空白：
```html
<span class="DEF LDOCE5_switch_lang switch_siblings"> to make something <a...>better</a>, or to become better</span>
<span class="DEF LDOCE5_switch_lang switch_siblings"> <span class="cn_txt"> 改善，改进；变得更好</span></span>
```
`<span class="DEF ...">` 与 `<span class="cn_txt">` 之间的那个空格文本节点，父链止于 DEF 本身 → `text_outside(" ")` 返回 True → `cn_only` 恒为 False。

**实际输出**（`improve`，真生成器渲染结果）：
```html
<div data-sc-class="ld-def"> <span data-sc-class="ld-zh" lang="zh"> 改善，改进；变得更好</span></div>
```
**设计意图**（HANDOVER §7 明文规定"纯中文 → `div.ld-defcn[lang=zh]`"）：
```html
<div data-sc-class="ld-defcn" lang="zh"> 改善，改进；变得更好</div>
```

**量化**（全量包统计）：

| 分类 | 数量 |
|---|---|
| `ld-defcn`（正确走了 cn_only） | **34** |
| `ld-def` 内只有一个 `span.ld-zh`（**本应是 ld-defcn**） | **119,249** |
| `ld-def` 纯英文（正确） | 19,758 |
| `ld-def` 英中混排（正确） | 1 |

**影响**
- 样式丢失：`ld-defcn` 的 `font-weight:600 / margin:1px 0 3px / 独立紫色块` 未生效，中文释义退化成英文释义的排版（`font-weight:500`）。颜色仍在（`span.ld-zh` 自带紫色），所以**没有到"看不清"的程度**。
- 容器 `lang="zh"` 丢失（内层 span 仍有，故语言标注未完全丢失）。
- 多出一个前导空格（`> 改善`）造成的视觉缩进。
- 下游任何按 `ld-defcn` 取中文释义的消费者会几乎取不到（34 而非 12 万）。
- **mono 模式不受影响**：中文仍被正确剔除（已由 mono 包零 CJK 校验证实）。

**修复（已验证）**：`ldoce2yomitan.py:1291` 单行
```diff
-            if not sc_text(str(node)):
+            if not sc_text(str(node)).strip():
                 return False
```
我把该补丁写入临时副本重渲染 `improve`，输出变为：
```json
{"tag":"div","data":{"class":"ld-defcn"},"lang":"zh","content":[" 改善，改进；变得更好"]}
```
与 §7 映射表完全一致。**注意：修补后需重跑全量（约 15 分钟）才能让产物与代码重新同步。**

> 我没有直接改动 `ldoce2yomitan.py`：它是唯一事实来源，且刚被证明与已交付 zip 逐字节同步。擅自打补丁会让"代码 ↔ 产物"失配，比缺陷本身更危险。是否应用 + 重建请确认。

---

### D2【低】mono 包并非"零中文"

`AUTHOR = "海鸥 LDOCE5++ converter"`（:30）与 `desc_bits[1] = "朗文当代高级英语辞典 · 双语增强版"`（:1939）在 mono 模式下仍写入 `index.json`。实测：

```
clean  term_bank_1.json
CJK in index.json -> ['...true,"author":"海鸥 LDOCE5++ converter"...', '...5++ V2.15; 朗文当代高级英语辞典 · 双语增强版; converter v...']
clean  tag_bank_1.json / styles.css
```
`targetLanguage:"en"` 的包里出现中文元数据。内嵌校验器只扫 term bank（:1718），所以放行。不影响使用，但"纯英文包"的对外承诺不成立。

**建议**：`ui_zh = (mode == "bilingual")` 时同步切换 `AUTHOR` 与 `desc_bits`，并把 mono 的 CJK 检查扩展到 `index.json`/`tag_bank`。

---

### D3【低】`index.json` 的 `url` 指向无关项目

`PROJECT_URL = "https://github.com/shoujocyber/OALD10-Yomitan-Converter"`（:31）被直接写入词典首页字段（:1949）。该仓库是**方法论参考**，不是本词典的归属地。用户在 Yomitan 里点词典链接会被带到别人的转换器仓库。

---

### D4【低】审计脚本 `audit1_aliases.py` 有失效计数器 + 日志已过期

1. `skip_keys = Counter()`（:14）从未被写入（重算结果写进了另一个变量 `sk`），但 :56 打印 `skip records={sum(skip_keys.values())}` → **恒为 0**。同一份日志下方却正确列出 1907+184+15=2106。这是明显的自相矛盾输出。
2. 仓库里的 `audit1.log` 是**过期快照**：其中 `dropped alias count=147` + "broken @@@LINK" 分类。我用当前代码重跑同一脚本，得到 `dropped alias count=0`（与构建日志 `dropped unresolvable: 0` 一致）。该 log 与 HANDOVER §8 L4 引用的"147"容易被误读为当前状态。

**建议**：修 :56 用 `sk` 合并计数；删除或标注 `audit1.log` 为 pre-fix 快照；重新生成一份 post-fix 日志。

---

### D5【低】末级归一化兜底可能认错"孪生词条"

`norm_target()` 抹掉空白与 `↔`，导致 292 组（585 个词条）归一化键碰撞，例如 `stand still` / `standstill`、`the voice` / `thevoice`。
只有当链接目标既非 exact 也非 casefold 命中、走到最后一级 norm 兜底时才会误配，且碰撞双方语义通常同源。**风险低，但属已知盲区**（0.45% 的词条对参与碰撞）。

---

### D6【低/产品决策】源数据键卫生

全量包中确有源 MDX 原文自带的"脏键"被忠实透传：

| 模式 | 行数 | 样例 |
|---|---|---|
| 以逗号开头 | 108 | `,  ian`、`, allhallowmas`、`, 12 step (program)` |
| 含连续空格 | 9 | `carry  something ↔ out`、`cut  somebody/something off` |
| 含 `?` / `*` | 197 | `and?`、`a*`（多为真实词条如 `any luck?/no luck?`） |

我逐条回溯了源文件，确认 `,  ian`、`a*`、`and?`、`begans`、`rans` 等**都是源 MDX 里真实存在的键**（内容为 `@@@LINK=...`），不是转换器构造错误。它们会作为可搜索的 `non-lemma` 行进入词库。是否需要清洗属产品决策，建议至少在 HANDOVER 里记录。

### D7【中】频率正则永不匹配 → S1–W3 等级标签全部丢失　✅ 已修复并验证

**位置**：`ldoce2yomitan.py:1713` `FREQ_SCAN_RE`。

```python
FREQ_SCAN_RE = re.compile(r'<span class="[^"]*\bFREQ\b[^"]*">\s*([SW][123])\s*<')
```

它要求 `class` 属性是 `<span>` 的**最后一个属性**（值后紧跟 `"` `>`）。但源数据的真实写法是：

```html
<span class="FREQ" title="Top 1000 spoken words">S1
```

`class` 之后还有 `title`。实测：整个 865 MB 源文件中含 `FREQ` 的 class 属性共 **32,195 个，100% 都带 `title`**，**零个**以 class 结尾 ⇒ 该正则命中数恒为 **0**。

对照：`POS_SCAN_RE` 侥幸可用，因为源的 `<span class="lm5pp_POS">` 没有多余属性——**同一份代码里两个正则对"属性顺序"的假设不一致，一个踩中一个没踩中**。

**影响**（不是显示问题，是**元数据**问题）：

| 层 | 状态 |
|---|---|
| 词头视觉芯片 | ✅ 正常（走 bs4 类选择器，6,383 个 `ld-freq` 节点，`title="Top 1000 spoken words"` 悬停也在） |
| 行的 `definitionTags` | ❌ **一个 S1–W3 都没有**（`tags` 取值分布里完全不存在） |
| `tag_bank_1.json` 里 6 个 `frequency` 标签 | ❌ **死声明**（S1/S2/S3/W1/W2/W3 从未被任何行引用） |

即：**用户在 Yomitan 里无法按 S1/W1 过滤**，而这恰好是学习者最需要的功能。

**影响面**（用修正后的正则 `r'<span[^>]*\bclass="[^"]*\bFREQ\b[^"]*"[^>]*>\s*([SW][123])'` 实测）：

| 记录类型 | 记录数 | 含 FREQ | FREQ 次数 |
|---|---|---|---|
| entry | 64,659 | **3,405（5.3%）** | 6,383 |
| redirect | 218,252 | 0 | 0 |
| skip（topic 页，故意丢弃） | 2,106 | 1,668 | 25,812 |
| **合计** | | | **32,195** |

等级分布均衡：S1 1004 / S2 977 / S3 1208 / W1 1000 / W2 1005 / W3 1189。**5.3% 的比例不高，但命中的正是 top-1000/2000/3000 的核心词**——重要性远超其占比。修正则全文件命中 32,195/32,195，证明修法充分。

**顺带的好消息**：`tags[:6]` 截断不会出问题——POS 标签在循环里上限为 4，再加最多 2 个频率码正好 6。实测 `len(POS tags) >= 5` 的词条数为 **0**。

**修复方向**：
1. 正则改为对属性顺序不敏感：`r'<span[^>]*\bclass="[^"]*\bFREQ\b[^"]*"[^>]*>\s*([SW][123])'`。
2. 顺手让 `POS_SCAN_RE` 也改用同一宽容写法（当前只是运气好）。
3. **新增 `term_meta_bank_1.json`** 输出真正的频率数据——`[["word", "freq", {"value": N, "displayValue": "S1"}]]`（S1=1…W3=6 之类），schema 见 `yomitan-ext/data/schemas/dictionary-term-meta-bank-v3-schema.json`，`freq` 是官方支持的枚举值。这能让 Yomitan **按频率排序**，而当前包完全没有任何频率元数据（只有显示芯片）。
4. 清理 `tag_bank` 里 8 个从未使用的 partOfSpeech 声明（`excl`/`linking-v`/`combining-form`/`symb`/`idiom`/`ordinal-num`/`inf-marker`/`short-form`）——修好第 1 条后 frequency 类别就不再是死声明了。

**已排除的怀疑**（不要重复调查）：
- `rules` 用的 `n`/`v`/`adj`/`adv` **是合法的**——`english-transforms.js` 的 `conditions` 表里这 4 个都是 `isDictionaryForm: true`，`rules` 值确实应取条件名而非 tag 名。变形条件标志（`translator.js:509`→`getConditionFlagsFromPartsOfSpeech`）因此能正常解析。
- 别名行的 `rules: non-lemma` **不是合法条件**，解析结果为空标志。但别名行靠"精确表达式"命中，不依赖变形，故无实际损害；只是这一字段在语义上是空的。
- 芯片的 `title` **确实落成真 `title` 属性**（`structured-content-generator.js` 中 `hasStyle=true` 时执行 `node.title = title`），悬停提示正常。

### D8【低–中】`See picture` 交叉引用被整块丢弃 —— 影响 1,548 个记录　✅ 已修复并验证

源里的插图指针写成：

```html
<span class="Crossref imagerelated LDOCEVERSION_5 ldoce4img">
  <span class="neutral span"> →</span><span><span class="LDOCEVERSIONLOGO_5">4</span>&nbsp;</span>…
  See picture of 见图 broken
</span>
```

`imagerelated` / `ldoce-show-image` 都在 `DROP_CLASSES` 里，而 `render_*` 的 DROP 判定发生在语义分派**之前**，于是整棵子树被丢掉。

**实测**：
- 含该模式的记录 **1,548** 个（元素 ~2,279 个：`Crossref imagerelated…` 437 + 1512 + 330，`a.crossRef ldoce-show-image` 1,949，`img…` 1,774）。
- **包内 `See picture` 出现 0 次**；同族的 `见图` 还有 1,183 次（那些走了别的、未被丢弃的路径）。
- **原版是显示的**：`LM5style.css` 有 `.Crossref.ldoce4img { color:#4058a4; }`（另有 `.Crossrefto { color:blue; font-weight:bold }`）。
- 与它同族的 `EXAMPLE LDOCEVERSION_new speaker`（816 个）**不在此列**——实测 100% 是重复，同记录里必有对应的普通 `EXAMPLE`，丢弃无损。

**修法建议（低风险）**：把 `imagerelated` 从 `DROP_CLASSES` 摘出（或对 `Crossref` 单独放行），让该行按普通文本渲染成 `→ 4 See picture of 见图 broken`；同时把 `render_*` 里的 `cls & DROP_CLASSES` 判定改成"**仅当该元素没有任何已知语义类时才整块丢弃**"，避免以后再踩同类陷阱。

### 机会（暂不建议实施）：15 张插图**可以**接，但风险不对称

`.mdd` 里只有 **15 张 jpg**（`\media\lm4\1.jpg`…`15.jpg`，合计 **8.11 MB**，单张 323–805 KB），而源里恰好只引用这 15 个（`file://media/lm4/N.jpg`），约 1,774 个 `<img>` + 1,949 个锚点。

**机制上可行**：SC 的 `img` 标签会产生 `structured-content-image` 需求，由导入器从 zip 的 `fileMap` 里解析并存入 `media`（`dictionary-importer.js:565/653/690`）。做法 = 输出 `img{path:"media/lm4/N.jpg"}` + 把这 15 个文件按**完全相同的路径**写进 zip。

**但风险很高**：`_getImageMedia()` 在 `context.fileMap.get(path)` 取不到时**直接 `throw`**（`dictionary-importer.js:770`），异常会沿 `importDictionary → _resolveAsyncRequirements` 冒泡，**导致整个词典导入失败**——不是"图片不显示"，是"装不上"。而本项目**从未做过真机导入验证**（长期头号风险）。15 张图换来整个包装不上的可能性，收益/风险不划算。

**若要做，安全路径**：先打一个只含 1 张图的 3 词测试包，真机导入确认通过，再上全量。**不要盲改。**

### D9【已定案】义项标签 `ACTIV`：原版是否隐藏无法判定，**维持显示**；中文照不加

源里的义项标签（`abandon` 的 `LEAVE A RELATIONSHIP` / `LEAVE A PLACE` / `STOP DOING something`）结构是：

```html
<a href="entry://ACTIV:LEAVE A RELATIONSHIP"><span class="ACTIV">LEAVE A RELATIONSHIP</span></a>
```

**`SIGNPOST` 在源里出现 0 次** —— 也就是说 `ACTIV` 就是义项标签本身，不存在"另一个可见类"。我们把它渲染成 `ld-act`（大写、主题色芯片），**45.4% 的词条带一个非空 `ACTIV`**（12,000 词条采样，5,445 个，1,399 种标签）。

**矛盾点**：`LM5style.css` 里有 `.ldoceEntry .ACTIV { display: none; }`，真浏览器实测也是 `display:none`（`w=0 h=0`，父 `<a>` 宽 0）。但——

**关键 caveat：`.mdd` 里缺一个样式表。** 源记录引用 **3 个**：

```html
<link href="LM5style.css"> <link href="LM5style_switch.css"> <link href="LM5style_show.css">
```

而 mdd 里 **只有 2 个**（扩展名普查：`.css` × 2）——**`LM5style_switch.css` 不存在**。`LM5Switch.js` 就是切换 `switch`/`show` 两套样式的开关，所以"谁覆盖谁"由那个缺失文件决定。

⇒ **不能断定原版隐藏义项标签。** 反过来，若按 `LM5style.css` 照做，很可能把 LDOCE 标志性的义项标签（signpost）全部删掉——那是**删内容**，代价比显示它大得多。

**建议：维持现状（显示）。** 它信息量正确、对我们有利，且"应该隐藏"的证据不成立。

### ⚠ 方法论修正：`LM5style.css` 不是完整的排版基准

D9 暴露了一件影响全盘的事：**我们取出的原版 CSS 只是 3 个样式表里的 2 个**，缺 `LM5style_switch.css`。因此：

- 凡"原版把 X 设为 `display:none` ⇒ 我们应该丢弃 X"的推断，**一律不可靠**（可能被缺失文件重新显示）。
- 凡"原版给 X 设了正向样式（颜色/字号）⇒ X 是可见的"这类推断**相对可靠**（缺失文件不太可能专门为它加正向样式）。
- 已验证不依赖该文件的三条（T8 顺序、HOMNUM 上标、HYPHENATION 隐藏）仍然成立：无 `order:` 是无条件的；`HYPHENATION` 与 `HWD` 互斥且有 `LM5Switch.js` 的显式 toggle 逻辑佐证；HOMNUM 的 `vertical-align:super` + DOM 顺序两边一致。

### D7 / D8 的修复与验证（2026-09-10）

**D7 改法**（`ldoce2yomitan.py`）：
1. `FREQ_SCAN_RE` / `POS_SCAN_RE` 改为对**属性顺序不敏感**：`<span[^>]*\bclass="[^"]*\bFREQ\b[^"]*"[^>]*>\s*([SW][123])(?![0-9])`。
2. 新增 `term_meta_bank_*.json` 输出真实频率元数据：`[["the","freq",{"value":1000,"displayValue":"S1"}], …]`，`value` 取该等级的**上限名次**（S1/W1=1000、S2/W2=2000、S3/W3=3000），lower = 更常用，正是 Yomitan 频率排序所需。内置校验器同步新增 freq 行形状与"词条必须存在"检查。
3. 清理 `--keep-json` 的临时文件时把 `term_meta_bank_*` 一并纳入。

**回归证据**：新旧 POS 正则在全文件上产出**完全相同**的 147,336 条（`op == np_ → True`），即放宽只增强健壮性、无行为变化；FREQ 命中数 **0 → 32,195**（与预期逐条吻合）。

**D8 改法**：新增 `is_dropped(cls)` 取代裸的 `cls & DROP_CLASSES` —— 一个元素可以同时带**有意义的类**和被丢弃的类（`Crossref imagerelated LDOCEVERSION_5 ldoce4img`），按首个命中就丢会连带丢掉真实内容。`DROP_EXEMPT = {"Crossref", "crossRef"}` 允许这两者胜出。全部 6 处 DROP 判定点统一改走该函数。

**调试包验证**：`child` → `noun S1 W1`、`improve` → `verb phrasal-v S2 W1`、`the` → `def-article adv prefix S1 W1 S3`；`term_meta_bank_1.json` 正确进包；`See picture` 渲染为 `ld-crossref`（`→ See picture of 见图 …`）。

**改动过程中我自己犯的两个错（已修，记录以备后人）**：
- **元数据没进包**：zip 在 Pass B **之前**就已打开（银行是流式写进去的），我却把 `term_meta_bank` 写成磁盘文件 ⇒ 包内根本没有。必须走 `zf.writestr(name, payload)`。
- **循环变量遮蔽**：写成 `for start in range(...)`，而 `start` 正是 build 的起始时间 ⇒ `Elapsed` 输出成 1789047636.6s。改名为 `offset`。

### D9 定案（含"中文照不加"的决定）

`ACTIV` 义项标签（`LEAVE A RELATIONSHIP` 等）**继续显示**，理由见下节。关于"给标签加中文"：**不加**。

**因为源里根本没有这份对照**，四条独立证据：
1. ACTIV 锚点只有英文：`<a href="entry://ACTIV:LEAVE A RELATIONSHIP"><span class="ACTIV">LEAVE A RELATIONSHIP</span></a>`；
2. `SIGNPOST` / `ACTIV_cn` 之类的中文类在源里出现 **0 次**；
3. `ACTIV:LEAVE A RELATIONSHIP` 主题页里有中文，但那是**该主题下各词条**的释义/例句（`抛弃`/`遗弃`/`她怎么能抛弃自己的孩子呢`…），不是标签本身的翻译；
4. `ACTIV:` 排行索引页（`<span class="_ACTIV_" title="rank:14 total:155">MONEY</span>`）**0 个中文**。

要加就只能**自己编一张对照表** —— 共 1,914 个不同标签，top 200 只覆盖 45.5%、top 400 覆盖 69.3%、top 800 覆盖 92.4%。**决定：不引入自撰内容，保持词典内容忠实。** 若将来要加，机制已就位：`render_link` 里的 ACTIV 分支可挂一张 `ACTIV_ZH` 表，中文渲染为 `ld-actcn`（该 class 的 CSS 已存在，只需把它从 `margin-right` 改成 `margin-left` —— 已顺手改好，对现有的 `cn_topic` 中文也更正确）。

**已排除的怀疑（本轮，勿重复调查）**：
- **`.suppressed`（含 `suppressed LEXVAR`，5,109 个）丢弃正确**：`.suppressed { display: none; }`，且 `suppressed` 语义即"被抑制的异体词头"。注意 `Head suppressedLEXVAR` 是**另一个 token**（`suppressedLEXVAR`），不在 DROP 里，会被正常当作 Head 处理。
- **`EXAMPLE LDOCEVERSION_new speaker`（816 个元素 / 459 记录）丢弃无损**：100% 在同记录里能找到等价的普通 `EXAMPLE`。
- **`lm5pp_popupitem`/`dictionary_intro`/`lm5ppMenu*` 等**（合计 8 万余个）是导航 UI，丢弃正确。
- **269 个重复表达式不是缺陷**：逐条比对，**0 个是纯冗余**（内容与标签都相同），全部是同形词（如 `act up` 同时有 phrasal-v 行与普通行）。
- **`Tail`（7,196 个，最大的未知类）不是内容丢失**：它是交叉引用行（`→ breakdown`、`→ give up the ghost at ghost 1(5)`），内容在包内（`breakdown` 357 次、`give up the ghost` 12 次）。原版只给它一条 `.PhrVbEntry .Sense ~ .Tail { margin-left:20px }` 的缩进，**我们少的是这个缩进样式，不是内容**。
- **文本守恒整体干净**：800 词条采样，未到达输出的词元 **3,349 / 192,189 = 1.743%**，且集中在 landscape 语法码（`c/u/a/adj/t/i/adv/v/phr`）、音频按钮标签（`bre/ame`）与 word-family 的重复标注——都不是丢失（`disadvantageous` 18 次、`overact` 62 次都在包内）。
- **`cls & DROP_CLASSES: continue` 的顺序脆弱性是真实代码异味，但当前不产生错误后果**（受影响的类经逐项核查都该丢）。仍建议改成"仅当没有任何已知语义类时才整块丢弃"，以防换皮时踩坑。

**新增门禁**：`converter/audit9_text_conservation.py`（逐词条文本守恒，含故意的丢弃模型；注意 SC 侧只统计 `content` 字符串，**绝不能把 `tag`/`lang` 的值算进去**，否则会得出"输出比源多 1.5 倍"的假象——我在本轮先踩了一次）。

---

## 3. 代码异味与可维护性

| # | 位置 | 问题 |
|---|---|---|
| 1 | :84 `add_class()` | 定义后从未调用 |
| 2 | :465/:477 `TermIndex.rendered` / `finalize_rendered()` | 只写不读；`resolve()` 从不使用它 |
| 3 | :553/:1319 `self.current_key` | 只写不读 |
| 4 | :688-689、:693-694 | `render_div` 中 6 行不可达（`Head`/`Inflections` 已在 :681/:686 提前 return） |
| 5 | :606-609 | `render_element` 的 `_has_block_child` 内 `Head` 分支不可达（:595 已拦截） |
| 6 | :106-117 `merge_adjacent_text()` | if/else 两分支结果完全相同 → 条件恒无意义；且该函数**从不补空格**，词间距完全依赖源文本节点，因此 :121-130 之类的"补空格"逻辑散落各处 |
| 7 | :163-164 vs :1216-1220 | `INLINE_MAP` 的 `cn_txt`/`cn_txt_ext` 条目被前面的显式分支永久拦截，永不生效 |
| 8 | :156 `UNWRAP_CLASSES` | 混入 `"span"`/`"div"`/`"a"` 三个"元素名当类名"的残留 |
| 9 | :8 文件头注释 | 仍写 "Part 1 of 2 (core + renderer). Assembled by build script." —— 与"单文件唯一事实来源"的事实矛盾，正是 HANDOVER §4 警告的误合并风险点 |
| 10 | :982 `b.extract()` | `render_asset` 在父节点 `for child in el.children` 遍历**中途**抽走兄弟节点。当前恰好正确（bs4 `children` 是列表迭代器，抽走后续项正好使其被跳过），但这是靠实现细节偶然成立，极易被后续改动破坏。建议改两阶段（先收集、后统一跳过） |
| 11 | :1716-1726 | `validate_package` 每个 bank **反序列化两遍**（先收集表达式集合，再逐行检查），470MB 白解析一次 |
| 12 | :1787 `count_lines()` | 为给 tqdm 一个总数，额外完整读一遍 877MB；且 `n_lines // 2` 只是估算，实际 285,017 条记录 |
| 13 | :905-906、:982 | `render_box`/`render_asset` 就地 `decompose()/extract()` 修改共享 soup，渲染函数不再幂等，调试与复算困难（本报告的重渲染之所以能 100% 复现，正是因为每次都从原始字符串重建 soup） |

**冷知识（有用的诊断副产品）**：17 条 CSS 规则定义了但从未命中，可反推哪些源结构不存在——
`ld-actcn, ld-block, ld-corpexa-{encyc,online,phrases}, ld-frequency, ld-hint-inline, ld-homophone, ld-infl-lab, ld-num, ld-panel-boxbody, ld-para, ld-sense-merge, ld-table, ld-td, ld-th, ld-xref`

其中 **`ld-table/ld-td/ld-th` 未命中 ⇒ `_render_table()` 在本源上从未触发过**（整条 table 分支是死路径）；**`ld-sense-merge` 未命中 ⇒ 源库无 `merge_sense`**；`ld-para` 未命中 ⇒ 源库无 `<p>`。这些可作为下次"换皮到其它 LM5pp 词典"时的清理依据。

---

## 4. 校验体系的可靠性评价

| 层 | 声明 | 我的结论 |
|---|---|---|
| L1 内嵌校验器 | 全 245,933 行 | **可信**。我独立复算了它最关键的"零悬挂"断言（63,647 个链接目标 / 52,138 个重定向目标），结论一致 |
| L2 官方 Schema | 20% 分层抽样 | **声明诚实**（HANDOVER 明说不跑全量并给了理由），抽样 + 极值方法合理 |
| L3 真生成器 | 405/405 | **可信且已复现**；生成器本体与 release 逐字节相同，stub 边界清晰 |
| L4 语义普查 | 别名/链接分类 | **结论可信，但工具与日志需修**（见 D4） |

**一处补强建议**：L1 的 `validate_package` **不检查序列号唯一性/连续性**（只检查 `row[6]` 是 int）。"seq 0..245932 连续无洞"这个结论目前只由 L2 的 `audit2_schema.py` 提供，构建时并不校验。建议把这 3 行检查内嵌进 L1：

```python
seqs = set()
...
seqs.add(row[6])
...
if len(seqs) != max(seqs) + 1:
    errors.append(f"sequence gap: {len(seqs)} unique vs max {max(seqs)}")
```

---

## 5. 文档与审计链的不一致

| 位置 | 问题 |
|---|---|
| `README-yomitan.md:8` | "**14 个**测试词条的调试包" |
| `HANDOVER.md` §1 | "**13 个**测试词条的调试包" |
| 实测 `yomitan_debug/…DEBUG.zip` | **11 个** score=10 的词条行（A / and / begin / child / decision / get / however / improve / run / second class / the），加 67 条别名行共 78 行 |
| `README-yomitan.md:32` | 称 Schema 校验"对**全部** 25 个 bank … 做整体校验"，实际是 **20% 分层抽样**（HANDOVER 写得很准确，README 过度承诺） |
| `README-yomitan.md:33` | "仅 stub contentManager"，实际 stub 了 **3 个**模块（display-content-manager / text-utilities / anki-template-renderer-content-manager） |
| `audit1.log` | 过期快照，含 `skip records=0` 这一恒错的输出（见 D4） |
| `HANDOVER.md` §9.6 | 建议删除/改名 `part1.py`/`part2.py` —— **本次审查仍看到二者留在 `converter/` 里**（11:17 / 11:19，均早于主文件 13:36），误合并风险仍在 |

---

## 6. 未覆盖 / 残余风险

1. **真机导入验收仍未做**（HANDOVER 已如实标注）。本报告验证的是"结构合法 + 能被真生成器渲染成 DOM"，不等于"Yomitan 扩展导入后 UI 正确"。chrome-devtools MCP 连不上的问题本次未尝试绕过。
2. **别名行未做字节级复现**（我的重渲染只覆盖 63 行，无法复算 18 万条别名行）。但它们的**目标存在性**已被独立扫描全量证实（52,138 个目标 0 悬空）。
3. **无 `.mdd`**，音频/图片链路完全未验证（设计上已剥离）。
4. **深色模式 / 真实浏览器视觉**未核对（`@media (prefers-color-scheme: dark)` 仅静态检查通过）。
5. **归因准确度**：`author` 字段写的是工具名而非词典编者，`url` 指向方法论参考仓库（D3），版权归属信息不完整。

---

## 7. 建议动作（按优先级）

| 优先级 | 动作 | 代价 |
|---|---|---|
| P0 | 应用 D0 修复（`render_head` 兜底分支改查 `CHIP_MAP`/`INLINE_MAP` + 补 `HYPHENATION` + HOMNUM 改 append）→ 重跑全量 → 抽查 `seeing`/`18-wheeler`/`abandon` 词头 | ✅ **已完成**（词头污染 16,751 → 0） |
| P0 | 应用 D1 单行补丁 → 重跑全量 → 确认 119,249 处变为 `ld-defcn` | ✅ **已完成**（34 → 119,283） |
| P0 | D0b：`HYP` 保留真实字符（重音符） | ✅ **已完成** |
| P1 | 清理 `part1.py`/`part2.py`（改名 `*_STALE` 或删除），消除误合并风险 | 1 分钟 |
| P1 | 修 D4：`audit1_aliases.py:56` 改用 `sk`；重新生成 post-fix 日志；标注旧 log | 5 分钟 |
| P2 | 修正 README/HANDOVER 的三处数字（14/13/11、20% 抽样、3 个 stub） | 5 分钟 |
| P2 | D2/D3：mono 元数据去中文；`url` 字段改为词典自身或留空 | 10 分钟 |
| P2 | 把"seq 连续性"内嵌进 L1 校验器（§4 补强） | 5 分钟 |
| P3 | 清理 §3 的 13 项死代码/异味（尤其 #6 合并空格语义、#10 遍历中 extract） | 1-2 小时 |
| P3 | 修 17 条未使用 CSS 中确认无用的（table 系列、ld-sense-merge 等） | 20 分钟 |

---

## 8. 复现命令

```bash
cd C:/workspace/ldoce
export PYTHONIOENCODING=utf-8

# ① 代码 ↔ 产物一致性 + 抽样重渲染（约 2.5 分钟，需重放 Pass A）
"C:/workspace/ldoce/venv/Scripts/python.exe" -u converter/audit3_reproduce.py

# ② 独立结构扫描（约 1 分钟，含 SC 白名单/链接目标/CSS 覆盖/别名遮蔽）
"C:/workspace/ldoce/venv/Scripts/python.exe" -u converter/audit4_structure.py

# ③ 真 Yomitan 生成器渲染（L3 复现）
cd scgen_test && NODE_PATH=./node_modules \
  "C:/Users/zitons/.workbuddy/binaries/node/versions/22.22.2/node.exe" run_scgen.mjs payload.json improve

# ④ 别名审计（当前代码下 dropped=0）
"C:/workspace/ldoce/venv/Scripts/python.exe" -u converter/audit1_aliases.py
```

—— 报告完 ——
