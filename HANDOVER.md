# LDOCE5++ → Yomitan 转换工程交接文档

> 接手人先读第 1、4、5 节。第 5 节全是真金白银踩出来的坑，跳过必返工。
> 生成时间：2026-09-10 · 前手：海鸥（DeepSeek Harness 会话）

---

## 0. 修订记录（2026-09-10 第二轮审查后）

本文档以下章节描述的是**初版构建（v1.0.0，915.7 s）**。此后做了一轮独立审查（见 `REVIEW.md`）
与一轮修复 + 性能优化，`ldoce2yomitan.py` 已升到 **v1.1.0**，交付物已重跑。差异如下：

| 项 | 初版 | 现在（v1.1.0） |
|---|---|---|
| 全量构建耗时 | 915.7 s | **686 s（11 分 26 秒）** |
| 解析器 | `html.parser` | **`lxml`**（需额外依赖，见 §3） |
| 词头被标签污染 | 16,751 条（25.9%） | **0** |
| 纯中文释义未走 `ld-defcn` | 119,249 处 | **0**（`ld-defcn` 34 → 119,283） |
| `HYP` 重音符被写成中点 | 39,354 个（27%） | **0** |
| 查询链接 live | 1,945,431 | 1,946,990（词头里的同音词/变体链恢复为活链） |
| 行数 / 词条 / 别名 | 245,933 / 64,659 / 181,274 | **完全不变** |
| zip 体积 | 59,919,504 B | 60,071,408 B |

**第三轮（排版/CSS 层，见 `TYPOGRAPHY.md`）**：主题机制从"跟随操作系统"改为"跟随 Yomitan 的
`:root[data-theme=dark]`"（原方案在 4 种主题组合里有 2 种文字与背景同色、对比度仅 1.02:1 与 1.39:1）；
21 种颜色抽成 `--ld-*` 变量并补齐暗色；新增 `ld-stress`（重音符与音节点分家）与 `ld-sense-n`
（只在义项确有编号时才留悬挂缩进，49% 的义项没有编号）；修正副义项编号越界；6 类芯片统一底座与间距。
CSS 118 → 120 类，**无类被删除**。全量构建 665 s，行数/词条/别名仍完全不变。

**第五轮（D7 + D8）**：修好频率扫描正则（改为属性顺序不敏感；FREQ 命中 **0 → 32,195**），使 S1–S3/W1–W3 真正进入 `definitionTags`（此前 tag_bank 里 6 个 frequency 标签是死声明），并新增 `term_meta_bank_*.json` 让 Yomitan **能按频率排序**；把裸的 `cls & DROP_CLASSES` 换成 `is_dropped()`，恢复被整块丢弃的 1,548 条 `→ N See picture of 见图 X` 交叉引用。**未给 ACTIV 义项标签加中文**——源里查无对照（见 REVIEW.md D9）。

**第四轮（词头顺序 + `.mdd` 普查）**：拿到 `.mdd` 后取出原版 `LM5style.css`，终结了 T8 的争议——
原版词头区域**没有任何 `order:`/绝对定位**，视觉顺序就是 DOM 顺序。`render_head()` 由"写死
`hwd → gram → pron → pos → chips → infl`"改为**单次遍历、按源 DOM 顺序发出**，例如
`18-wheeler` 从 `18-wheel·er [countable] /…/ noun` 变为正确的 `18-wheel·er /…/ noun [countable]`。
顺带修好：多词性词条（如 `the`）原来只保留最后一个词性标签，现在逐条发出。
**配色未采用原版**（原版是亮色专用，本项目坚持主题自适应）。构建 669 s；行数/词条/别名仍完全不变。

**第六轮（外部审计 A1–A6 / D23–D28，2026-09-12）**：修掉发布门禁（校验失败不得覆盖好包、CLI 退出码
0 → 2）、别名 rules 未按表达式取并集（940 → 0）、POS 正则被嵌套标签截断（281 → 0）、变形列表丢失
文字音标（596 词/816 块 → 0）、mono 模式泄漏中文（243 → 0，两处成因）、sequence 校验盲点。
交付包 `LDOCE5pp_Yomitan_2026.09.12.zip`，60,209,514 B；**245,933 行逐行比对，表达式/评分/sequence
全部不变，glossary 变化全是纯插入**。细节与验证见 `converter/audit_2026_09_12/FIXES.md`。

**第七轮：本仓库首次把「审源码」而非「只审 ZIP」的审计纳入流程。** 该审计还暴露了一个环境级教训：
报告第一版因 PowerShell `$OutputEncoding` 为 `us-ascii`，中文在进管道时被替换成 `?` 而**不可逆丢失**
（详见坑列表 #47）。今后所有写报告的脚本必须显式 UTF-8 并做写入前后字节比对。
`.mdd` 里的 182,065 个 mp3 **接不进弹窗**（SC 无 audio tag），插图仅 15 张，均不做——见 §9.9。

**§5 的坑列表本轮新增 27–29 三条（顺序不可自造、同类元素可重复、`.mdd` 读取方式），§9 新增 §9.9，§4 的文件清单有较大变化，§10 的依赖多一个 `lxml`。**
新增审计工具：`audit3_reproduce.py` / `audit4_structure.py` / `audit5_headword.py` /
`audit6_diff.py` / `audit7_parser_equiv.py` / `audit8_head_order.py` / `bench_parse.py` /
`build_ref_render.py`（用原版 CSS 生成参考渲染页）。

**第六轮（独立复审 + 修复，见 REVIEW.md D10–D17）**：

| 项 | 结果 |
|---|---|
| 词族面板丢内容（`span.opp` 反义词、裸文本成员） | 修（影响 12.6% / 2.0% 的词族块） |
| 词头 `GRAM` 丢方括号与限定词（`[singular, uncountable]`） | 修（508/1,501 词条） |
| "LDOCE Online" 增补条目当普通词条外露（`absurd` 两个词条） | 修（618 词条，改为默认折叠面板） |
| 搭配框 `span.HEADING` 义项分组标签丢 | 修 |
| 变形列表丢 BrE/AmE 区域标签与 `(same pronunciation)` | 修（58/2,389 跨度） |
| 复制脚本把源码截断为 0 字节 | **已从 git 恢复**，新增原子写工具与快照 |
| 校验器漏检复合 class | **已加固**（复合值 token 必须有 `~=` 选择器） |
| `span.opp` 内词族词丢类名 | 修（unknown-class 噪声归零；修它时引入的裸文本回归被断言当场拦住） |

新增工具：`_apply_patch.py`（原子写补丁框架）、`_restore_all.py`（本轮补丁重放）、
`_fix_after_recovery.py`、`_patch_validator.py`、`verify_recovered.py`（四项修复的行为验证）、
`audit9c_compose.py`（把 audit9 的缺失逐词元归因到源路径）、`wf_loss_quant.py` / `box_probe.py` /
`heading_quant.py` / `gram_quant.py` / `infl_inside.py` 等定量脚本。


---

## 1. 项目概述与交付物

**任务**：把本地 MDX 词典 `C:\workspace\ldoce\LDOCE5++ V 2-15.mdx`（235,059,959 B，朗文 LM5pp HTML 内核）转换成 Yomitan format-3 词典包。方法论参考 `github.com/shoujocyber/OALD10-Yomitan-Converter`（仅方法模板，实现全部重写）。

**当前状态：已完成并通过多轮审计，可直接交付安装。**

> ⚠️ 本节以下的"最终数字"是 **v1.0.0 初版**（915.7 s）。此后经过审查与修复，耗时与部分计数已变，
> **以 §0 修订记录为准**；行数/词条数/别名数三者未变。

### 交付物清单

| 路径 | 说明 | 状态 |
|---|---|---|
| `C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.12.zip` | **主交付物**，双语版，60,209,514 B（未压缩 470 MB，25 个 term bank + index + tag_bank + styles.css）。sha256 `d63a7ad99fcde2131982f5177b27237ec788034aa1c32cdca5d97665e44095f7` | ✅ 最终版（A1–A6 修复后） |
| `C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.11.zip` | 上一版交付物，保留用于逐行比对（`converter/audit_2026_09_12/diff_before_after.py`） | 📦 归档 |
| `C:\workspace\ldoce\converter\ldoce2yomitan.py` | **转换器，唯一事实来源**（单文件 ~2060 行，无包依赖结构） | ✅ 最终版 |
| `C:\workspace\ldoce\yomitan_debug\..._DEBUG.zip` + `term_bank_1.json` | 13 个测试词条的调试包（JSON 带缩进，可 diff） | ✅ 与主版同步 |
| `C:\workspace\ldoce\yomitan_mono_smoke\..._EN.zip` | 纯英文模式冒烟包（--limit 300，非全量） | ⚠️ 演示用 |
| `C:\workspace\ldoce\preview.html` | SC→HTML 本地预览（镜像 Yomitan 生成器语义），浏览器直接打开 | ✅ |
| `C:\workspace\ldoce\README-yomitan.md` | 面向**使用者**的安装/特性说明 | ✅ |
| 本文档 | 面向**维护者**的交接 | — |

### 最终数字（全量构建，915.7 s）

```
记录扫描        285,017 条（词条 64,659 / 唯一 key 64,390；redirect 218,252；skip 2,106）
渲染词条         64,390 行（score 10，同 key 多记录 → 269 个重复表达式各成一行）
别名重定向行    181,274 行（score -10，"non-lemma" tag，rules 继承目标词条）
别名行去留     186,424 个别名 key = 181,274 成行 + 5,150 个自身就是真词条的 key（正常让位给词条行）；HTML 污染导致的真断链修复后 = 0
查询链接       1,945,431 个存活 / 4,596 个降级为虚线 span / 0 悬挂
渲染异常             0   空内容行  0   seq 0..245932 连续无洞
```

---

## 2. 数据流架构

```
LDOCE5++ V 2-15.mdx
   │  (prepare_input: mdict_utils.unpack；缓存出 <源>.mdx.txt，mtime 新于 mdx 则复用)
   ▼
extract\LDOCE5++ V 2-15.mdx.txt   (877.5 MB；协议: KEY行\n正文...\n"</>"行)
   │
   ├─ Pass A（全文件扫描①）: classify_record → TermIndex(exact/by_fold/by_norm)
   │                          + alias_rows + 别名预规划(target_map/resolve_with → linkable)
   ▼
Pass B（全文件扫描②）: LdoceRenderer.render_record
   │   BeautifulSoup(html.parser) → 类名分派 → SC(dict) 树 → sanitize_strings
   ▼
term_bank_N.json (10000 行/个) + 尾部别名行 + index.json + tag_bank_1.json + styles.css
   │
   ▼
ZIP (deflate level 6) → validate_package（内嵌校验器，全量模式=严格"目标必须有真实行"）
```

关键设计：**两遍扫描换流式内存**。Pass A 建全键索引 → Pass B 渲染时链接解析不回写；别名行的 linkable 注册在 Pass B **之前**规划（否则流式渲染看不见后写的行），渲染实际失败数 ≈0 由严格校验器兜底显形。

---

## 3. 重建 Runbook

环境：`C:\workspace\ldoce\venv`（Python 3.13.5 + beautifulsoup4 + **lxml** + tqdm + mdict-utils + jsonschema + fastjsonschema）。

> ⚠️ **`lxml` 不在 PyPI 可达范围**（pypi.org 与清华镜像都被挡）。本机是从同版本 Python 3.13.5
> 的 conda 环境复制 `lxml 6.1.1`（`etree.cp313-win_amd64.pyd`，ABI 一致）到 venv 的：
> `copy C:\Users\<user>\miniconda3\Lib\site-packages\lxml <venv>\Lib\site-packages\lxml`
> **换机器必须先解决 lxml，否则 import 直接失败。** 若实在装不上，把文件头的
> `HTML_PARSER` 改回 `"html.parser"` 也能跑，只是慢约 1.5×（输出经证明逐字节相同）。

```powershell
${env:PYTHONIOENCODING}='utf-8'   # 否则中文 print 在 pwsh 下直接 UnicodeEncodeError
# 全量双语（~15 分钟，主要是 2×877MB 扫描 + 500MB 压缩）
& C:\workspace\ldoce\venv\Scripts\python.exe -u C:\workspace\ldoce\converter\ldoce2yomitan.py `
  -i 'C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt' -o C:\workspace\ldoce\yomitan_full -m bilingual
# 调试包（13 词，~16 秒，含内嵌校验）
... --test-words 'A,the,run,improve,...' --keep-json --no-progress
# 纯英文（源里 cn_txt 全剥，校验器强制全 bank 零 CJK）
... -m mono [--limit 300]
# 常用开关: --open-panels(details 默认展开) --revision 2026.9.10 --skip-validation --limit N
```

`-i` 也可直接指 `.mdx`（自动解包）。后台长跑用 `python -u` + Tee，**没有 -u 时管道块缓冲，日志半天下不出一行**（本项目踩过两次）。

---

## 4. 文件清单（converter\ 与周边）

| 文件 | 用途 | ⚠️ |
|---|---|---|
| `ldoce2yomitan.py` | 唯一事实来源（v1.1.0） | 直接改这个 |
| `part1_STALE.py` / `part2_STALE.py` | **已过期**（11:17/11:19 vs 主文件）；曾是分块写作产物，之后全部修复只落在合并文件。已于第二轮审查改名 `*_STALE` | **绝对禁止再 `copy /b` 合并**，会回滚全部审查修复 |
| `preview.py` | ZIP→独立 HTML 预览（模拟生成器：data-sc-* 属性、?query→#锚点、跳过 score<0） | |
| `dump_sc.py` | `dump_sc.py <zip> <词> [节点上限]` 把 SC 树打成人能读的 outline——**本项目的主力目检工具** | |
| `audit1_aliases.py` | 别名完整性普查（复用转换器函数 import，不复制逻辑） | ⚠️ 其 `skip records` 恒打印 0（死计数器，见 REVIEW D4） |
| `audit2_schema.py` | 官方 JSON Schema 抽样+极值 + 全量结构扫描 | 见 §8 为何不跑全量 |
| **`audit3_reproduce.py`** | 重放 Pass A + 别名预规划，抽样重渲染并与已交付 zip **逐字节比对** | 改渲染器后的首选门禁 |
| **`audit4_structure.py`** | 自写 SC 白名单/链接目标/CSS 覆盖/别名遮蔽独立扫描（不依赖自带校验器） | |
| **`audit5_headword.py`** | 词头污染回归门禁（有 exit code） | 见 §5.15 |
| **`audit6_diff.py`** | 两包前后对比（行数、`ld-defcn`、词头 diff） | 改渲染器后必跑 |
| **`audit7_parser_equiv.py`** | 解析器等价性（lxml vs html.parser 逐字节） | 换解析器必跑 |
| **`bench_parse.py`** | 解析/渲染基准，含样本缓存 `_bench_sample.pkl` | 避免重复扫 877 MB |
| `extract_payload.py` | 从 zip 抽 405 条分层样本喂 node 真生成器 | |
| `..\scgen_test\run_scgen.mjs` | Node+jsdom 加载 Yomitan 真 `structured-content-generator.js`（3 个 stub 模块）渲染样本 | `npm i jsdom` 已装 |
| `..\yomitan-ext\` | Yomitan release（契约核对源：`js/display/structured-content-generator.js`、`data/schemas/*.json`、`js/language/en/english-transforms.js`） | |
| `..\OALD10-Yomitan-Converter\` | 参考项目（重定向行形状等实证来源） | |
| `..\REVIEW.md` / `..\IMPROVEMENTS.md` | 第二轮审查报告 / 性能改进清单 | |
| 根目录 `*.log`、`dump_*.txt`、`d_*.txt`、`questions*.txt`、`tree_*.txt`、`corpus_profile.json` | 侦察/审计存档 | 可删 |

---

## 5. 关键坑列表（血泪，接手必读）

1. **`data-sc-class` 必须单 token**。Yomitan 把 `data:{class}` 整串写进一个属性，浏览器 `[data-sc-class="a b"]` 精确匹配对复合值**永远不命中**。全项目已改成单 token 纪律（`ld-ex-good`、`ld-panel-corpus`…），新加的 class 一律走 `generate_css()` 里补选择器 + `~=` 兼容列表头。复合样式（例:语料条目基础样式）用**逗号选择器列表**逐个 token 写，没有 `ld-corpexa` 这种"基础类"。
2. **本环境 `re.findall(r'\[data-sc-class(?:=|~)="..."\]', css)` 玄学只匹配 `~=` 分支**（dbg3.py 验证过）。校验器最终拆成两条独立 findall。写正则遇诡异漏配先拆模式对照，别怀疑人生。
3. **bs4 的 `Tag.__eq__` 是内容相等不是身份**，`x in list_of_tags` 会误判。所有"这个节点是不是那个"都用 `is` / `id()`（见 render_example 的 `is_in_cn`、render_box 的 heading 比较）。
4. **流式渲染时 resolve 不能查"已渲染集合"**。链接解析必须查 Pass A 的全键索引（`TermIndex.exact/by_fold/by_norm/linkable`），否则所有链接被降级。别名行同理：linkable 在 Pass B 前规划。
5. **`a.dictlink` 包住整个词条**（href="/index.html"）。分派器必须先 `_has_block_child()` 路由到块渲染，否则整词条被链接处理器吞掉。`span.frequent.Head` 也是同类事故：`frequent` 在 UNWRAP 表里会把词头拆散——**Head/Inflections 判断要放在 DROP/CHIP/UNWRAP 之前**（render_element 与 render_inline_node 都有守卫，别再挪到后面）。
6. **`@@@LINK=` 目标可能带 HTML**（`add<span class="OBJECT"> something ↔</span> on`），共 73 种/147 个词。`clean_target()` 去标签 + `norm_target()`（去空格/↔/NBSP + casefold）三级回退链：exact → casefold → 空格/连字符互换 → norm → linkable(norm 表)。**别退回裸字符串比较。**
7. **重定向行形状是实战验证过的**：`[word, "", "non-lemma", 目标rules拼接, -10, [[target, ["redirect"]], ...], seq, ""]`（OALD 参考项目同款）。`[target]` 内层必须是 `[term, rules]` 二元数组，不是对象。
8. **Yomitan SC 白名单严格**：`<a>` 只许 `{tag,content,href,internal?}`——给它 data/class/title 会在**导入时**整行报错。span/div/ol/ul/li/details/summary 才有 style/title/open。td/th 无 title/open。内部链接 `href="?query=<urlencoded>&wildcards=off"`，真生成器会重写为 `search.html?query=` 并打 `data-external="false"`。
9. **英文 deinflection rules token** 以 `yomitan-ext/js/language/en/english-transforms.js` 为准（n/ns/np/v/v_phr/adj/adv…），转换器用 POS_RULE_MAP 子集。改 rules 语义前先翻那个文件。
10. **无 `.mdd` 伴生文件** → 音频/图片资源物理不存在，`sound://`、`<img>`、speaker 图标全策略性剥离。哪天拿到 .mdd，接入点在 `render_head`(发音)、`render_example`(朗读)、资源路径 `get_media_filename`，还要 SC img 的 path 由 importer 收集 requirements。
11. **pwsh 引号地狱**：`cmd /c copy /b` 里嵌双引号会碎；改用 `& python.exe 'arg'` 直调 + 单引号。多行 Python 用 `@"..."@` here-string（内部 `\"` 在 Python 侧是合法转义）。
12. **`--test-words`/`--limit` 的部分构建里链接"目标有行"校验会假阳**——`validate_package(full_rows=...)` 只在完整构建传 True，部分构建回退查索引。别把部分构建的 dangling=0 当全量证据。
13. **构建日志消失**是块缓冲（见 §3 `-u`），Tee-Object 也一样。
14. exit code 1 但输出全绿：pwsh 管道对 native stderr 的 `$LASTEXITCODE` 传染（第一次全量构建 tqdm 期间），**先看日志末尾有没有 `[OK] Dictionary package` 再定罪**。
15. **`render_head()` 的兜底分支会把标签文本塞进词头**（v1.1.0 前）：它硬编码只认 HWD/HOMNUM/PronCodes/PRON/AMEVARPRON/lm5pp_POS/GRAM/LEVEL/FREQ/tooltip/Inflections 这 11 个，其余一律 `hwd_nodes.append(text)`，而 `hwd_nodes` 整体包在 `ld-hwd-wrap`（1.28em/700 粗体）里。结果 16,751 个词条（25.9%）词头被污染：`seeing` → `see·ingspoken`、`18-wheeler` → `18-wheel·erAmerican English AmE`、`abandon` → `¹abandon   AWL`。**关键教训**：泄漏的 13 个 class 里有 12 个在 `CHIP_MAP` 里早有映射（`REGISTERLAB`/`GEO`/`FIELD`/`Variant`/`HOMOPHONE`/`AC`…），`render_head` 只是从不查这张表。**改渲染器时先查已有映射表，别硬编码白名单。**
16. **`HYPHENATION` 是词头的音节切分"重复显示形式"**（HWD `abandon` vs HYPHENATION `a·ban·don`），必须丢弃；它是 §5.15 之外唯一没有映射的 Head 子元素类。
17. **`HYP` 不等于中点**：全库 146,026 个里 106,672 个是 `·`，但 **21,451 个是主重音 `ˈ`、17,903 个是次重音 `ˌ`**。硬编码成 `·` 会破坏 27% 的重音符（`second class` 显示成 `·second ·class`）。凡是"某 class 恒等于某字符"的假设，**先统计一遍再写死**。
18. **`HOMNUM` 必须 append 到词头之后**，不能 `insert(0, …)`：实测 12,612/12,612 个 Head 的 DOM 顺序都是 `HWD → HOMNUM`，`insert(0)` 会把 `abandon¹` 渲染成 `¹abandon`。
19. **`render_def()` 判"纯中文"要用 `.strip()`**：`sc_text()` 只折叠空白、不 strip，所以 `" "` 是真值，一个前导空格就会让 `cn_only` 判假，导致 119,249 个纯中文释义丢掉 `ld-defcn` 容器和 `lang="zh"`。
20. **别关 GC**：bs4 的树每个节点都持有父引用（引用环），只有循环回收器能释放。`gc.disable()` 会让 64,659 棵解析树全部滞留。用 `gc.set_threshold(50000, 100, 100)` 抬阈值才对。
21. **暗色主题不能跟操作系统走，也不能靠 `:root[data-theme=dark]` 选中**。两层坑，都已实测：
    - **坑一**：Yomitan 的主题是它自己的设置（`yomitan-ext/css/display.css:184` 的 `:root[data-theme=dark]`），与 OS 无关。用 `@media (prefers-color-scheme: dark)` + 硬编码前景色，会在"Yomitan 暗 + OS 亮"和"Yomitan 亮 + OS 暗"下把文字渲染成与背景几乎同色（1.02:1 / 1.39:1）。
    - **坑二（更隐蔽）**：**即使写成 `:root[data-theme=dark] …` 也没用**。Yomitan 用 `addScopeToCss()` 把整个 `styles.css` 嵌套包进 `[data-dictionary="…"] { … }`（`display.js:1317`）；嵌套规则不以 `&` 开头时会被隐式加上后代组合符，于是选择器变成 `& :root[data-theme=dark] …`，要求 `:root` 是本词典元素的**后代** —— 永远不匹配。实测词头仍是 `#1c1e21` 落在 `#1e1e1e` 上。
    - **正确做法**：**不要试图选中主题**。把调色板从继承来的文字色**派生**：基础色 `color:var(--text-color,#202124)`；中性色 `color-mix(in srgb, var(--text-color,currentColor) N%, transparent)`；彩色 `color-mix(in srgb, <中间调色相> 68%, var(--text-color,currentColor) 32%)`（亮主题变深、暗主题变浅，自动双向适配）。词头直接 `var(--text-color)`，**绝不写死颜色**。实测两主题下全部 ≥ 4.3:1。
    - 附带：**弹窗路径不做 CSS 消毒**（`setCustomCss()` 只是 `styleNode.textContent = css`），`sanitizeCSS()` 仅用于外部 API 路径，所以 `color-mix()` 能正常存活。
22. **同一元素可能承载不同语义的字符**：`HYP` 里 73% 是音节点 `·`、27% 是重音 `ˈ`/`ˌ`；两者需要不同样式（灰点带间距 vs 与词头同色、紧贴）。凡"某 class 恒等于某语义"的假设都要先统计再写死（同 §5.17）。
23. **改大段 CSS 后必须做声明级对比**，不能靠肉眼。把新旧 CSS 各自反解成 `{选择器: {属性}}` 再逐项 diff —— 这一招在本轮抓出了两处无意改掉的属性（`ld-act`/`ld-synmark` 丢了 `font-weight:700`、表格边框丢了暗色适配）。注意先剥掉 `/* 注释 */` 再解析，否则注释会和选择器粘在一起造成假"消失"。
24. **多 token 的 `data-sc-class` 必须用 `~=` 匹配**：`ld-sense ld-sense-n` 这种值是刻意为之，但 `[data-sc-class="ld-sense"]` 精确匹配**永远不会命中**它——基础规则也得改成 `~=`。见 §5.1。
25. **词典 CSS 一律被嵌在 `[data-dictionary="…"]` 之下**（`display.js` 的 `addScopeToCss`）。因此**任何锚在 `html`/`body`/`:root` 上的选择器都是死代码**（嵌套后会变成"要求 `:root` 是词典元素的后代"）。`@media` 块可以写，但里面的选择器同样被加作用域。写新样式时只锚定词典内部的类名。同理，**不要假设 `styles.css` 会覆盖宿主**——它只作用于本词典的词条区域。
26. **验证排版不要只看代码，也别只靠静态分析**：用真 Chrome 复刻 Yomitan 的注入结构（`[data-dictionary]` 嵌套 + `--text-color`/`--background-color` 两套变量）跑 `getComputedStyle`，才能量出真实对比度和真实生效情况。本轮的 T1 单靠读代码先后写错了两版。注意两个自己踩过的测量陷阱：① `getComputedStyle().color` 可能返回 `color(srgb r g b)` 小数格式，解析要兼容；② 无头 Chrome 默认 `prefers-color-scheme: dark`，会把"宿主报暗色"这条分支激活，测量前要显式钉住 `color-scheme`。
27. **元素的可视顺序只能来自源 DOM，不能自造模板**。`render_head()` 曾按 `hwd → gram → pron → pos → chips` 的固定次序拼装，把 `GRAM` 顶到音标前（`18-wheel·er [countable] /…/ noun`）。判定依据不能靠"哪种排布更常见"，而是要证明原版**没有**用 CSS 重排：拿到 `.mdd` 里的 `LM5style.css` 后确认词头区域无任何 `order:`/绝对定位（`.Head` 是 `display:inline`），视觉顺序 = DOM 顺序。**通法**：任何"按类别分桶再按固定次序输出"的渲染器都有此风险；改成单次遍历、遇到什么发什么。
28. **同一个"位置"在源里可能有多份，且顺序有语义**：`the` 有两条 `lm5pp_POS`（`definite article` + `determiner`），原来用单个 `pos_text` 槽位**只留最后一条**。凡是"每类元素只留一个值"的写法都要先统计该类元素的最大重复数。
33. **`text-indent` 是继承属性，会给 `display:inline-block` 的子元素埋雷**：例句块 `.ld-ex{text-indent:-1.6em}`，而芯片是 inline-block —— inline-block 会建立**新的块容器**，于是继承的负 `text-indent` 作用到它自己的首行，把盒内文字左移约 19px，且盒子的内在宽度按"首行左移"算 → **盒子比文字还窄，文字溢出边框并压到前一句上**（`rather` 的 `British English` 就是活证据，影响 598 处）。修法是给所有 inline-block 规则加 `text-indent:0`。同理要警惕 `line-height`/`letter-spacing`/`word-spacing`/`text-align`/`visibility` —— 都是继承属性。
34. **审计脚本不要硬编码包路径**：zip 名带修订日期，重建后路径就过期，审计会静默跑在**旧包**上（本轮踩到：`audit2/3/4/5` 全写死 `2026.09.10`）。已统一改成 `_find_zip()`（取 `yomitan_full` 里最新的非 DEBUG 包，argv 可覆盖）。
35. **大文件不要走 `git push`**：60 MB 的单次 POST（`Content-Length: 60052449`）无论直连还是经代理都会在**约 19 秒后被链路重置**（`curl 55 Send failure`），`http.postBuffer` 调大/调小、chunked、HTTP/1.1 均无效。**改用 Release 附件**（`uploads.github.com/.../releases/{id}/assets?name=X`）一次通过。
36. **`git push` 静默失败**：本机 `~/.gitconfig` 里有 `http.proxy`，且凭据助手会干扰；用 `git -c credential.helper= push <带 token 的 URL>` 才稳定。
30. **zip 在 Pass B 之前就已打开**（bank 是 `zf.writestr()` 流式写进去的，见 §9.8 的性能优化）。因此**任何在 Pass B 之后新产出的文件都必须走 `zf.writestr(name, payload)`**；只写磁盘文件不会进包。我加 `term_meta_bank` 时正是漏了这点，包内一度完全没有它，而磁盘上却躺着那个文件。
31. **别用 `start` 当循环变量**：`build()` 里 `start = time.time()` 是计时基准，遮蔽它会让 `Elapsed` 输出成 17 亿秒。用 `offset`/`idx` 之类。
32. **`cls & DROP_CLASSES` 不能作为"整块丢弃"的唯一判据**：元素可以同时带有意义的类与被丢弃的类（`Crossref imagerelated LDOCE5 ldoce4img`），首个命中就丢会连带丢掉真实内容。统一改用 `is_dropped(cls)`（`DROP_EXEMPT` 允许 `Crossref`/`crossRef` 胜出）。
29. **`.mdd` 的读取**：`mdict_utils.reader.MDD` **不支持下标**（`m[k]` 报 `TypeError`），要用 `m.items()` / `m.keys()`；返回的**键是 `bytes`**（需解码），且 `m.header` 是 **dict** 不是对象（没有 `.version` 属性）。别用全量 `findall` 去测"按单个 key 调用"的正则（`SKIP_KEY_RE` 就是这么被我误判成零命中的）。

---

37. **⚠️ 绝不要用 `io.open(path, "w")` 改这个文件——`newline` 参数非法也会先截断**。本轮把
    `ldoce2yomitan.py` 写成 0 字节就是这么发生的：`io.open(p, "w", encoding="utf-8", newline="\\n")`
    里 `newline` 传了**两个字面字符**（应为 `"\n"`），`io.open` 在抛 `ValueError` **之前**已经完成截断，
    2,585 行源码瞬间归零；随后一次"编译空文件"把 `__pycache__` 里的 `.pyc` 也覆盖成 113 字节，彻底断掉退路。
    **所有程序化改写必须走 `converter/_apply_patch.py` 的 `write_atomic()`**（临时文件 + `os.replace`，
    失败不触碰原文件），并且每条替换都要 `assert` 命中数。补丁示例见 `converter/_restore_all.py`。
    另：**改动要尽快 `git add`** —— 工作区版本一旦被截断，未入库的内容只能靠重放恢复（本轮全库 102 个
    git blob 里没有任何一个含本轮标记，直接还原无门）。恢复的锚点是"T9 重放后 md5 与事故前日志里
    打印过的 md5 逐位相同"。
38. **复合 `data.class` 只能用 `~=` 选择器命中，而它有两种截然不同的性质**。Yomitan 把 `data:{class}`
    写进**单个属性值**，`[data-sc-class="a b"]` 永不命中。于是：
    * **误用**：`cls="ld-panel ld-panel-online"` → 面板基础样式静默全失效（本轮实例，已改单 token）。
    * **正当用法**：`"ld-sense-cross ld-sense-n"` 这种"基础 + 修饰"是**设计如此**，靠
      `[data-sc-class~="ld-sense-n"]` 命中，不能一刀切禁止。
    **校验器已按此加固**：`collect_sc_classes()` 分开收集"整值 token"与"复合值内 token"，后者**必须**有
    `~=` 选择器，否则报错。改动渲染器发新 class 时，这条检查会在构建时就抓住问题。
39. **`sc_text()` 只折叠空白、不 `strip()`**（与 D1 同源）。凡是拿它做"这段文本非空吗"的判断，都要自己
    `.strip()`；本轮给词族加裸文本分支时正是漏了这一点，把每个标签间空白都变成了
    `<span class="ld-wf-word"> </span>` 外加空分组。
40. **一个元素类名可能同时承载"隐藏"与"可见"两种语义，按类名一刀切必错**：`LDOCEVERSION_new` 既在
    默认隐藏的 LDOCE Online 增补条目上（`.dictentry.LDOCEVERSION_new{display:none}`），也在**可见**的
    搭配框上（`<div class="ColloBox LDOCEVERSION_new BoxHide lm5ppBox">`，`.ldoceEntry .LDOCEVERSION_new`
    那条规则是**折叠**机制而 `BoxHide` 由 JS 展开）。判据要落到**祖先结构**上（本轮用
    `_is_online_entry()`：只认最外层容器），而不是类名本身。
41. **判定"原版是否显示"要去 `.mdd` 的 CSS/JS 里找反证，不能凭观感**：本轮据此确认了三件事——
    `.portrait` 与 `.landscape` **各自**都有 `display:none`（由 JS 二选一，故渲染全称是对的）；
    `h1.pagetitle`、`.Crossrefto .REFLEX`、`.bussdict`、`.suppressed`、`.BoxPanel` 原版都隐藏
    （所以 audit9 里那部分"缺失"不是缺陷）；而 `span.HEADING`（义项分组标签）与 `span.GEO`/`span.LINKWORD`
    （变形区域标签/注解）在原版**是可见的**，丢掉才是缺陷。

42. **`landscape` / `portrait` 的默认方向容易读反** —— 必须看 `@media` 上下文。`.portrait{display:none}` 之后
    在 `@media screen and (max-width:500px)` 里还有 `.landscape{display:none}; .portrait{display:inline}`。
    也就是说：**默认显示完整标签（landscape），缩写（portrait）只在窄屏出现**。用"按花括号切规则"的粗糙正则
    去读（会丢掉 `@media` 包裹）会得出**完全相反**的结论 —— 我据此差点否掉 D14 的方向。正确读法：先把 CSS
    按 `@media` 分块，再逐块解析。
43. **同一个缺陷类要一次找齐所有调用点**：D14 为 `GRAM` 修了 `span.portrait` 泄漏（引入 `_no_portrait_text()`），
    却把 `POS`（`_pick_landscape()`）和 `Inflections` 的 `infllab` 留在旧 helper 上，于是同一个 bug 又活了
    两处：**479 个词条的变形标签出现 `past tense pst abode`，168 个 POS span 丢掉并列项（`Algeria` → `adjective`
    而非 `noun, adjective`）**。改完一个 helper，务必 `grep` 它的全部调用点。
44. **新 CSS 类写进 `generate_css()` 不等于接线了**：`ld-infl-lab` 从首版就定义在样式表里，包内出现 **0 次**
    —— 定义了却从未被任何渲染分支输出。审查时把"CSS 定义了但包里 0 次使用"当成一条独立检查项，能反推出
    漏接的分支（本轮据此找到变形标签从未走标签类）。
45. **`.gitignore` 的判定别用子串 `in`**：我写了 `if '*.log' not in s` 来判断是否已加规则，而文件里已有的
    `converter/_*.log` 正好包含子串 `*.log`，于是规则从未写入、`git check-ignore` 一路报"仍入库"。
    判断忽略规则请直接用 `git check-ignore -v <路径>`，不要自己解析 `.gitignore`。
46. **审计日志别入库**（本轮起 `.gitignore` 已覆盖 `*.log`）：库里留着 46 个日志不只是噪音 —— 复审时我读到
    的 `audit5.log` 是**上一轮**的旧内容，差点据此判定"新包词头污染未检"。**重建后必须整批重跑审计**，
    或至少删掉旧日志，否则"读到的结论"和"当前的包"不是一回事。
47. **`$OutputEncoding` 会把中文吃掉，而且是不可逆的**（2026-09-12 报告编码事故）：PowerShell 5.1 的
    `$OutputEncoding` 默认是 `us-ascii` 且用替换式回退，中文 here-string **在进管道之前**就被换成 `?`
    （0x3F），此后任何 UTF-8 写入都救不回。症状是"英文/路径/数字都在，中文全变问号"——
    这与"用错编码读文件"完全不同（后者字节还在，换个编码就能还原）。修法是**在产生管道数据之前**
    设 `$OutputEncoding = [System.Text.UTF8Encoding]::new($false,$true)`，并**在写入前后按字节比对**；
    只设 `PYTHONIOENCODING=utf-8` 不够。
48. **正则 `(.*?)</span>` 不能配对嵌套 span**：`POS_SCAN_RE` 遇到第一个内层 `</span>` 就停，于是
    `<span class="lm5pp_POS"> <span class="landscape">adverb</span>…` 只捕获到 `' <span class="landscape">adverb'`，
    紧随其后的第二个 `lm5pp_POS` 只捕获到 `','` —— `above` 丢 `preposition`、`andante` 丢 `adverb`，
    共 **281 个词条**的 definitionTags/rules 错误。正确做法：正则只匹配**开标签**，正文用深度计数读取。
    注意这**不是**解析器差异（audit7 已证明 bs4/lxml 字节等价），**缺陷在正则本身**。
49. **"先发布、后校验"是反模式**：`build()` 曾在校验前就 `os.replace(.part → 正式包)`，校验失败只打印
    `[FAIL]`，随后仍打印 `[OK] Dictionary package` 并 **exit 0** —— 坏包静默覆盖好包，且对外报告成功。
    审查任何构建脚本时，除了"校验是否存在"，还要问三件事：**校验对象是未发布的文件吗？失败会覆盖旧产物吗？
    退出码/最后一行输出会骗人吗？**
50. **mono 的过滤逻辑分散在两处**：中文侧通常是 `span.cn_txt`，由 `render_inline_node()` 在 mono 下丢弃；
    但 ErrorBox 的「不要说…」用的是 **`div.cn_txt`**，div 到不了 `render_inline_node()`，会落到
    `render_div()` 的通用兜底（连 `ld-zh` 类都不加）而泄漏进 mono 包。修完标题后仍有 **56 个词条**泄漏，
    就是这条漏网。**加任何 mode 相关的过滤，必须同时覆盖 inline 与 div 两条分派路径。**
51. **新增 SC 类要同步审计脚本的白名单**：`ld-infl-pron`（A4 新增）会被 `audit8_head_order.py` 当成
    "我们这边多出来的 token"，报 `INFL / ld-infl-pron / INFL` 假阳性 —— 它需要被加进"属于 Inflections
    序列的注解"忽略列表。**加了新类就重跑全部门禁**，别只看审核通过就收工。
52. **本沙箱会拦截文件删除**：`shutil.rmtree` / `os.remove` 触发 fail-closed 回收站策略（
    `SAFE_DELETE_FAIL_CLOSED`），要么静默失败要么直接中止进程。两个后果：① 回归脚本不要靠"先删旧目录"
    开局，改用唯一目录名；② 断言"临时文件已清理"之前先探测该能力，否则会把环境限制误报成代码 bug
    （`regress_gates.py` 里已有这个探测）。另外 `dangerouslyDisableSandbox` 那一次运行是通过的，
    所以**同一条检查在有无沙箱下结论可能相反**。
53. **交付包名带构建日期，审计脚本必须自动挑最新的**：`_find_zip()` 之类"取 `yomitan_full` 里最新的
    非 debug 包"是必需的，硬编码 `…2026.09.11.zip` 会在重建后静默过期（audit3 的注释里记了这条教训）。

## 6. Yomitan 契约速查（format-3）

- **ZIP 成员**：`index.json`、`styles.css`、`tag_bank_1.json`、`term_meta_bank_1..N.json`（可选，频率元数据）、`term_bank_1..N.json`（文件名数字任意）。
- **term_meta_bank 行**：`[term, "freq", {"value": N, "displayValue": "S1"}]`。`value` 用等级的上限名次（S1/W1=1000、S2/W2=2000、S3/W3=3000），Yomitan 据此排序（lower = 更常用）。**没有这个 bank 就没有任何频率数据，无法按频率排序**；导入器只按文件名正则 `/^term_meta_bank_(\d+)\.json$/` 识别，且 schema 只允许 `freq`/`pitch`/`ipa` 三种 type。
- **term 行（8 字段）**：`[expression, reading, definitionTags, rules, score, glossary, sequence, termTags]`，前四+末全 string，`sequenced:true` 时第 7 字段必填 int（本项目全局连续）。
- **glossary 项**：`{"type":"structured-content","content":<SC>}` / `[target,["rules"]]`（重定向）/ `{"type":"text","text":...}`。
- **SC 节点**：`{tag, content?, data?, lang?, style?, title?, open?, href?, colSpan?, rowSpan?}`；`data` 值必须 string；`data.class` → 属性 `data-sc-class`。允许 tag：br ruby rt rp table thead tbody tfoot tr th td span div ol ul li details summary img a。
- **index.json**：本项目 `{title:"LDOCE5++ (LM5pp)", format:3, revision:"2026.09.10", sequenced:true, sourceLanguage:"en", targetLanguage:"zh"(bilingual)|"en"(mono), author,url,description,attribution}`。
- **tag_bank 行**：`[name, category, order(-5..100), notes, score]`，category ∈ partOfSpeech/frequency/search/...；本项目 33 个 tag（POS 1+，S1-S3/W1-W3 30+，redirect -5，non-lemma 100）。
- **词典 CSS** 由 Yomitan 原样注入词条作用域；`styles.css` 里 `@media (prefers-color-scheme: dark)` 已备。

---

## 7. LM5pp 源码 → SC 映射表（渲染器骨架）

源码层级：`span.lm5ppbody > div.entry_content > div.dictionary > [div.wordfams + div.dictentry > a.dictlink > div.ldoceEntry.Entry]`。

| 源元素 | 输出 | 备注 |
|---|---|---|
| `span.frequent.Head` | `div.ld-head` | **前置守卫**；内含 HWD/HYP(`·`→`ld-hyp`、`ˈ`/`ˌ`→`ld-stress`)/HOMNUM(→`ld-sup`，追加在词头**之后**)/`a.PronCodes`(含 `sound://` 剥离)/LEVEL(●●●,title 提示)/FREQ(S2/W1)/lm5pp_POS/GRAM([countable])/Inflections；**其余子元素一律查 `CHIP_MAP`/`INLINE_MAP` 渲染成芯片**（REGISTERLAB→`ld-register`、GEO→`ld-geo`、FIELD/FIELDXX、AC→`ld-gloss`、Variant/LEXVAR/AmEVariant/BrEVariant→`ld-lexvar`、HOMOPHONE→`ld-homophone`、PHRVBHWD→`ld-refhwd`、LINKWORD→`ld-collo`），`HYPHENATION` 丢弃 |
| `div.newline.Sense` / `span.Sense` | `div.ld-sense`（有编号时追加 `ld-sense-n` 才留悬挂缩进） | cross_sense/merge_sense → `ld-sense-cross/merge` 单 token；编号为**多 token**（`"ld-sense ld-sense-n"`），CSS 用 `~=` 匹配 |
| `span.DEF` | `div.ld-def`；纯中文 → `div.ld-defcn[lang=zh]` | cn_only = 剔除 cn_txt 后无残余文本（O(子树)，别重解析） |
| `span.DEF>span.cn_txt`（混排） | `span.ld-zh[lang=zh]` | |
| `div.EXAMPLE` | `div.ld-ex` + 内嵌 `div.ld-excn` | 风味单 token 阶梯：ld-gramexa > ld-colloexa > ld-ex-good(✓::before) > ld-ex-bad(✗) > ld-ex；`span.english` 定中文归属域 |
| `div.F2NBox/GramBox/ThesBox/ColloBox/UsageBox` | `details.ld-panel`（summary 双语标题 PANEL_TITLES_ZH） | heading 去 foldsign 后取文本；FrequenceBox 整个跳过；BoxPanel→ld-panel-boxbody |
| `div.asset + 连续 div.assetlink` | 合并成一个 `details.ld-panel-corpus` | exaGroup→`ul.ld-corpulist`，`span.exa[type=X]`→`li.ld-corpexa-X`（X∈corpus/dics/encyc/online/phrases） |
| `div.wordfams` | `details.ld-panel-wf` | **只处理带直接子 `sensefold` 的那种**（无表头的 38 个在原版永不显示）；POS 分组 `ld-wf-group`，crossRef 词→活链接，词根 `ld-wf-root`，反义词标记 `span.opp`→`ld-wf-opp`，裸文本成员→`ld-wf-word` |
| `div.dictentry.LDOCEVERSION_new` | `details.ld-panel-online`（默认折叠） | LDOCE Online 增补条目（LDOCE4 遗留，`type="encyc"`）。原版 `display:none` + `#switch_online` 开关，故保留内容但折叠；`_is_online_entry()` 只认最外层容器。**不能按类名整类丢弃**——同类名也在可见的搭配框上 |
| `span.HEADING`（盒内） | `div.ld-panel-sub > span.ld-grouptitle` | 义项分组标签（`– Meaning 1: …`），夹在折叠头与 `BoxPanel` 之间，旧代码只渲染 `BoxPanel` 把它丢了 |
| `span.etym` | `details.ld-panel-etym` | CENTURY/ORIGIN/TRAN/LANG → ld-century/origin/tran/lang |
| `a` href=`entry://X` | `?query=X&wildcards=off` 活链 / 降级 `span.ld-xref-dead` | resolve 链见 §5.6；topic-full 锚整个丢弃；`ACTIV:`/cn_topic→`span.ld-act(cn)` 绿芯片 |
| `span.GRAM/GEO/SENSENUM/SIGNPOST/REFHWD/...` | 同名 ld-* 芯片 | 全表在 part `CHIP_MAP/INLINE_MAP/UNWRAP_CLASSES`（文件头 400 行内） |
| `span.lm5pp_popup`、speaker、foldsign、img/input/label | 删除 | DROP_CLASSES/DROP_TAGS |
| 未识别 class | 通用 `span`+原文（现全库只剩 `Tail`×7196 与 `Error`×11） | 计数在 unknown_classes 报表，构建末尾打印 |

---

## 8. 校验体系（如何证明这批数据是对的）

| 层 | 工具 | 覆盖 | 最近结果 |
|---|---|---|---|
| L1 构建内嵌 | `ldoce2yomitan.py` 的 `validate_package`（自动随 build 跑） | **全部 245,933 行**：行形状/SC 白名单/零悬挂(严格实形)/CSS token 覆盖/index 字段/mono 零 CJK 全 bank | `[OK] Validation passed.` |
| L2 官方 schema | `audit2_schema.py`（Yomitan release `data/schemas/*.json` 原版 + fastjsonschema） | index、tag 全量；term **20% 分层抽样(50,402 行)+全库最小/最大各 200 行**；seq 连续性、控制字符、tag 词表、重复表达式 | 全 0 失败 |
| L3 真代码渲染 | `scgen_test/run_scgen.mjs`：Node24+jsdom 加载**未修改的** `structured-content-generator.js`（仅 stub DisplayContentManager/text-utilities/AnkiCM 三个模块文件） | 405 条样本（最大 run/get、15 最小、370 随机、topic/别名重点词）→ 真 DOM | 405/405 零异常，29,155 链接全部重写 search.html，details 全有 summary |
| L4 语义普查 | `audit1_aliases.py` + 定向抽查 | 218,252 @@@LINK 全分类；147 HTML 污染目标 100% 救回证明；2,106 skip 逐条核对（1907 ACTIV 主题页 + 184 图片 key + 15 LDOCE4 扫描页）；topic 链接实形存在 | 通过 |

**为何 L2 不跑全量**：fastjsonschema 对 470MB 嵌套 oneOf 实测 >50 分钟（杀），L1 的自研校验器语义等价且做过 diff 级抽查；抽样+极值（嵌套最深的行必在最大 200 行里）+L3 真代码渲染共同补齐。要全量跑就换 AJV（node，`import Ajv; compile(schema)`），预期几分钟。

**已知未验证项**：浏览器里真实扩展导入（chrome-devtools MCP 连不上 9821；headless 走不了扩展 IndexedDB 管线）——最终目检靠人：装 zip 或开 `preview.html`。视觉/深色模式未在真 UI 核对。

---

## 9. 后续 TODO / 扩展方向

1. 真机装包验收（**唯一缺口，也是当前最大风险**）：Yomitan → Dictionaries → Load zip，查词条显示/跳转/标签过滤/去词形搜索（输 `children` `ran` `improving`）。本轮所有验证都是"结构合法 + 能被真生成器渲染成 DOM"，**不等于**扩展导入后 UI 正确。
2. ~~若拿到 `.mdd`：接入音频与插图~~ **已结案（2026-09-10）**：`LDOCE5_V_2-15.mdd`（1.24 GB）已到手并普查完毕。**音频接不进弹窗**，插图不值得做。详见 §9.9；原版 CSS 已取出，用于终结 T8。
3. 4,596 个残余降级链接的 target 清单值得导出看一眼（改 render_link 记 Counter 即可），可能还有二级拯救空间（如 `A-level` 类标点差异）。
4. mono 全量包（-m mono，约同耗时）——当前只有 300 词冒烟；元数据零中文已修好并验证。
5. 若源 mdx 换版本：删除 `extract\*.mdx.txt` 旧缓存（prepare_input 按 mtime 复用，md5 不校验）。
6. ~~part1/part2 改名~~ **已完成**（→ `part1_STALE.py` / `part2_STALE.py`）。
7. 换皮到其它 LM5pp 词典（LDOCE6 预览版之类）：映射表集中在文件头 400 行的六张表，渲染器结构不用动。**注意**：新词典的 Head 子元素可能有本库没有的 class，改完先跑 `audit5_headword.py`（它同时会列出"Head 里出现但 render_head 不认识的 class"）。
8. **性能：还差最后一块。** 现状 686 s；瓶颈已定位为 **bs4 的 Python 对象构造（约 1.5 MB/s）且单核绑定**。上 **Pass B 多进程**（12 核，预期 6–8×）可压到 4–6 分钟。设计要点见 `IMPROVEMENTS.md` §2.8：按 `</>` 边界切分、TermIndex 经临时 pickle 分发给 worker（Windows 无 fork）、`sequence` 在主进程统一分配以保可复现。**注意每 worker 一份索引的内存开销。**
9. 解析器依赖：`lxml` 装不上时改 `HTML_PARSER = "html.parser"` 即可（输出逐字节相同）。
10. 其余待办清单（mono 元数据以外的小修、README/HANDOVER 数字、`audit1_aliases.py` 死计数器、seq 检查已内嵌）见 `REVIEW.md` §7。

---

## 9.9 `.mdd` 普查结论（2026-09-10）

`LDOCE5_V_2-15.mdd`（1,244.9 MB，183,926 条目，`Encrypted=2`，mdd 版本 2.0）。用 `mdict_utils.reader.MDD(p).items()` 遍历（**注意 `MDD` 不支持下标，且键是 `bytes`**）。

| 扩展名 | 数量 | 说明 |
|---|---|---|
| `.mp3` | **182,065** | 发音，`\media\english\{ameProns,breProns}\<key>.mp3` |
| `.spx` | 1,842 | 同上，Speex 编码 |
| `.jpg` | 15 | 图片 |
| `.css` / `.js` | 2 + 2 | `LM5style.css`(54 KB) / `LM5style_show.css` / `LM5Switch.js` / `jquery-3.2.1.min.js` |

**① 音频：接不进弹窗，结论是"放弃"。**
- Yomitan 的 structured-content **没有 audio tag**：`structured-content-generator.js` 的 `_createStructuredContentGenericElement` 是白名单 switch，只有 `br / ruby / rt / rp / table / thead / tbody / tfoot / tr / th / td / div / span / ol / ul / li / details / summary / img / a`。**没有 audio，也没有 video。**
- 词典内媒体确实有通用通道（`display-content-manager.js:95 openMediaInTab(path, dictionary)` → `api.getMedia` → `_getNormalizedDictionaryDatabaseMedia`），但它**只被 `img` 消费**；`term_meta_bank` 的合法枚举也只有 `freq / pitch / ipa`，没有 audio。
- 外部音频源（`media/audio-system.js`）走的是 **URL 模板**（jpod101 / custom URL / TTS），读不到 zip 内部。
- 代价对比：182 k 个 mp3 会把包从 **60 MB 撑到 1.2 GB 以上**，而弹窗里放不出来。⇒ 不做。
- 现状已正确：`speaker / brefile / amefile / fa / fa-volume-up` 全在 `DROP_CLASSES` 里，喇叭图标被丢弃（不留死按钮）。

**② 原版 CSS：已取出，用于终结 T8。** 见 §7 的 T8 / `TYPOGRAPHY.md`。三条硬证据：词头区域无 `order:`/绝对定位（视觉顺序=DOM 顺序）；`.HOMNUM{vertical-align:super}`（编号原地渲染，证实 `append` 修复正确）；`.HYPHENATION{display:none}`（是隐藏的音节切分副本，证实丢弃正确）。
**注意配色取向不同**：原版是亮色专用（词头红 `#ff0000`、词性/语法绿 `#008000`、语域紫 `#800080`、地域 `#364395`、AWL 黄底白字 `#f1d600`、FREQ 红框）。本项目坚持主题自适应，**不采用**。

> ⚠ **但 `LM5style.css` 不是完整的排版基准**：源记录引用 **3 个**样式表（`LM5style.css` + `LM5style_switch.css` + `LM5style_show.css`），mdd 里**只有 2 个** —— **`LM5style_switch.css` 缺失**，而它正是 `LM5Switch.js` 用来切换的那一套。所以"原版把某类设成 `display:none` ⇒ 我们该丢弃"的推断**不可靠**（可能被缺失文件重新显示）；反之"原版给了正向样式 ⇒ 可见"相对可靠。详见 REVIEW.md 的 D9（义项标签 `ACTIV` 就卡在这个歧义上，结论是**维持现状显示**）。

**③ 图片：不值得做。** 仅 15 张 jpg，且对应的图片页记录本来就在 `skip`（2,106 条里 184 条图片页）。

**复现**：
```bash
python -c "from mdict_utils.reader import MDD; m=MDD(r'LDOCE5_V_2-15.mdd'); print(len(list(m.keys())))"
```

---

## 10. 环境与依赖快照

- Windows / pwsh 7；Python 3.13.5 venv：beautifulsoup4 4.15、**lxml 6.1.1**、tqdm、mdict-utils（git 版，`mdict_utils.reader.unpack`）、jsonschema 4.26、fastjsonschema
- **lxml 是从同版本 conda 环境复制进来的**（PyPI 与镜像都被网络策略挡住），换机器需先解决
- Node v24.19 + `scgen_test/node_modules`（jsdom，38 pkgs）
- Chrome 152（headless 截过一次图，模型不可看图，未作最终依据）
- 机器 12 核；全量构建峰值内存约 1.2 GB
- 源数据只读约定：`.mdx` 从不改动；一切写操作在 `extract/ yomitan_* converter/` 下
- 构建计时基线：v1.0.0 = 915.7 s → v1.1.0 = 686 s（P0 性能优化后）→ 665 s（排版轮）→ 669 s（T8 词头顺序轮，Pass B 略增）；再上 §9.8 并行预期 250–350 s

—— 完 ——
