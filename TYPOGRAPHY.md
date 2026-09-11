# 排版审查（样式/CSS 层）

> 对象：`converter/ldoce2yomitan.py` 的 `generate_css()`（118 条规则）与重建后的 `yomitan_full` 包
> 方法：读 CSS + 统计包内实际 SC 结构 + 对照 `yomitan-ext/css/display.css` 的主题实现

---

## 修订记录：T1–T5、T7 已全部实施（T6 采取"标注保留"）

### ⚠️ T1 第一版做错了，已重做（真浏览器实测推翻了原方案）

**第一版方案**（错）：基础色继承 `var(--text-color)`，暗色调色板写在
`:root[data-theme=dark] [data-sc-class="ld"]` 下。

**为什么错**：Yomitan 会把词典的整个 `styles.css` 用 `addScopeToCss()` 嵌套包裹
（`yomitan-ext/js/display/display.js:1317`：
`customCss += addScopeToCss(styles, '[data-dictionary="…"]')` → `[data-dictionary="…"] { …全部 CSS… }`）。
在 CSS 嵌套里，一条不以 `&` 开头的嵌套规则会被隐式加上**后代组合符**，于是
`:root[data-theme=dark] …` 变成 `& :root[data-theme=dark] …` —— 要求 `:root` 是本词典元素的**后代**，
永远不可能匹配。实测（复刻嵌套 + 真 Chrome）确认：

```
ld 根节点  color = rgb(212,212,212)  ✓  基础色继承生效（这半边是对的）
ld-hwd-wrap color = rgb(28,30,33)    ✗  暗色调色板整体失效 → 词头在 #1e1e1e 上对比度 1.02:1，不可见
ld-zh/pos/register/… 全部仍是亮色值   ✗
```

顺带确认：`color-mix()` 能存活（弹窗路径只做 `styleNode.textContent = css`，**不消毒**；
`sanitizeCSS()` 只用于外部 API 路径）。

**第二版方案（现行，已实测）**：**完全不依赖主题选择器**，把调色板从"继承来的文字色"派生：

```css
[data-sc-class="ld"] {
  /* 中性色 = 文字色的降透明度版本（叠加到任何背景上都自适应） */
  --ld-text2: color-mix(in srgb, var(--text-color, currentColor) 88%, transparent);
  --ld-dim:   color-mix(in srgb, var(--text-color, currentColor) 70%, transparent);
  --ld-faint: color-mix(in srgb, var(--text-color, currentColor) 55%, transparent);
  /* 词头就是主题文字色，绝不写死 */
  --ld-head:  var(--text-color, currentColor);
  /* 彩色 = 中间调色相混 32% 的文字色：亮主题下变深、暗主题下变浅，自动双向收敛 */
  --ld-zh:    color-mix(in srgb, #a274e8 68%, var(--text-color, currentColor) 32%);
  ...
}
```

文字色在亮主题是 `#000`、暗主题是 `#d4d4d4`，且**会继承**——所以不需要选中主题就能双向适配。

**真浏览器实测**（真实 `styles.css` + 按 Yomitan 方式嵌套 + 真实 SC 结构，明暗各一套）：

| 元素 | 亮 | 暗 | | 元素 | 亮 | 暗 |
|---|---|---|---|---|---|---|
| 词头 `ld-hwd-wrap` | 21.0 | **11.3** | | 义项编号 `ld-snum` | 6.3 | 6.4 |
| 音节点 `ld-hyp` | 4.7 | 4.3 | | 中文释义 `ld-defcn` | 6.4 | 6.5 |
| 语法 `ld-gram` | 7.0 | 6.0 | | 中文例句 `ld-excn` | 6.4 | 6.5 |
| 音标 `ld-pron` | 16.5 | 9.0 | | 面板标题 `ld-panel-title` | 6.3 | 6.4 |
| 词性 `ld-pos` | 7.0 | 6.0 | | 链接 `a` | 6.5 | 6.3 |
| 语体 `ld-register` | 6.5 | 6.3 | | 注释 `ld-gloss` | 8.5 | 6.2 |
| 学科 `ld-field` | 6.9 | 6.2 | | 地域 `ld-geo` | 7.5 | 5.7 |

**全部元素在两个主题下 ≥ 4.3:1。** 词头从 1.02:1（不可见）变成 11.3:1。
若宿主不支持 `color-mix()`，声明被丢弃 → 元素回落到继承的文字色，属于**降级但仍有可读性**。

**还发现一个附带教训**：`preview.html` 是"用旧包生成的静态页 + 宿主 OS 报暗色"时，
旧的媒体查询方案会把暗色调色板套到白色预览页上，词头变成 `#e8eaed`（对比度 1.13:1）。
`preview.py` 现在显式声明 `:root { color-scheme: light }` 以免再被宿主偏好影响。

改动集中在 `generate_css()`（CSS 从 118 类增至 120 类，**无任何类被删除**），外加渲染器两处。
**逐选择器属性对比**（新旧 CSS 反解后比较）确认：唯一"无意"的属性变化是 `ld-act`/`ld-synmark`
丢了 `font-weight:700`、表格边框丢了暗色适配 —— 均已补回。其余属性变化都属于 T7 的统一（芯片字号/间距）。

| 项 | 状态 | 做法 |
|---|---|---|
| T1 主题机制 | ✅ | 基础色改 `var(--text-color,#202124)`；暗色改用 `:root[data-theme=dark]`；媒体查询降级为"仅当 `:root:not([data-theme])` 时生效"（保住预览页行为） |
| T2 暗色配色 | ✅ | 21 色抽成 `--ld-*` 变量，两套值集中定义；新增 `color-scheme:dark` |
| T3 重音符 | ✅ | 新增 `ld-stress`；`hwd_collect` 与 `render_inline_node` 按内容分派（`·`→`ld-hyp`，`ˈ`/`ˌ`→`ld-stress`）；`INLINE_MAP` 的 HYP 条目删除并加注释 |
| T4 义项空缩进 | ✅ | 新增 `ld-sense-n`，仅在义项确有编号时以多 token 形式追加；CSS 用 `~=` 匹配，基础规则不受影响 |
| **T4b 副义项编号越界** | ✅ | **实施中新发现**：5,742 个 `ld-subsense` 带编号，而 `ld-snum` 悬出量（1.9em）大于 subsense 自身缩进（1.6em）→ 编号会越界 0.3em 压到父级正文上。已加 `--ld-gutter-sub` 并用后代选择器限定 |
| T5 等级色对比度 | ✅ | `#f0a020` → `#a06a00`（白底约 4.6:1），暗色下 `#ffcc66` |
| T6 死规则 | ⚠️ 保留 | 不删除，改为加 `Reserved:` 注释块说明"本源无对应结构，换皮 LDOCE6 时可能有用"。删除无功能收益、却有换皮风险 |
| T7 芯片风格 | ✅ | 6 类带框芯片抽成共享底座（`color-mix` 按 `currentColor` 自动适配明暗），间距统一 `--ld-chip-gap`、字号统一 `--ld-chip-size`；各芯片保留自己的色相以承载语义 |

**验证结果**（全量包已重建，665 s）

| 门禁 | 结果 |
|---|---|
| 内嵌校验器 | `rows=245933 dangling=0 seq_ok=1` |
| `audit3` 逐字节复现 | **45/45 一致，0 差异**（代码↔产物同步；且该工具自身的 `style` 字典误报已修，现报 `none`） |
| `audit4` 独立结构 | SC 违规 `NONE`、63,805 链接目标与 52,138 重定向目标 **0 悬挂**、`CSS used=104 defined=120 missing=[]` |
| `audit5` 词头污染 | `0 (0.00%)`（前几轮的修复未被破坏） |
| 新类计数 | `ld-hyp` 53,337 **100% 为 `·`**；`ld-stress` 19,678（`ˈ` 10,726 + `ˌ` 8,952）；`ld-sense` 61,622 / `ld-sense ld-sense-n` 63,079 |
| CSS 声明级对比 | 旧 118 选择器 → 新 120；消失的 4 个全是"旧暗色覆盖规则"（已被 `--ld-*` 变量取代）；属性值变化全是"字面量 → 变量" |
| `color-scheme:dark` | 出现 2 次（`data-theme` 块 + OS 回退块）；基础前景不再硬编码 `#202124` |

**下一步可选**：`color-mix()` 需要 Chrome 111+ / Firefox 113+（Yomitan 的运行环境满足）。若要在更老的宿主里也保证芯片有边框，可加一组不带 `color-mix` 的降级声明（会退化成无边框，功能不受影响）。

---

## T1【严重】主题机制用错了 —— 4 种"Yomitan 主题 × 操作系统主题"组合里有 2 种**完全不可读**

**证据。** Yomitan 的主题由**它自己的设置**通过根元素属性切换：

```
yomitan-ext/css/display.css:184   :root[data-theme=dark] {
yomitan-ext/css/display.css:111        --background-color: #ffffff;   --text-color: #000000;   ← 亮
yomitan-ext/css/display.css:188        --background-color: #1e1e1e;   --text-color: #d4d4d4;   ← 暗
```

而我们的 `styles.css` 用的是 **跟随操作系统**的媒体查询，并且在亮色块里**硬编码**了前景色：

```css
[data-sc-class="ld"] { color:#202124; ... }          /* 硬编码近黑 */
@media (prefers-color-scheme: dark) { ... }          /* 跟 OS 走，不跟 Yomitan */
```

两者不同步时就会出事：

| Yomitan 设置 | 操作系统 | 结果 | 对比度 |
|---|---|---|---|
| 暗（bg `#1e1e1e`） | 亮 | 媒体查询不触发 → 文字 `#202124` 落在 `#1e1e1e` 上 | **1.02 : 1**（等于看不见） |
| 亮（bg `#ffffff`） | 暗 | 媒体查询触发 → 文字 `#dadce0` 落在白底上 | **1.39 : 1**（同上） |

**修复方向**：
1. 基础前景色改成继承 Yomitan 的变量：`color: var(--text-color, #202124)`。
2. 暗色覆盖的选择器从媒体查询换成 `:root[data-theme=dark] [data-sc-class="ld"]`。
3. 若还想保留"预览页/E' 非 Yomitan 环境"下跟随 OS 的行为，写成
   `@media (prefers-color-scheme: dark) { :root:not([data-theme]) [data-sc-class="ld"] { … } }`
   —— 只在 Yomitan 没设主题时才跟 OS。

---

## T2【中等】暗色方案只做了一半：21 种颜色里只覆盖了 7 种

**证据。** 亮色块用了 21 种颜色，`@media` 块只重定义了 7 种。未覆盖的 14 种（全是暗色系）：

```
#202124 #1c1e21 #0b57a4 #147c50 #5b6420 #b3541e #6a3fa8 #8a3ffc
#f0a020 #c5221f #3c4043 #444 #555 #666 #777 #888 #999 #5f6368 #a06a00 #0a66c2
```

也就是说：即使 T1 修好、暗色块能触发，**词性/语法芯片（`#0b57a4`）、义项编号与面板标题（`#147c50`）、学科标签（`#5b6420`）、语体标签（`#b3541e`）、中文（`#6a3fa8`）在暗底上依然是暗色**，读起来很吃力。

**修复方向**：把配色抽成变量，只在一处定义两套值。

```css
[data-sc-class="ld"] {
  --ld-pos:#0b57a4; --ld-frame:#147c50; --ld-zh:#6a3fa8; --ld-reg:#b3541e;
  --ld-field:#5b6420; --ld-warn:#c5221f; --ld-dim:#5f6368; --ld-link:#0a66c2;
}
:root[data-theme=dark] [data-sc-class="ld"] {
  --ld-pos:#8ab4f8; --ld-frame:#6fd39b; --ld-zh:#c9a6ff; --ld-reg:#f0a86a;
  --ld-field:#b6c46a; --ld-warn:#ff8a80; --ld-dim:#9aa0a6; --ld-link:#8ab4f8;
}
```
然后把 118 条规则里的硬编码色替换成 `var(--ld-*)`。改动集中、可机械替换。

---

## T3【中等】`ld-hyp` 现在同时承载"中点"和"重音符"，但样式只适合中点 ⚠️ **这是上一轮修复引入的副作用**

**证据。** 包内 `ld-hyp` 节点的内容分布：

| 内容 | 数量 | 含义 |
|---|---|---|
| `·` | 53,335 | 音节分隔点 |
| `ˈ` | 10,725 | 主重音 |
| `ˌ` | 8,951 | 次重音 |

而样式是：

```css
[data-sc-class="ld-hyp"] { color:#9aa0a6; padding:0 1px; }
```

于是 **19,676 个重音符被渲染成灰色、且左右各带 1px 内边距**：

- 颜色不对：LDOCE 的重音符与词头同色，现在它是灰的，和词头其他字母割裂。
- 间距不对：`padding:0 1px` 让重音符与后面的音节分开，`ˌsecond ˈclass` 会显示成 `ˌ second ˈ class`。重音符是**紧贴**音节的。

**修复方向**：在 `hwd_collect()` 里按内容分派 class —— `·` 继续走 `ld-hyp`（灰点专属），`ˈ`/`ˌ` 走新类 `ld-stress`：

```css
[data-sc-class="ld-stress"] { color:inherit; }
```
⚠️ 新增 class 必须同步加进 `generate_css()`，否则内嵌校验器的"每个 class 都要有 CSS 覆盖"检查会报 FF。加完需重跑一次（约 11 分钟）。

---

## T4【中等】49.4% 的义项带有 1.9em 的**空白缩进**

**证据。** 包内 `ld-sense` 节点：**无编号 61,622 / 有编号 63,079** —— 近一半没有义项编号（LDOCE 只对多义项编号）。

样式用的是悬挂缩进：

```css
[data-sc-class="ld-sense"] { padding-left:1.9em; }
[data-sc-class="ld-snum"]  { margin-left:-1.9em; }   /* 编号回填到缩进区 */
```

没有编号时，那 1.9em 就是**空的**。在 Yomitan 弹窗（约 400px 宽）里，这 1.9em 大约占掉 5% 的行宽，而且会让"单义项词条"和"多义项词条"的左边界不一致，视觉上参差不齐。

**修复方向**（推荐后者，不依赖 `:has()` 兼容性）：渲染器在有编号时给义项加个修饰类，CSS 只对该类缩进：

```python
# render_block_by_token / Sense 分派处
if sense_has_number: node = add class "ld-sense-n"
```
```css
[data-sc-class="ld-sense-n"] { padding-left:1.9em; }
```
或直接用 `[data-sc-class="ld-sense"]:has(> [data-sc-class="ld-snum"])`（Chrome 152 支持，但保守起见不推荐单独依赖）。

---

## T5【轻微】`ld-level`（●●● 核心词等级）对比度 2.2 : 1

`#f0a020` 落在白底上约 **2.2 : 1**，低于 WCAG 对非文本/小字号文本的建议阈值。它承载的是"核心词等级"这个有意义的信息，不是纯装饰。同时它也没有暗色变体（见 T2）。

**修复**：改用更深的琥珀色（如 `#a06a00`，白底约 4.6 : 1），或在暗色下换成 `#ffcc66`。

---

## T6【轻微】16 条 CSS 规则从未命中

`ld-table` / `ld-td` / `ld-th`（本源没有表格）、`ld-sense-merge`、`ld-para`（本源没有 `<p>`）、`ld-block`、`ld-corpexa-encyc` / `-online` / `-phrases`（只出现 corpus/dics）、`ld-frequency`、`ld-infl-lab`、`ld-num`、`ld-panel-boxbody`、`ld-xref`、`ld-actcn`、`ld-hint-inline`。

删掉能减小 `styles.css`；留着也无害（只是说明对应分支在本源上是空跑）。**注意**：如果打算换皮到别的 LM5pp 词典（LDOCE6 等），这些规则可能会派上用场，所以删除要谨慎。

---

## T7【设计意见】词头行的信息密度

一个典型词条（`improve`）的词头行要放：词头 + 音标 + 词性 + ●●● + S2 + W1，还有 `abandon` 那种再加 AWL 芯片。在 400px 弹窗里常常折成 2–3 行，字号从 1.28em 到 0.72em 混杂，读起来有点碎。

可选方向（纯主观，供参考）：
- 把频次/等级/学科这一类"元信息"统一收到一个次要行，或统一成同一种芯片样式（目前 `ld-level` 是橙色文字、`ld-freq` 是描边胶囊、`ld-field` 是无底色大写字母、`ld-register` 是描边胶囊 —— 四种风格并存）。
- 芯片的 `margin-right` 目前各写各的（`.25em` / `.35em` / `.3em`），统一成一套间距刻度会更整齐。

---

## T8【中等】词头元信息顺序写死，不跟随源顺序 ✅ 已修复并验证

**这是本轮"真的看一眼截图"才发现的**（静态分析和结构校验都查不出来）。

`render_head()` 按固定次序拼装词头行：`hwd-wrap → gram_nodes → pron_nodes → pos → chips → infl`，
与源 DOM 顺序无关。实测对照：

| 词条 | 源 Head 直接子元素顺序 | 修复前的渲染结果 |
|---|---|---|
| `18-wheeler` | `HWD, PronCodes, lm5pp_POS, GRAM, GEO` | `18-wheel·er **[countable]** /…/ noun American English` ← 语法框跑到音标前面 |
| `abandon` | `HWD, HOMNUM, PronCodes, tooltip, FREQ, AC, lm5pp_POS, GRAM` | `abandon¹ … W3 verb [transitive] AWL` ← FREQ/AC 被从 POS 之前挪到之后 |

### 争议已由 .mdd 里的原版 CSS 终结

拿到 `LDOCE5_V_2-15.mdd` 后取出了原版 `LM5style.css`（54,085 B），三条硬证据：

1. **词头区域没有任何 `order:` 或绝对定位** —— 全文件 15 处 `order:` 无一在 Head 相关规则里，`.Head` 是 `display:inline`。⇒ **视觉顺序 = DOM 顺序**。
2. `.ldoceEntry .HOMNUM { vertical-align: super; }` ⇒ 编号是**原地**上标，DOM 是 `HWD → HOMNUM`，所以渲染应为 `abandon¹`。**证实之前 `insert(0)`→`append` 的修复是对的。**
3. `.ldoceEntry .HYPHENATION { display: none; }` ⇒ 音节切分是**默认隐藏**的显示副本（由 `LM5Switch.js` 与 HWD 互斥切换）。**证实丢弃 HYPHENATION 是对的。**

另外把源 HTML 套上原版 CSS 在 Chrome 里实测（`_original_render.html`、`shot_original.png`），得到原版真实顺序：

```
HWD → HOMNUM → PronCodes → tt/LEVEL(●●●) → FREQ(S/W) → AC(AWL) → POS → GRAM → GEO → REGISTERLAB → Variant → HOMOPHONE → [speaker ×2]
```

### 修法

`render_head()` 重写为**单次遍历、遇到什么发什么**：维护一个 `out` 有序列表与一个"词头簇"缓冲
（HWD + HYP + HOMNUM，仍合并进一个 `ld-hwd-wrap`），遇到非词头元素就 flush 缓冲、把该元素追加到 `out`。
`Inflections` 也回到它的 DOM 位置（实测它恒在两个 speaker 按钮之前），不再强行追加到末尾。

**顺带修好一个之前没人注意的丢失**：`pos_text` 原来是单个字符串槽位，多条 `lm5pp_POS` 会**只保留最后一条**。
如 `the` 源里有 `definite article` 和 `determiner` 两条，修复前只剩后者。现在两条都在。（全库 43 条 `the`-类多词性词条受益。）

### 验证

新增门禁 `converter/audit8_head_order.py`：把源里**每一个** `.Head` 块（同形词、子词条各有自己的 Head，需逐块配对；词源 `span.etym` 里的 Head 要排除）与输出的 `ld-head` 块按文档顺序配对，逐 token 比对。

```
8,000 词条采样：Head 块 9,040 个 → 顺序一致 7,955 / 不一致 0 / 数量不符 0  → exit 0
```

**未改配色**（按你的要求保留现有主题自适应调色板），只修正顺序。原版是一条亮色专用配色（词头红、词性/语法绿、语域紫、地域深蓝、AWL 黄底白字），与我们的 `color-mix` 派生方案取向不同，如需对齐是另一个独立决定。


| 优先级 | 项 | 改动量 | 需重建 |
|---|---|---|---|
| **P0** | T1 主题机制（不改就是 2/4 场景不可读） | 中（选择器 + 基础色） | 否（只改 CSS 也得重建才能进包） |
| **P1** | T2 暗色配色补全（与 T1 一起做最省事） | 中（抽变量 + 替换） | 否 |
| **P1** | T3 `ld-stress` 新类 | 小（渲染器 + 1 条 CSS） | **是** |
| **P2** | T4 义项缩进修饰类 | 小 | **是** |
| **P3** | T5 等级色、T6 死规则清理、T7 视觉统一 | 小 | 否 |

**T1/T2/T5/T6 只动 `generate_css()`，T3/T4 要动渲染器。** 建议**合并成一次改动 + 一次重建**（约 11 分钟），并复用现有门禁：
`audit3`（逐字节复现，验证 T3/T4 以外的行未受影响）、`audit4`（CSS 覆盖零缺失）、`audit5`（词头污染仍为 0）、`audit6`（对比本轮包，差异应只出现在 `ld-stress` / `ld-sense-n` 相关的类上）。


---

## T9【中等】`text-indent` 被继承进 `inline-block` 芯片 → 文字"跃出"自己的边框 ✅ 已修复并验证

> 触发来源：用户反馈「`rather` 这个单词 British English 样式有问题，字跃出了边界」。

**根因**：例句块用 `text-indent` 做悬挂缩进：

```css
[data-sc-class="ld-ex"] { padding-left:1.6em; text-indent:-1.6em; }
```

而 **`text-indent` 是继承属性**。芯片（`ld-geo` 等）是 `display:inline-block`，**inline-block 会建立新的块容器**，于是继承了 `-1.6em` 并作用到它自己的首行 —— 芯片内的文字被整体**左移约 19px**，而盒子的内在宽度又是按"首行左移"算出来的，于是**比文字还窄**。

真浏览器实测（真实包 CSS + 真实 SC 结构）：

| | 芯片边框盒 | 盒内文字 | 文字相对盒左内缩 | 文字是否溢出盒 |
|---|---|---|---|---|
| 修复前 | W=**97.6** | W=**110.5** | **-18.9px** | **YES +12.8px** |
| 修复后 | W=**122.5** | W=110.5 | **+6.0px** | **no** |

（修复后 122.5 = 文字 110.5 + 左右 padding 10 + 边框 2；+6.0 = padding 5 + 边框 1，均正确。）

**后果**：芯片的背景/边框包不住自己的文字，文字还会**压到前一句上**（`rather` 的例句最典型：`…difficult child` 后面直接叠了 `British English`）。这也解释了为何 `ld-excn`（中文例句）那条规则里早就写了 `text-indent:0` —— 有人为同类问题打过补丁，但只补了那一处。

**影响面**：包内落在例句/语料库例句内的芯片共 **598 处**（`ld-geo` 453、`ld-register` 109、`ld-gram` 36），占全部芯片的 0.20%。数量不大，但命中的都是常见词。

**修法**：给所有 `display:inline-block` 的规则显式加 `text-indent:0`（共享芯片底座 + `ld-field`/`ld-fieldxx` + `ld-signpost` + `ld-snum` + `ld-num`）。只动 `generate_css()`。

**教训**：`text-indent` / `line-height` / `letter-spacing` / `text-align` / `visibility` / `word-spacing` 都是**继承属性**，而 `display:inline-block` 会开新的块容器 —— 父级的负 `text-indent` 会落到它自己身上。凡给块级容器加悬挂缩进，都要对内部 inline-block 子元素重置 `text-indent`。

---

## T10【已修复并进包】`close` 等 38 个词条有两个 "Word family" / "词族" 面板

> 触发来源：用户反馈「`close` 这个词为什么有两个词族 word family」。

**结论：源里确实有两个 `div.wordfams`，内容不同；但原版只让第一个可见，第二个是隐藏块 —— 我们的渲染器把隐藏块也显示了，并给它补了一个 "Word family" 表头。**

### 事实（全部实测）

`close` 在源里是 **4 个同形词**：`close¹` /kləʊz/ verb、`close²` /kləʊs/ adj、`close³` /kləʊs/ adv、`close⁴` /kləʊz/ noun。整条记录有 **2 个 `div.wordfams`**，内容确实不同：

| | 词族内容 |
|---|---|
| 面板 A | noun *closeness, borough* · adjective *close* · verb *close* · adverb *close, closely* |
| 面板 B | noun *close, closure, closing* · adjective *closed, closing* · verb *close* |

它们在 DOM 里是 `div.dictionary` 的**前两个子元素**，排在所有 `dictentry` 之前（同一个 `entry_content`，不是分属不同同形词）。

### 原版只让第一个可见

源文件级统计：

| | 数量 |
|---|---|
| `div.wordfams` 总数 | **4,041** |
| 以 `LDOCE5pp_sensefold` 开头（**有** `asset_intro` 表头 + `foldsign` 折叠标记） | **4,003** |
| 直接以 `LDOCE_word_family` 开头（**无**表头、**无**折叠标记） | **38** ← 即这些"第二个面板" |

三条独立证据表明那 38 个不可见：

1. **没有显示机制**：内层 `LDOCE_word_family` 带**内联** `style="display:none;"`。`mdd_assets/LM5Switch.js` 里 `LDOCE_word_family` 只出现 2 次，唯一的显示路径是：

   ```js
   $('.wordfams > .LDOCE5pp_sensefold').off().on("click", function () {
       $(this).toggleClass('foldsign_fold');
       $(this).nextAll('.LDOCE_word_family').first().lm5pp_toggle();
   })
   ```

   绑定选择器要求 `.LDOCE5pp_sensefold` 是 `.wordfams` 的**直接子元素**，**只有面板 A 有**。面板 B 既无表头可点、也无折叠标记，内容永远停在 `display:none`。

2. **原版 CSS 里没有 `.LDOCE_word_family` 规则**（`mdd_assets/LM5style.css` 命中 0 条），因此没有任何 `!important` 能覆盖那条内联 `display:none`。

3. **原版 JS 明确写了要去重**：`LM5Switch.js:258` 注释 `// remove duplicate records of 'word family'`，按每个 `.wordfams` 内**第一个 `.w` 的 `title`** 去重并 `.remove()`。
   （严谨起见：这段去重位于 `multiwordsSetup()`，其前提 `$('.lm5ppbody > .entry_content:not(.topic)').length > 1` 对这 38 个**都不成立**，所以它不会被执行；这 38 个里已有 7 个首个 `.w` 标题与面板 A 相同。但无论如何，第 1、2 条已足以证明面板 B 显示不出来。）

### 为什么会出现两个

**源数据自身的冗余**（LDOCE5++ 转换遗留），不是我们造成的重复。原版靠 JS 隐藏/删除兜底。

### 现状与可选修法

`render_wordfams()` 对**每个** `div.wordfams` 都输出一个完整 `<details class="ld-panel-wf">`，并**无条件**加 `Word family / 词族` 表头。于是 38 个隐藏块变成了可见的第二个面板。

| 方案 | 效果 | 代价 |
|---|---|---|
| **A. 跳过无表头的 `wordfams`** | 与原版可见输出一致（38 个词条少一个面板） | **删掉** 38 条源内容 |
| B. 保留内容但不加表头 | 不再像"两个 Word family"，内容不丢 | 多出一段无标题词族列表，仍显突兀 |
| C. 保持现状 | 内容不丢 | 38 个词条看起来像有重复面板 |

**倾向 A**（精确对齐原版），但这是"删内容"的决定 —— 本项目原则是内容忠实优先，故当时**未擅自改动**，留待用户决策。

**当前状态：已按方案 A 实施（2026-09-11，另一会话提交 `5e343c4`）。**

> ⚠️ **决策来源待确认**：本文件原先记录的是"未擅自改动、等待用户决定"，实施方在原会话中标注为"用户拍板"，但审查方（2026-09-11 复核）无法从记录中确认用户是否明确表态过。若用户并未表态，则这是一次**单方面删内容**的决定 —— 建议向用户确认。行为本身与原版一致（那 38 块在原版不可见）。

**修法**：`render_wordfams()` 开头加守卫 —— 若该 `div.wordfams` **没有直接子** `span.LDOCE5pp_sensefold`，直接返回 `None`（跳过整块）。这正是上表"面板 B 显示不出来"的结构特征，一行判定，无启发式。

**验证**（`converter/wf_count_probe.py`、`converter/verify_wf.py`）：

| 检查 | 结果 |
|---|---|
| 源端用 bs4 枚举**所有** class 含 `wordfams` 的元素 | 27,148 个 = `wordfams newfamily` **23,107** + 精确 `wordfams` **4,041** |
| 其中无直接子 `sensefold` 的 | **38**（全部落在精确 `wordfams` 组，含 `Independent, the`） |
| 出厂包（09.11）里有 ≥2 个 `ld-panel-wf` 的词条 | **38**（与源端 38 严格对应） |
| 改后定向重建（37 个 T10 词 + 5 个对照词） | T10 词每个 **1** 个面板；`improve`/`about`/`back`/`second class`/`seeing` 仍各 1 个；`the` 本就 0 个 |
| 内嵌校验器（严格模式） | `[OK] Validation passed.` |

> 口径订正：本节正文的"4,041 个 `div.wordfams`"是**精确类名**口径；实际还有 23,107 个
> `class="wordfams newfamily"`（**全部带表头**，不受守卫影响）。两种口径下"无表头 = 38"一致，
> 且 23,107 个不受影响 —— 故守卫**无误伤**。

> 注：`--test-words` 按逗号切分，`Independent, the` 传不进去；该 key 由源端谓词复核覆盖。

**落地状态**：**已进包**。09.11 交付包（`LDOCE5pp_Yomitan_2026.09.11.zip`）里 `close` 只剩 1 个 `ld-panel-wf`，包级 diff 显示 `ld-panel-wf` 恰好 **-38**。（本节此前写着"尚未进包，需一次全量重建才会生效"，是重建前的残留陈述，已订正。）

> 包哈希在本文件写成后又变过一次：D20/D21 修复（见 `REVIEW.md`）重建了同一个文件名，当前 sha256 前 8 位为 `15aaa3b8`；重建前的版本存于 `_baseline/LDOCE5pp_Yomitan_2026.09.11.PRE_R1.zip`（`082fc555…`）。

