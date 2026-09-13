# LDOCE5++ → Yomitan：修改后复审（2026-09-13）

## 范围与结论

- 对照会话：`01a0937e-757d-7cc0-baec-751f687aaf00`。上次审查基线为 `2985637`。
- 本次基线：`f120dbb`；审查三次提交 `fd566aa`、`136b65d`、`f120dbb`，开始时工作区干净。
- 当前成品：`yomitan_full/LDOCE5pp_Yomitan_2026.09.12.zip`，不是旧的 09.11 包。
- 直接审查了渲染出口、分隔算法、列表分组、内联样式、POS 提取、别名规则合并，以及构建/校验/发布流程；不是仅检查 ZIP。

**上轮 A1–A6 在对应复测范围内均未再复现；但本次新增的可移植显示逻辑引入了 3 项 P2 回归。当前版本不宜判定为全部验收通过。**

没有修改转换器或正式 ZIP。新增的是本目录内的报告与审计探针；大体积证据、生成页面和浏览器临时文件忽略入库。

## R1 · P2：通用分隔器在单词内部插入空格

**位置：** `converter/ldoce2yomitan.py:494–497`、`:672–677`。

`_seam_needs_space()` 把任意两个行内节点的字母接缝视为“需要分隔的独立内容”；`separate_inline_runs()` 又将它递归应用到所有正文。链接或强调节点的结束位置不一定是单词边界。

当前包中的真实例子：

| 词条 | 源文本 / 修前包 | 当前包 |
|---|---|---|
| `7/7` | `terrorists carrying` | `terrorist s carrying` |
| `7/7` | `rucksacks` | `rucksack s` |
| `criminal` | `bank robbers in US history.` | `bank robber s in US history.` |
| `MP4 player`、`vodcast` | `downloaded from the` | `download ed from the` |

已直接核对源 HTML：`7/7` 是 `<a ...>terrorist</a></span>s carrying`；`criminal` 是 `<span class="COLLOINEXA">bank robber</span>s in US history.`。这里没有漏写空格，`s` 原本就是同一个词的后缀。

**量化：** 逐行配对新旧包的 64,659 条内容记录，确认 **15 个不同词条、16 处**从“链接/强调节点紧接后缀”变成“中间新增空格”。这是限制在指定节点及常见后缀集合的保守计数，不是所有可能断词的上限。

**影响：** 英文释义/例句被改写成错误拼写；空格已经进入 SC 正文，因此有 CSS 和无 CSS 两种环境都受影响。删除全部空白后再比较文本的守恒审计无法发现这类回归。

**建议：** 将强制分隔限制在已确认独立的标签/元数据边界；正文中的链接、强调、内嵌格式必须保留源接缝。补充 `7/7`、`criminal`、`MP4 player` 的精确文本回归，不要仅做去空白比较。

证据：`suffix_probe.py` → `suffix_results.json`。

## R2 · P2：隐藏源编号后，原生列表重新计数，改变义项编号

**位置：** `converter/ldoce2yomitan.py:607`、`:623–628`。

`hide_native_numbering_conflict()` 将原始义项编号置为 `fontSize: 0`；`group_into_list()` 创建的每个 `<ol>` 都采用默认计数。两者结合后：

1. 义项中间插入面板等非成员节点，会拆成新的列表并从 1 开始。
2. 没有源编号的交叉引用也会占一个列表项，从而推动后面编号偏移。

**真实例子：** `act` 的一组短语动词源编号是 **7、8、9、10**，无 CSS 时实际列表显示 **1、2、3、4**。`access` 的无编号 `→ direct access` 插在第 2、3 义项之间，后续源 3、4、5 因此变成原生 4、5、6。

**量化：** 全量扫描确认 **531 个不同词条、572 个列表、2,436 个隐藏的数字编号**与浏览器默认计数不一致。计数只涵盖隐藏的数字标签，不包含字母型子义项。

**真实浏览器验证：** Yomitan 原始 SC 生成器生成 `act` 的 DOM，再用 Chrome 152 测量：

| 环境 | 原生列表样式 | 源编号字体/宽度 | 用户可见编号 |
|---|---|---|---|
| 有词典 CSS | `none` | `16px` / 约 `21.59px` | 7、8、9、10 |
| 无词典 CSS | `decimal`，`ol.start = 1` | `0px` / `0px` | 1、2、3、4 |

**影响：** 无 CSS 导出时，义项标识不再与源词典及按义项号表达的引用一致。列表父子结构合法，不能证明编号语义正确。

**建议：** 保留源编号语义，不要把“重建列表位置”当作源编号。当前 SC Schema 不接受任意 HTML `start`/`value` 属性，不能直接加这两个属性了事；可在合法 SC 样式范围内保留源标签并抑制冲突的原生标记，或采用等价的编号保真方案。加入列表被面板打断、夹有无编号引用的用例。

证据：`package_probe.py` → `package_results.json`；`browser_probe.mjs` → `browser_results.json`。

## R3 · P2：无 CSS 兜底的固定颜色覆盖了正常主题颜色

**位置：** `converter/ldoce2yomitan.py:539–551`、`:573–580`。

`add_inline_semantics()` 为中文释义、译文、词性等节点写入 `green` / `DodgerBlue`。这些内联颜色在**有 CSS 时也存在**，优先级高于词典里正常的 `color: var(--ld-zh)` / `var(--ld-pos)`；当前样式只用 `!important` 恢复了编号，没有为主题颜色处理同样的层叠问题。

**实际测量，不是仅根据 CSS 字符串推断：** 将当前包中的 `act` 经真实 SC 生成器生成 DOM，用 Chrome 152、词典作用域内的 CSS，以及宿主亮/暗色变量测量实际文字节点：

- 暗色背景 `#1e1e1e`：中文释义/译文被固定为 `rgb(0,128,0)`，对比度 **3.245:1**。
- 控制组保持同一份 CSS、同一份内容，只去掉新增固定内联颜色：同一段文字恢复主题色，对比度 **6.482:1**。
- 亮色背景下，词性/语法被固定为 `DodgerBlue`，对比度 **3.236:1**。

这些是常规字号文本，低于常用的 4.5:1 对比度基准。全包有 119,283 个 `ld-defcn` 和 118,604 个 `ld-excn` 节点被写入 `green`；这不是个别词条的样式偶发问题。

**建议：** 兜底颜色必须在加载词典 CSS 后让位于主题配色，例如明确处理相应属性的 CSS 优先级，或使用能在两种环境正确回退的变量机制。补充“固定内联兜底 + 有 CSS + 亮/暗主题”的计算样式回归，不能只检查 `@supports` 结构。

证据：`browser_probe.mjs` → `browser_results.json`。这是真浏览器局部验证，不是已完成真实扩展导入验收。

## 上轮 A1–A6 的复测

| 项目 | 本轮实际结果 |
|---|---|
| A1 校验失败仍发布 | 隔离构建注入校验失败后抛出 `BuildValidationError`；CLI 返回 2；原好包哈希不变；`.part` 清理通过。 |
| A2 别名 rules 覆盖 | 当前 181,274 条别名的规则与其全部目标内容行的规则并集一致，0 条缺失。 |
| A3 POS 嵌套/上限 | 使用独立 lxml DOM 路径，逐源记录/出现次数对照当前包 **64,659 条内容记录**，POS、规则、频率标签集合 0 差异。没有用同 key 并集掩盖某一条记录的错误。 |
| A4 变形音标 | 旧候选集回归：源/输出词头配对失败 0，检查到的源 PRON 缺失 0；609 个候选词条已带 `ld-infl-pron`。 |
| A5 mono 中文标题 | 原中文标题候选集重渲染，CJK 泄漏 0。仅代表该候选集，不代表已跑 mono 全量构建。 |
| A6 sequence | 重复、缺 0、跳号负例均被拒绝；合法序列通过；成品序列为唯一且连续的 0…245932。 |

### 旧 A3 断言需要维护，但不是产品仍缺 POS

`converter/audit_2026_09_12/regress_content.py:90–95` 对历史 `source_findings.json` 中的旧 reference 做精确比较，本轮因此返回退出码 1、报告 12 个失败。新的源码已取消旧 reference 同样受限的标签/规则上限，例如：

- `after` 新增正确的 `prefix`；
- `down` 新增正确的 `noun` / `prefix` 和 `n` 规则；
- `last` 新增正确的 `pron` / `verb` 和 `v` 规则。

独立源 DOM 核对确认这 12 项全部是新输出正确、旧预期过时。应更新回归预期/独立参考，不应为了旧断言变绿而恢复截断。详见 `source_reference_results.json`。

## 其他已执行检查与边界

- 独立结构扫描：245,933 行；无悬挂查询/重定向目标、SC key 违规或缺失 CSS 类；包内 CSS 与当前 `generate_css()` 相同。
- 列表合法性：836,768 个 `<li>`、99,131 个 `<ol>`、212,149 个 `<ul>`；孤儿 `<li>` 和列表非法子节点均为 0。**这项通过没有覆盖 R2 的编号语义。**
- `audit3_reproduce.py` 实际成功比较 45 条内容重渲染样本，0 不一致；该脚本跳过的别名没有算作复现通过。
- 20 个词头通过真实 SC 生成器的分隔回归；方案 A 静态 CSS 回退检查、方案 B 标记全量检查通过。**这些检查没有覆盖 R1 的正文断词和 R3 的实际层叠颜色。**
- 官方 Yomitan Schema：本轮确认首 3 个 bank、共 **30,000 行**校验无错误。完整 Schema 递归校验耗时较长，已明确停止；未宣称 245,933 行官方 Schema 全量通过。之后另行完成了全量结构/编号扫描。记录见 `schema_partial_results.json`。
- 未进行正式全量重建、mono 全量重建、真实扩展导入/交互验收。

## 复现

从仓库根目录运行，读取本地源数据/现有包，不覆盖正式包：

```powershell
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13/package_probe.py
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13/source_reference.py
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13/suffix_probe.py
node converter/audit_2026_09_13/browser_probe.mjs
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_12/regress_gates.py
```

`browser_probe.mjs` 使用本地 `scgen_test` 的 jsdom / Yomitan 生成器与 Chrome；为每次测量创建独立 headless profile，仅打开本地页面。受限环境可能需要批准浏览器在沙箱外运行。

可选的耗时 Schema 检查：`package_probe.py --schema --schema-banks 3`；去掉 `--schema-banks 3` 才是官方 Schema 全量检查。`seam_candidates.py` 只是早期候选扫描器，它输出的候选数不能直接当作缺陷数。

## 审计前后不变的 SHA-256

- 转换器：`4ef239c1cced9722a25169589e6bc56961e5029aef9a0f2cdb1c74e1e68943fa`
- 正式 ZIP：`bc0674113e9a991da633ab8ac844ac8c44e31ae92a34e572672f5e0ae2bef71f`

报告使用显式 UTF-8 写入，并校验回读字节一致及实际中文字符数量；未复用此前发生 ASCII 替换损坏的写入方式。
