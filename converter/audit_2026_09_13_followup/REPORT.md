# f774b4e 修复后复审及扩展检查（2026-09-13）

## 结论与范围

- 本次提交：`f774b4e`，与上次审查的 `f120dbb` 对照；开始时工作区干净。
- 当前正式包：`yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip`，不是 09.12 的旧包。
- **R2 原编号和 R3 主题颜色修复已验证生效。R1 上次具体指出的 16 处已修复，但同类问题仍有残留。**
- 扩展检查另外确认：**渲染异常仍可发布缺词包；标准 mono 全量内容仍不能通过零 CJK 校验。** 这两项是本轮扩大覆盖后发现的既有问题，不应误解为本次提交新引入的回归。

本轮没有修改转换器、正式 ZIP 或既有审计报告。新增文件仅在本目录；失败发布测试中的“好包被覆盖”只发生在新建的隔离测试目录，正式包哈希未变。

## F1 · P1：渲染异常只计数并跳过，仍成功发布缺词包

**位置：** `converter/ldoce2yomitan.py:3320–3324`；发布路径 `:3472–3505`。

`build()` 捕获 `render_record()` 的所有异常后，只增加 `stats["render_errors"]`、打印警告并 `continue`。发布门禁只检查 `validate_package()` 返回的 errors，没有把已发生的渲染失败纳入失败条件。

而结构校验收到的是**已经成功写出的** `written_exprs`。如果被丢弃的记录没有被其他条目引用，少一条记录的包仍然可以满足行结构、序列连续、零悬挂链接等条件。

### 真实 CLI 复现（未 monkeypatch）

在本目录新建隔离输入和输出：

1. 输入 `audit-ok`、`audit-broken` 两条正常记录，成功生成含两条记录的好包，记下 SHA-256。
2. 只把第二条的正文替换为 450 层嵌套 `<span>`，使**实际渲染器**触发 `RecursionError`。
3. 使用相同输出目录再次运行真实 CLI，默认启用校验，没有使用 `--skip-validation`。

实际输出：

```text
[WARN] render error 'audit-broken': RecursionError('maximum recursion depth exceeded')
[*] Rendered entries: 1
[*] Render errors: 1
[OK] Validation passed.
[OK] Dictionary package: .../render/LDOCE5pp_Yomitan_2026.09.13.zip
```

**退出码仍为 0；ZIP 从 2 条变成 1 条；SHA-256 改变，测试目录内的好包被覆盖。**

这与已经修好的 A1 是不同入口：A1 的“校验器明确报错时禁止发布”本轮仍通过；这里的渲染错误在进入校验器之前就被吞掉，导致门禁根本没有看到错误。

**建议：** 可继续扫描以汇总异常，但默认严格构建在发布前必须把非零 `render_errors` 转为失败、返回非零并保留旧包。如果需要 best-effort 输出，应由显式选项启用，而非默认行为。补上“真实渲染器失败”的负向门禁，不能只注入 validator 错误。

**范围说明：** 当前正式双语包没有因这个测试而丢词；本轮标准源 mono 全量渲染也未发生渲染异常。此项是在异常输入/后续渲染器缺陷出现时的发布安全缺口。

证据：`build_probes.py` → `build_results.json` 中的 `render_failure`，以及隔离目录的 `render_bad.log`。

## F2 · P1：mono 仍有 4 条记录、9 个字符串节点泄露中文，正常构建失败

**位置：**
- `converter/ldoce2yomitan.py:1835–1840`：`_panel_title()` 只移除第一个 `span.cn_txt`。
- `converter/ldoce2yomitan.py:1731–1733`：例句中的裸文本直接进入输出。
- `converter/ldoce2yomitan.py:2207–2221`：标签分派依赖类名，未处理源中不同标记方式的中文标签。

这轮不再只检查之前 243 条标题候选，而是对标准源中的 **64,659 条内容记录全部执行当前 renderer 的 mono 路径**，并递归检查生成的 SC 字符串。用当前全量包建立查词索引，避免测试词列表导致的链接降级干扰。

结果：耗时 772.1 秒；**4 条记录、9 个字符串节点含 CJK；渲染异常 0**。

| 词条 | 残留内容 | 原因 |
|---|---|---|
| `approximate` | `【正式】`、`【非正式】`，共 3 个节点 | 源使用 `REGISTERLAB LDOCE_switch_lang switch_siblings`，不是 `cn_txt`；被普通标签分派直接保留。 |
| `for` | `NOT不用 ...`，1 个节点 | 中文嵌在英文例句的裸文本中，不在独立中文节点内。 |
| `hardly` | `NOT 不说 ...`，4 个节点 | 同上；例如 `He was so ill he could hardly speak (NOT 不说 he hardly could speak).` |
| `need` | `GRAMMAR : Verb patterns 动词句型`，1 个节点 | 同一标题含两个 `cn_txt`；只摘掉了第一个“语法”，第二个“动词句型”仍被拍平进英文标题。 |

### 不只是“显示里还有一点中文”

从标准源原样提取以上四条记录，交给真实 CLI 执行 `-m mono`，得到：

```text
[*] Rendered entries: 4
[*] Render errors: 0
[FAIL] Validation failed with 1 error(s):
   - term_bank_1.json: mono build contains CJK text
[FAIL] Nothing published ...
```

**CLI 退出码为 2，没有发布 ZIP。** 因为完整标准源同样包含这四条记录，标准全量 mono 的输出内容目前仍无法通过默认零 CJK 校验。旧 A5 候选集通过不等于 mono 全量已可交付。

**建议：** 标题提取移除所有中文子节点；识别源中中文侧的 `switch_siblings` 标签；对夹在英语提示中的中文注解做保留英文含义的过滤。不要简单删除整条例句，也不要用 `--skip-validation` 掩盖问题。将以上四条纳入快速回归，并保留全量 mono 内容扫描。

**覆盖说明：** 本轮完成的是全量 mono 渲染和四条原始记录的真实 CLI 构建验证，没有压缩/发布正式的全量 mono ZIP。

证据：`mono_probe.py` → `mono_render_results.json`；`build_probes.py` → `build_results.json` 的 `mono` 与 `source_excerpts`。

## F3 · P2：R1 只处理“元素 → 文本”，反方向的缩写断词仍存在

**位置：** `converter/ldoce2yomitan.py:547–553`。

新增保护只在 `left` 是元素、`right` 是裸字符串时触发。这确实恢复了 `terrorist` + `s`、`download` + `ed`。但源中也有反方向的词内接缝，例如：

```html
You’<a class="defRef" href="entry://re#re__2__a" title="re">re</a>
I didn’<a class="defRef" href="entry://t" title="t">t</a>
```

在这些位置，左边是文本，右边是链接。保护条件不成立，弯撇号又在 `_LEFT_END` 中，随后仍返回“需要空格”。

当前 09.13 包中实际可见：

| 词条 | 源及未引入分隔器时的文本 | 当前包 |
|---|---|---|
| `apprentice` | `You’re fired!` | `You’ re fired!` |
| `auxiliary verb` | `I didn’t go` | `I didn’ t go` |
| `Berra, Yogi` | `It ain’t over` | `It ain’ t over` |
| `but` | `I’m sorry` | `I’ m sorry` |

**量化：** 对 09.11 原包中的紧接节点和 09.13 当前包的新增空格节点逐行配对，保守确认 **34 个不同词条、36 处缩写断词**。计数只覆盖能以指定简单缩写接缝配对的情况，不代表所有可能的断词都已穷尽。

这批问题在 09.12 时已经存在，当前修复没有触及，所以只检查“本次删除/新增了哪些空格”会漏掉它们。全量去空白文本比较同样无法发现单词内部空格。

**建议：** 对正文中“元素→文本、文本→元素、元素→元素”三类词内接缝统一保持源连接；只在真正独立的标签/元数据边界增加分隔。加入缩写精确文本断言，而不是仅验证上次列出的后缀案例。

证据：`package_probe.py` → `package_results.json` 的 `contraction_examples`；上表前三条和 `but` 另有直接源 HTML 核对。

## 已验证修好的部分与其他通过项

| 检查 | 本轮结果 |
|---|---|
| R1 原 16 处案例 | 全部恢复正确文本，旧错误片段不再出现；不包括 F3 新发现的残留。 |
| R2 源编号 | 当前包 75,903 个源编号节点不再有 `fontSize:0`；Chrome 确认 `act` 在无 CSS 时仍显示 7、8、9、10，原生计数不冲突。 |
| R3 主题颜色/字重 | 原始 Yomitan SC 生成器 + Chrome 双模式通过。中文暗色对比度恢复约 6.48:1；词性亮色约 6.97:1；有 CSS 时词例字重回到 600。 |
| 行内样式与 CSS | 22 条兜底声明的同值/`!important` 一致性检查通过。 |
| A1 / A6 原门禁 | validator 明确报错时返回非零、旧包不变；重复序号、缺 0、跳号负例通过。F1 是它们未覆盖的另一条失败路径。 |
| A2–A5 旧候选集 | `regress_content.py` 使用 09.13 包运行，退出码 0；A3 旧断言已更新。F2 是超出旧候选集的全量发现。 |
| 非 glossary 字段 | 245,933 行与 09.12 包逐行对照，其余 7 个字段完全相同。 |
| 内容保守检查 | 64,659 条内容记录剥除空白后文本与 09.12 包逐字符相同；不能将此当作“没有断词”的证明。 |
| 频率元数据 | `term_meta_bank` 的频率代码与同表达式的 `definitionTags` 频率代码并集一致，缺失/多余均为 0。 |
| 独立结构扫描 | 245,933 行；序号唯一且连续；SC key/tag/style 违规 0；非法 href 0；悬挂查询/重定向目标 0；CSS 缺类 0；别名/内容行互遮蔽 0。 |
| 源码/包抽样 | 当前源码成功重渲染并逐字节比较 45 条内容样本，0 不一致；旧 `audit3` 跳过的别名未算作复现通过。 |

`package_results.json` 中的 426 个未加 `listStyleType:none` 的列表均属于源原生 `ld-list`，不是生成的义项/例句列表；这里没有将保留源列表标记误报成 R2。

## 复现与边界

本目录探针固定审查 09.13 包，并明确使用 09.12/09.11 做相应比较；不会自动把新日期包混入本次结论。

```powershell
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13_followup/fix_verification.py
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13_followup/package_probe.py
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13_followup/mono_probe.py
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13_followup/build_probes.py
& .\venv\Scripts\python.exe -X utf8 -u converter/regress_render_contract.py 'yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip'
```

- `mono_probe.py` 约需 13 分钟；发现中文/异常时退出码为 1。
- `build_probes.py` 新建独立 `builds/<时间戳>/`，记录真实 CLI 的退出码和产物；诊断脚本本身完成不等于被测构建通过。
- 浏览器契约探针只打开本地页面，沙箱外执行可能需要批准。
- 没有正式全量双语重建、全量 mono ZIP 压缩、真实扩展导入/交互验收，也没有跑完整官方 JSON Schema。没有把独立结构检查等同于这些未执行的检查。

## 固定基线与编码

审计前后相同的 SHA-256：

- 转换器：`ad83a5151e5575d44c6d00cb60712334f9ab938e8cccb40c33178142fb41876c`
- 正式 09.13 ZIP：`5edae5d9131ab8261d80ba602bfc733642e3840c49bc37fe8d54c081fb53f8fc`

报告和证据均显式 UTF-8 原子写入，并校验回读字节一致。未修改生产代码来让回归变绿。
