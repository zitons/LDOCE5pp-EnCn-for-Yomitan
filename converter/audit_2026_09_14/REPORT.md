# 2026-09-14：从头完整复审

> **后续状态：N1–N3 已修复并完成完整验收，见 [FIXES.md](FIXES.md)。** 以下保留修复前基线、位置与证据。

## 结论

**尚不能判定当前版本“没有问题”。本轮确认 3 项需要修复的缺陷：1 项发布安全缺口、2 项实际显示/正文问题。**

已读取会话 `01a098a9-ab1f-79b2-83d1-078905c4956c` 的审查、修复和验证记录，但没有把上轮结论当成本轮证据。重新阅读转换器全部主要路径，复跑旧门禁，并加入独立源 DOM 核对、完整重建、全量官方 Schema 和真实浏览器导入检查。

本轮**没有修改转换器、正式 ZIP 或既有项目文档，没有提交、推送或发布到 GitHub**。新增文件仅为本目录的审查脚本、失败用例和本报告；运行产物位于被忽略的 `results/`。

## 基线与范围

- Git 基线：`153d00a`；核心转换器仍是已修复 D39–D41 的版本。
- 转换器 SHA-256：`5343520b762db09bb43d8191d6e789f95db94952338c4985c8dae886ff8fcc6f`。
- 输入：`extract/LDOCE5++ V 2-15.mdx.txt`，920,087,116 字节，285,017 条源记录。
- 当前正式双语包：`yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip`，63,737,603 字节，SHA-256 `8544ed4c6677f7c8e1cdc17a3222dc69b40be3d3b0857feefecb2ccfe73d77e1`。
- 当前正式 mono 包：`yomitan_full/LDOCE5pp_Yomitan_2026.09.13_EN.zip`，54,116,529 字节，SHA-256 `73662eabaa3985eb9843026ca55a440838c12d286d6247fa7565cd93dcaa840e`。
- 两个正式包均与 `yomitan_fixed/verified/` 对应包相同。**没有沿用旧的“正式目录尚未同步”假设。**
- Yomitan 契约取自本地 `yomitan-ext/`，版本 **26.8.24.0**；不声称这是联网核对过的最新版本。
- 动态审查覆盖输入记录、词条及别名元数据、正文节点接缝、双语/mono、列表/链接、发布门禁、CSS、导入器和 IndexedDB。发布助手仅静态阅读，未调用凭据或远程 API。

## N1 · P1：渲染成空内容仍会成功发布缺词包

**位置：** [`build()` 的空记录分支](../ldoce2yomitan.py#L3381-L3383)，与[仅拦截异常计数的门禁](../ldoce2yomitan.py#L3410-L3414)。

`render_record()` 没有抛异常、但返回空内容时，程序只增加 `empty_records` 并继续。随后的拒绝发布条件只看 `render_errors`。校验器检查“已经写出的行”是否合法，不检查每条被识别为 entry 的源记录是否都产生了内容行，因此遗漏不会触发失败。

真实 CLI 隔离复现：

1. 在新测试目录先构建有 2 条内容行的合格包。
2. 保留第一条，把第二条正文改成 `<div class="entry_content"></div>`；该记录仍被 Pass A 识别为 entry。
3. 正常构建返回 **0**，打印 `Empty after render: 1`、`Validation passed`，并用 **1 条内容行**的新包覆盖原包。
4. 把两条记录设成**相同 key 的两个义项记录**，结果仍一样。仅比较词头集合也无法发现这一种遗漏。

`publication_probe.py` 使用真实 CLI，未注入假 validator 或假 renderer。`regress_new_findings.py` 进一步覆盖 `validate=True/False` 两个路径；当前均未拒绝发布、旧包均未保留。

**影响边界：** 本轮完整源构建的空记录数为 0，现有正式包内容行数与源记录数匹配。此项是损坏/异常源内容或后续渲染器遗漏出现时的发布安全缺口，**不是宣称当前正式包已经因它缺词**。

**建议：** 将非零 `empty_records` 纳入拒绝发布条件，按源记录而非唯一 key 计数；在别名及辅助数据产出前统一拒绝、清理临时包、保留旧 ZIP。若确需允许丢弃空记录，应单独显式启用并标记非完整构建，而非默认成功。

证据：`results/publication/results.json`、`results/publication-argument-check/results.json`、`results/new_findings_regressions.log`。

## N2 · P2：分隔器仍会拆开链接后缀和 n't 缩写

**位置：** [`_seam_needs_space()`](../ldoce2yomitan.py#L545-L564)，尤其是 558–562 行。

上轮保护了“元素 → 裸文本”的部分接缝以及“左侧以撇号结尾”的缩写。仍未保护：

- **元素 → 元素**：`<a>relieve</a><a>d</a>` 仍按两个词插空格。
- **撇号前的切分**：`did<span>n’t</span>` 的左侧并不以撇号结尾，仍会插空格。

从源 HTML 出发扫描全部 64,659 条内容记录，而不是仅与某个旧转换包比较，确认以下 **5 个词条**在当前双语和 mono 包中都有错误：

| 词条 | 源文应有的正文 | 当前成品 |
|---|---|---|
| `come` | `relieved` | `relieve d` |
| `come as a surprise/relief/blow etc (to somebody)` | `relieved` | `relieve d` |
| `in vitro fertilization` | `fertilized` | `fertilize d` |
| `none` | `didn’t get any` | `did n’t get any` |
| `not` | `didn’t know anybody` | `did n’t know anybody` |

例如源中直接存在：

```html
<span class="NonDV"><a class="defRef" href="entry://relieve">relieve</a></span><a class="defRef" href="entry://d">d</a>
I did<span class="COLLOINEXA">n’t</span> know ...
```

这些空格是实际正文字符，因此有无 CSS、是否展开面板都不会自动修好。`none` / `not` 中受影响的还是教读者正确用法的例句。

**数量口径：** 源扫描得到 15 个候选接缝，人工核对确认 5 个，另 10 个是正确的词间分隔，例如 `over exposure`、`to go`、`a new`、`games console`。没有把候选数当缺陷数；5 是确认数，不是对所有可能断词形式的上限保证。

**建议：** 区分词内边界与独立词/标签边界，覆盖上述两类漏网方向；同时保留正常词组、词族和芯片分隔。不能靠禁用全部插空格来修复。本轮新增测试同时保留 `You’re`、`downloaded`、`model kits` 和 `[countable] noun` 等正反例。

证据：`results/source_inventory.json`、`results/negative_contractions.json`、`results/findings.json`；最小复现见 `regress_new_findings.py`。

## N3 · P2：带样式的 Anki 暗色导出会把正文锁成深色

**位置：** [`generate_css()` 根节点规则](../ldoce2yomitan.py#L2437)：

```css
color: var(--text-color, #202124);
```

**触发条件：** 卡片携带词典样式，暗色宿主没有定义 Yomitan 专用的 `--text-color` 变量。这与无 CSS 回退是不同路径。

Yomitan 扩展的明暗主题会提供此变量，所以旧主题回归通过。Anki 导出则使用 `anki-note-data-creator.js` 中的 `addScopeToCssLegacy()` 生成作用域样式，默认字段模板可嵌入这些样式；普通卡片并不因此自动获得 Yomitan 的主题变量。

本轮用**实际导出作用域函数、实际 SC 生成器及 Chrome**测量相同 `act` 正文：

| 环境 | 正文计算颜色 | 背景 | 对比度 |
|---|---|---|---:|
| Yomitan 亮色，提供主题变量 | `rgb(0,0,0)` | `#ffffff` | 21.000 |
| Yomitan 暗色，提供主题变量 | `rgb(212,212,212)` | `#1e1e1e` | 11.247 |
| Anki 作用域样式，亮色且无变量 | `rgb(32,33,36)` | `#ffffff` | 16.099 |
| **Anki 作用域样式，暗色且无变量** | **`rgb(32,33,36)`** | **`#1e1e1e`** | **1.036** |
| 无 CSS，暗色且无变量 | `rgb(212,212,212)` | `#1e1e1e` | 11.247 |

双语和 mono 均复现。也就是说，宿主本已提供浅色文字，词典根节点却用硬编码 fallback 覆盖它，导致正文几乎融入背景。**不是原来的 R3 内联绿/蓝压过主题；也不影响本轮已通过的无 CSS 模式。**

**建议：** 变量缺失时继承宿主文字色，而不是固定 `#202124`；增加“有词典 CSS、无 Yomitan 变量、暗色宿主”的浏览器回归。

证据：`results/browser-import/results.json` 中两种模式的 `render.anki-dark`；测试逻辑见 `browser_import_page.js`。这里没有运行 Anki 客户端，不将浏览器中的导出契约复现冒充客户端端到端验收。

## 本轮通过的验证

| 检查 | 本轮结果 |
|---|---|
| 旧快速回归 | `regress_review_followup.py` **14/14 通过**；原异常发布门禁、已知中文泄漏和既有缩写用例没有回退。 |
| 旧非浏览器回归套件 | `regression_suite.py` **11 个脚本调用全部退出 0**，包括列表、词头分隔、CSS 一致性、CSS 回退、语义标记、历史内容与词头污染。 |
| 独立源 DOM 元数据核对 | **64,659 条内容记录全部核对，POS/规则/频率标签零差异**；源记录与包内内容记录一一对应，没有遗漏同 key 的第二条记录。 |
| 双语完整重建 | **退出 0**，64,659 内容行 + 181,274 别名行 = **245,933 行**；空记录/渲染错误/悬挂链接 0。总耗时 932.3 秒。 |
| mono 完整重建 | **退出 0**，相同行数；空记录/渲染错误/悬挂链接 0、零 CJK。总耗时 913.0 秒。 |
| 重建与正式包比对 | 两种模式的 term bank、term_meta、tag bank、CSS **全部逐字节相同**；`index.json` 仅 revision 不同。不是只抽查 45 个样本。 |
| 官方 Schema 全量 | 直接调用本地 Yomitan 实际使用的预编译 AJV 校验器；**两包全部 491,866 条 term 行**、index、tag、term_meta 均通过；另有非法 style / 错误 sequence 类型负例确认校验器确实生效。不是 20% 抽样。 |
| 独立包不变量 | 两种模式各 **1,949,979 个查询链接、209,756 个别名目标**均有效；别名规则等于目标内容规则并集；5,971 条频率元数据与正文标签覆盖一致；零嵌套锚点、孤儿 li、非法列表子节点、未声明标签和 CSS 类缺失。 |
| 原浏览器契约 | 实际 Chrome 亮/暗 Yomitan 主题、无 CSS 源编号、标记和字重回归通过，`act` 仍显示源编号 `7,8,9,10`。 |
| 实际导入器 + IndexedDB | 两包分别导入两个全新 localhost origin 的真实 Chrome 数据库：每包实际存入 **245,933 条词条、5,971 条频率、33 条标签**；导入错误与运行时异常均 0。导入耗时约 106.8 / 104.3 秒。 |
| 导入后查询与 DOM 交互 | 使用实际 English transforms/条件匹配及实际数据库，`bailout's→bail out`、`amen's→amen`、`children`、`ran`、`improving→improve` 通过；真实链接点击处理保留 query/wildcards 参数且目标存在；summary 点击能展开 details。 |

两种重建同时执行，耗时不是空载性能基准。`browser_import_page.js` 的 `completed=true` 表示导入/查询作业完成，**不代表记录下来的 Anki 对比度合格**。

### 新增的失败回归

`regress_new_findings.py` 不依赖完整词典，使用最小源 HTML 与新建隔离发布目录：

- 5 个测试方法，当前 **10 个子用例断言失败**，均对应 N1/N2；已有分隔正反例的控制测试通过。
- 这些失败是预期的审查结果，不是测试工具崩溃。
- N3 由上述真实浏览器测量覆盖；修复后的验收必须单独断言无主题变量的暗色正文对比度，不能仅沿用旧的有变量主题测试。

## 复现命令

工作目录为项目根目录。`venv` 和 `yomitan-ext` 已在本机存在；未为本轮下载新的依赖。

```powershell
# 新缺陷：当前应退出 1，修复后才应通过。
& .\venv\Scripts\python.exe -X utf8 converter/audit_2026_09_14/regress_new_findings.py

# 真 CLI 发布探针。必须用新的输出目录，防止覆盖上一轮证据。
& .\venv\Scripts\python.exe -X utf8 converter/audit_2026_09_14/publication_probe.py --output converter/audit_2026_09_14/results/publication-recheck

# 全量源 DOM 核对及接缝候选扫描。
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_14/source_inventory.py

# 全量官方 Schema，包路径显式指定。
node converter/audit_2026_09_14/official_schema.mjs yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip yomitan_full/LDOCE5pp_Yomitan_2026.09.13_EN.zip

# 真实 Chrome 导入 + IndexedDB + 导出样式测量；输出目录必须不存在。
# 可在输出目录后再传双语和 mono ZIP 的显式路径；省略则用本报告的基线包。
node converter/audit_2026_09_14/browser_import.mjs converter/audit_2026_09_14/results/browser-import-recheck

# 本轮已完成构建的完整包比对；拒绝使用与当前转换器哈希不符的构建清单。
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_14/package_audit.py
```

重新构建时使用新目录，不覆盖正式包或本轮已验收产物：

```powershell
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13_followup/build_fixed.py bilingual --output converter/audit_2026_09_14/results/rebuild-recheck/bilingual
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_13_followup/build_fixed.py mono --output converter/audit_2026_09_14/results/rebuild-recheck/mono
& .\venv\Scripts\python.exe -X utf8 -u converter/audit_2026_09_14/package_audit.py --build-root converter/audit_2026_09_14/results/rebuild-recheck
```

最后一条是“与本轮正式基线应相同”的检查。以后真的修改转换器后，预期变化需要另行审核，不能把它误当成应无条件通过的修后验收。

## 非阻断事项与验证边界

1. **`--limit` 输出风险：** 隔离 CLI 也证实同日 `--limit 1` 会以同一正式文件名覆盖完整包，2 行变 1 行、退出 0。限制行数本身是显式请求，故未将“生成部分数据”计作上述 3 项缺陷；但 smoke 构建必须使用独立 `--output`，建议像 `--test-words` 一样标记调试成品。
2. **文档基线须以哈希为准：** `HANDOVER.md` 开头仍有“正式包未同步”的旧描述，而后续 `FIXES.md` 的独立复核已说明同步完成；README 对无 CSS 编号的部分描述也仍写成 UA 自编。当前实现是源编号芯片、关闭 UA 编号。本轮不改旧文档，修复时应同步订正。
3. **完整扩展/Anki UI 尚未验收：** 真实 Chrome 中跑的是实际导入器、数据库、SC 生成器和链接处理器，不是完整扩展设置页/搜索弹窗。查询探针用实际 English transforms 和数据库，不冒充完整 Translator 的全部配置/排序行为；链接处理的 Display 接收器由探针提供。未测试 AnkiConnect、制卡保存、Anki 客户端或移动端。
4. 两种包共用词典 title，是替代版本；导入测试使用不同 origin 的全新数据库，不声称两包可在同一个数据库内同时安装。
5. GitHub Release 状态、既有发布说明文件缺失及历史凭据吊销等外部待办未在本轮解决，也未执行任何远程发布操作。
6. 源扫描中针对多根 entry_content、多个并列中文-only DEF、嵌套 portrait 标签、混合 assetlink 组和表格跨格的怀疑没有找到本库实例，未把纯假设列为缺陷。接缝扫描也不是自然语言正确性的完备证明。
7. 探针本身做过两项订正：源记录分类排除资源记录；Node 的 ZIP 输入转为普通 `Uint8Array`，避免 Buffer 的 slice 语义导致假报分卷 ZIP。上述结论和计数均来自订正后的成功运行，未把初版探针错误算作产品问题。

**建议处理顺序：先补 N1 发布门禁，再修 N2 词内接缝、N3 暗色继承；保留本轮负例作为长期门禁。旧测试全部通过不能替代这些此前未覆盖的场景。**