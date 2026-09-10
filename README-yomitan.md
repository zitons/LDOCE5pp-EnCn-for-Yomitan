# LDOCE5++ → Yomitan 词典转换

## 产物

| 文件 | 说明 |
|---|---|
| `yomitan_full\LDOCE5pp_Yomitan_<date>.zip` | 全量双语版（推荐，含中文释义/翻译/搭配中文） |
| `yomitan_debug\LDOCE5pp_Yomitan_<date>_DEBUG.zip` | 测试词条的调试包（JSON 带缩进，便于检查）。**词条数取决于 `--test-words` 传了什么**，最近的样例是 11 条 |
| `converter\ldoce2yomitan.py` | 转换器（单文件，Python 3.11+，依赖 beautifulsoup4 / **lxml** / tqdm / mdict-utils） |
| `preview.html` | 本地 SC 渲染预览（模拟 Yomitan structured-content 生成器 + styles.css） |

> ⚠️ `lxml` 是必需依赖。装不上时把文件头 `HTML_PARSER` 改回 `"html.parser"` 可运行（输出逐字节相同，只是慢约 1.5×）。

## 安装

1. Yomitan → 设置 → Dictionaries → Load (install) → 选择 `LDOCE5pp_Yomitan_*.zip`。
2. 勾选启用该词典，建议排序在 OALD 之前或之后均可。
3. 词内超链接（蓝色实心词）= 跳转词条（内部 `?query=` 搜索链接）；绿色虚线词 = 主题词(ACTIV，源库为独立页面未收录)；灰色虚线下划线 = 源链接指向不存在的词条（降级处理）。

## 内容特性

- 64,390 词条 + 181,274 条别名重定向行（复数/过去式/派生词/大小写变体、主题页链接、含 147 个源库 HTML 污染 @@@LINK 的修复行），共 245,933 行。
- 194.7 万个词条内查询链接（含 2.77 万条 topic 别名行链接），仅 4,596 个降级（源库真缺失目标）；校验器对全部行做"目标必须有真实行"的强约束，零悬挂。
- 词头：括号音标、●●● 核心词等级（悬停有 tooltip）、S1/W1 频次徽标、词性、[countable] 语法框、变形（plural/past 等 · 分隔）。**语体/地域/学科/学术词表/变体/同音词等标签都渲染为独立芯片**（不再粘进词头），多词词头保留 `ˈ ˌ` 重音标记。
- 义项编号 + 语法标签（[intransitive]、[countable]）+ 中文翻译（紫色）逐行跟随英文释义。
- 例句：`–` 前缀、✓/✗ 例句、语法框例句；中文翻译独立行；Don't-say 框内红色删除线错法 / 绿色正法芯片。
- 折叠面板：Word family（词族）、Register/Grammar/Thesaurus/Collocations/Usage 框、语料库例句(Corpus examples，同组自动合并)、Encyclopedia、词源（Word origin）、Extra examples。
- 搜索命中自动去词形：deinflection rules 从源词性标签推导（n/v/adj/adv/v_phr…），`children` 可直接命中 `child`。
- tag bank：词性标签 + S1-S3/W1-W3 频次标签 + redirect/non-lemma，支持 Yomitan 标签过滤。
- `term_meta_bank`：**真实频率数据**（5,971 行，`[term,"freq",{value,displayValue}]`）。S1–S3/W1–W3 现在同时是"可过滤的标签"和"可排序的频率"，可在 Yomitan 里按词频排序。
- `term_meta_bank`：**真实频率数据**（5,971 行，`[term,"freq",{value,displayValue}]`）。S1–S3/W1–W3 现在同时是"可过滤的标签"和"可排序的频率"，可在 Yomitan 里按词频排序。
- 无音频（源库无 .mdd 伴生文件，sound:// 全部剥离）；ACTIV 主题页为绿色芯片纯文本（源为独立页面体系）。

## 质量审计（构建后自动 + 多轮外部验证）

1. **构建内嵌校验器**（`validate_package`，随 build 自动跑）：全 245,933 行逐行检查——行形状、SC 节点白名单、`?query=` 链接与 redirect 目标的"必须有真实行"强约束（零悬挂）、序列号唯一且连续、CSS token 覆盖、index 字段、mono 包零 CJK。
2. **Yomitan 官方 JSON Schema**（`converter/audit2_schema.py`，release 原版 schema + fastjsonschema）：index 与 tag bank 全量，term bank 取 **20% 分层抽样（50,402 行）+ 全库最大/最小各 200 行**。*（全量跑法：470 MB 嵌套 oneOf 在 fastjsonschema 下 >50 分钟，属该库的性能问题；换 AJV/node 可全量。）*
3. **Yomitan 真实渲染管线**（`scgen_test/run_scgen.mjs`）：Node+jsdom 加载与 release **逐字节相同**的 `structured-content-generator.js`（stub 掉 3 个模块：display-content-manager / text-utilities / anki-template-renderer-content-manager），把 405 条抽样渲染为真实 DOM——405/405 零异常，29,155 个内部链接全部改写为 `search.html?query=`，details/summary 结构完整。
4. **别名/链接完整性普查**（`converter/audit1_aliases.py`）：218,252 条 @@@LINK 全分类；147 条含 HTML 的目标经 `clean_target` 归一化救回；2,106 条 skip 全部核对为 ACTIV 主题页(1907)/图片页(184)/扫描页(15)。

### 独立复核工具（第二轮审查新增，均不依赖转换器自带校验器）

| 工具 | 作用 |
|---|---|
| `audit3_reproduce.py` | 重放 Pass A + 别名预规划，抽样重渲染并与已交付 zip **逐字节比对**（代码↔产物一致性门禁） |
| `audit4_structure.py` | 自写 SC 白名单/链接目标/CSS 覆盖/别名遮蔽独立扫描 |
| `audit5_headword.py` | **词头污染回归门禁**（有 exit code，可挂 CI） |
| `audit6_diff.py` | 两个包的前后对比（行数、`ld-defcn` 计数、词头差异） |
| `audit7_parser_equiv.py` | 解析器等价性（`lxml` vs `html.parser` 逐字节比对） |
| `audit8_head_order.py` | **词头顺序门禁**：源里每个 `.Head` 块与输出的 `ld-head` 块逐块配对、逐 token 比对（8,000 词条 → 9,040 块，不一致 0） |
| `audit9_text_conservation.py` | **文本守恒门禁**：逐词条比对源文本与输出文本的词元多重集，找"悄悄丢内容"的地方 |
| `build_ref_render.py` | 用 `.mdd` 里的原版 `LM5style.css` 把源 HTML 渲染成参考页（用于对照原版排版） |
| `audit8_head_order.py` | **词头顺序门禁**：源里每个 `.Head` 块与输出的 `ld-head` 块逐块配对、逐 token 比对（8,000 词条 → 9,040 块，不一致 0） |
| `audit9_text_conservation.py` | **文本守恒门禁**：逐词条比对源文本与输出文本的词元多重集，找"悄悄丢内容"的地方 |
| `build_ref_render.py` | 用 `.mdd` 里的原版 `LM5style.css` 把源 HTML 渲染成参考页（用于对照原版排版） |
| `bench_parse.py` | 解析/渲染基准（带样本缓存，避免重复扫 877 MB） |

## 重新生成 / 参数

```powershell
# 全量双语
python converter\ldoce2yomitan.py -i 'C:\workspace\ldoce\LDOCE5++ V 2-15.mdx' -o yomitan_full -m bilingual
# 纯英文（剥离所有 cn_txt，validators 会强制检查零 CJK）
python converter\ldoce2yomitan.py -i '...mdx' -o yomitan_mono -m mono
# 调试小包 / 展开面板 / 保留中间 JSON
python converter\ldoce2yomitan.py -i '...mdx' -o yomitan_debug -m bilingual --test-words 'A,the,run' --open-panels --keep-json
```

`-i` 直接指向 `.mdx`（自动调 mdict-utils 解包，缓存为 `*.mdx.txt`）或已解出的 txt（`extract\LDOCE5++ V 2-15.mdx.txt`）。

## 校验器

构建结束自动跑 `validate_package`：ZIP 结构、index 字段（format3/sequenced/语言对）、8 字段行结构、SC 节点白名单（tag/prop/data 值必须字符串、`a` 仅 tag/content/href/lang）、glossary 非空、redirect 与 `?query=` 链接零悬挂、每个 `data-sc-class` 有 CSS 覆盖、mono 包零 CJK。
