> 最新：r7 已修复同名正文漏义项和短语动词入口漏接。40 张卡片恢复 65 条原文释义；23 个已确认词典问题修复 20 个，3 个斜杠范围问题保留。两批各 2,000 条固定例句分别多命中 26、19 条，没有丢失原有命中。详见 [PHRASE_REPAIRS_R7.md](PHRASE_REPAIRS_R7.md)。下文 r6 诊断和规则是历史记录。

# 交接：LDOCE6 短语词典

> 后续诊断更正：r6 仍有词典构建缺陷。已发现 put out、cut up、lie down 的独立词条正文挡掉同名短语动词正文；短语动词入口亦有漏接总义项。剩余 179 条经本轮审核改分为词典侧可处理 23、原本可用或评分误判 7、仍待定位匹配候选 149。仅做隔离诊断，正式 r6 未修改。详见 [PHRASE_REMAINING_DIAGNOSIS.md](PHRASE_REMAINING_DIAGNOSIS.md)，不应再把原 154 条候选统称为引擎问题。

> 最新：r6 已补入经过验证的三条有限查词入口规则，新增 4,665 个入口；不恢复代词或词形穷举。新抽且排除旧样本的 2,000 条例句命中从 r5 的 942 提高到 r6 的 1,280，原有命中无丢失。成品、规则取舍、20,396 个无需恢复的旧别名、5 个已知错误别名，以及 fushi 待办明细见 [PHRASE_RULES_R6.md](PHRASE_RULES_R6.md)。正文、来源上下文与 r5 逐行完全一致，r4/r5 原包冻结不变。

> 下文 r5 的“禁止所有未标可选 be／宾语省略”属于历史策略；r6 现在仅允许文档明确列出的查词入口省略，仍禁止无依据删除内部宾语、所有格或词汇成分。

> 更新于 2026-11-18。r4/r5 现均冻结供对照；r5 删除策略未通过可行性验证，不应直接作为替代版。r4 的格式检查通过不代表语言正确；不要再将其 28 万新增入口作为覆盖改进成果。
> 后续全量对照：403,811 个分组案例，加 2,000 个独立源例句抽样。允许来源同文释义覆盖时，r4 为 72.75%，r5 为 47.90%；497 例只有 r4 查回。本轮未改生成规则或词典包，详见 [FUSHI_R4_R5_BENCHMARK.md](FUSHI_R4_R5_BENCHMARK.md)。


工程根目录 `C:\workspace\ldoce`；实施工作区 `_tmp\ldoce6-phrases-work`，分支 `feat/ldoce6-phrases`。以下产物相对工程根目录。

## r5：只保留可靠且通用的来源规则

用户要求：不可靠的机械修改去掉；Fushi 无法处理的输入集中汇报，不再穷举实际代词和词形去绕过引擎限制。

已移除：

- 代词、所有格、反身代词枚举，以及与动词词形的交叉组合；相关生成模块已删除。
- 自动动词变形、推测名词复数。源明确声明的复数/拼写仍保留。
- 未标可选的宾语、所有格、首部 be 删除，包括 r3 遗留规则。
- 一律连字符转空格、只凭词性相同批准斜杠组合、仅凭大写逗号猜人名倒序。
- 将逗号/斜杠混合的声明变体直接当作完整入口。14 个有歧义的源声明另列待审，不猜其边界。

保留：原始短语和释义；明确括号可选项、可判定的源斜杠选项、源例句支持的备选、↔ 标明的可分结构、源明确声明的独立变体/复数、sb/sth 记号缩写、标点编码规范化、明确后置冠词索引及小写查询键。未解决的词典记号保留原文并列入 review.tsv。

## 成品与验证

- [LDOCE6_Phrases_2026.11.18-r5.zip](yomitan_phrases/2026.11.18-r5/LDOCE6_Phrases_2026.11.18-r5.zip)，10,234,140 字节。
- SHA256：`47c780943de1b542551decc0a9c2f8119d10c79752b905f3743f465d5bc2ebfa`。
- 32,889 个规范短语、7,346 个来源上下文、33,912 个别名，共 74,147 行。493 个别名有多个源目标，不强行选择单一义项。
- 规范短语清单、释义/例句数量、来源父词条与 r4 完全一致；别名从 340,366 减至 33,912。
- 规范化多词查询键为 55,079，较 r4 有意删除 302,052 个；移除记录见 removed_multiword_queries.txt。不以查询数量作为质量指标。
- 11 项当前回归测试通过。已删除专门验证被撤销枚举逻辑的旧测试；新增整个构建流程的禁止生成测试。
- 全部 74,147 行官方 Schema 通过、54,488 条内部链接无无效目标或重定向链、13 个实际生成器渲染样例通过。
- 复用已验证的源提取数据库，再重读完整源缓存重建声明变体；未重新下载源数据。
- 2,353 个复数查询在扫描长度 16 / 128 时命中 2,048 / 2,340，与 r4 相同；57 个可分查询为 15 / 25。
- 54 个探针中 52 个规范目标有效，128 时 11 个命中、41 个未命中，另 2 个源模式缺失。未命中者集中列于 [FUSHI_QUERY_GAPS.md](FUSHI_QUERY_GAPS.md)。未修改 Fushi 或发布远端包。

报告目录：`yomitan_phrases/2026.11.18-r5/`。主要报告为 build_report.json、cleanup_audit.json、coverage_audit.json、upgrade_report.json、comparison/support_report.json、supplemental_source_report.json、engine_gaps/gap_probes.json、coverage_report.json。review.tsv 中 11,441 条是待审记录，不是确定错误条目数。

## 复跑

在实施工作区运行：

```powershell
$r = 'C:\workspace\ldoce'
$py = "$r\venv\Scripts\python.exe"
$out = "$r\yomitan_phrases\2026.11.18-r5"
$pkg = "$out\LDOCE6_Phrases_2026.11.18-r5.zip"
# 完整构建；已有 extraction.sqlite 可加 --reuse-extraction。
& $py -X utf8 converter/build_ldoce6_phrases.py -i "$r\_tmp\phrase_audit\records.jsonl" --cache -o $out --revision 2026.11.18-r5 --supplement-sources
& $py -X utf8 -m unittest discover -s converter -p 'test_*phrase*.py'
& $py -X utf8 converter/audit_ldoce6_phrase_build.py $out --baseline "$r\_tmp\phrase_audit\core_all_comparison.tsv"
& $py -X utf8 converter/compare_phrase_support.py --ldoce6 $pkg --ldoce5 "$r\yomitan_full\LDOCE5pp_Yomitan_2026.10.03.zip" --previous "$r\yomitan_phrases\2026.11.18-r4\LDOCE6_Phrases_2026.11.18-r4.zip" --allow-query-removals -o "$out\comparison"
node "$r\converter\audit_2026_09_14\official_schema.mjs" $pkg
node converter/render_phrase_samples.mjs $r "$out\render_samples.json" "$out\render_samples.html"
& $py -X utf8 converter/audit_fushidicts_gaps.py --revision r5 --package $pkg --import-dir "$r\_tmp\fushi-engine-probes\r5" --output "$out\engine_gaps" --dll "$r\_tmp\fushi-engine-build\Release\fushidicts_ffi.dll" --transforms 'C:\workspace\fushi\fushi\assets\transforms'
```

当前构建有意撤除不可靠旧入口，因此比较时明确传 --allow-query-removals，并输出完整删除清单。全部原始源查询仍要求保留。根目录其他工作不得一并覆盖或提交。

以下 r3 及早期内容保留作历史记录；发生冲突时，以本节最新用户约束和最终验收结果为准。

> **r3 已完成**：未找到 5++ 原作者的上游生成源码，已根据全量源重定向审计独立实现并改进规则，代码在 `_tmp/ldoce6-phrases-work/converter/phrase_alias_rules.py`，来源与范围见同目录 `phrase_rule_provenance.json`。成品 `yomitan_phrases/2026.11.18-r3/LDOCE6_Phrases_2026.11.18-r3.zip`：41,709 个别名键；规范化后的多词查询键 71,426，较 r2 增加 13,408，旧查询键全部保留；5++ 独有查询从 32,501 降为 21,660。新增分组多词选项、明确括号、可分动词宾语调序、标点/连字符、人名/冠词调序，以及受限 be/占位符查询省略；未加入自动词形变化或虚构同义词。生成只读 LDOCE6 数据，5++ 仅供离线研究和比较。七组回归、79,602 行官方 Schema、全量源覆盖、53,823 条链接和 13 个实际生成器渲染样例通过；这不等于逐条语言学审核无误。验证与比较结果均在 r3 目录下，`upgrade_report.json` 记录新增覆盖，`aliases.tsv` 记录目标和规则。

> **后续全量审计更正（2026-11-18）**：下文早期的 26,909、104,907、去标点比对及“大部分是模式展开”属于旧口径，不能作为最终覆盖结论。r2 成品在仅统一大小写和空白、排除主题导航后，LDOCE6 / LDOCE5++ 的多词查询键分别为 **58,018 / 78,634**，5++ 独有 **32,501**。5++ 的 **48,371** 个非主题多词重定向均能在源 TXT 中找到原始 `@@@LINK` 键；转换器只清理、解析和合并源重定向，不生成斜杠等变体。全量规则特征分类、29,540 个未覆盖的重定向查询键明细，以及四个入口族的集合复现验证见 [_tmp/ldoce5_rule_audit/classified_report.json](_tmp/ldoce5_rule_audit/classified_report.json) 和 [classified_aliases.tsv](_tmp/ldoce5_rule_audit/classified_aliases.tsv)。规则分类是对现存数据的观察，原作者的上游生成代码尚未取得；不可声称已还原全部原始算法。5++ 中确有有用的省略、可分动词调序、复数、拼写和同义别名，也有人名/冠词调序及机械展开错误，不能把差额一概当成缺失习语，亦不能一概当成无用入口。
> 项目其他部分见 `README.md`、`HANDOVER.md`、`AUDIO.md`（后者是音频库，与本文无关）。

## 一句话背景

仓库里有两本朗文：

| 包 | 形态 | 位置 |
|---|---|---|
| **LDOCE5++ En-Cn** | 已成品的 Yomitan 包 | `yomitan_full/LDOCE5pp_Yomitan_2026.10.03.zip`（61 MB，25 个 `term_bank`） |
| **LDOCE6 英英版** | **MDict 源包**（mdx，未转换） | `C:\Users\zitons\Downloads\LDOCE6EnEn_v2026.11.16-*.zip` → 已解压到 `_tmp/ld6/LDOCE6EnEn_v2026.11.16/` |

LDOCE6 的转换器在 **`feat/ldoce6-en-en` 分支**（PR #13），文件 `converter/ldoce6en2yomitan.py`，
**只转文本、不处理音频**。任务是在它之上补「短语提取」。

## 现状数字（都实测过，可直接当验收基线）

### LDOCE6 英英版

| 项 | 数值 | 说明 |
|---|---:|---|
| mdx 大小 | 162.6 MB | `Title = LDOCE6 En-En`、`CreationDate 2026-11-16`、引擎 2.0 |
| 词条 | **52,745** | `len(mdx._key_list)` 与遍历 `mdx.items()` 一致（有 4 个重复键：`expose`/`lame`/`pate`/`rose`，各自出现两次） |
| 归一化后不同的词条 | **52,220** | 去大小写/标点/括号后的去重数，与 5++ 比对时用这个口径 |
| 键里带空格的条目 | **12,967** | 这些是独立成条的短语 |
| 短语总数（键 + 词条内嵌） | **26,909** | 含括号变体，未归一化 |

### LDOCE5++

| 项 | 数值 |
|---|---:|
| 词头 | 242,646 |
| 含空格的键 | 104,907 |
| 其中含数字/斜杠/百分号的**模式条目** | 5,389 |

⚠️ **5++ 的 10 万「短语」要打折**：它把 `a (a) moment/hour or two`、`$100/50 a clip`
这类斜杠变体全部铺成了独立键。排除数字模式、去掉括号后仍有 102,109，但抽样看
绝大多数是同一模式的组合展开，不是真正的独立短语。

### 交叉比对（脚本 `_tmp/cmp_phrase.py`，可直接复用）

归一化（去括号及其内容 → 去标点 → 压空格）后：

| 项 | 数值 |
|---|---:|
| LDOCE6 短语 | 25,183 |
| LDOCE5++ 短语 | 102,109 |
| **重合** | **24,239（96.3%）** |
| 只在 LDOCE6 | **944** |
| 只在 LDOCE5++ | 77,870（大部分是模式展开） |

**结论**：LDOCE6 的短语 96.3% 已被 5++ 覆盖。所以「短语提取」的价值不在于补数量，
而在于 **LDOCE6 的标记更干净**（见下），能产出一份结构化的短语索引。

只在 LDOCE6 的 944 条样例：`a good screw`、`a hot date`、`a run on the bank`、
`a short space of time`、`a shoulder to cry on`、`a who's who of something`、
`after you`、`answer to the name of something`。

## 数据长什么样（关键，别猜结构）

### 短语在 LDOCE6 里的两种存在形式

**1) 独立词条**：键本身带空格，例如 `a hot date`、`3-D printer`。

**2) 内嵌在词条里**（大多数），藏在 popup 盒子内：

```html
<span class="popup-button" onclick="...showAtLink(this)">Phrases</span>
<div class="at-link"><span class="entry">
  <span class="popheader popphrase">PHRASES FROM OTHER ENTRIES</span>
  <span class="phrase">
    <span onclick="...toggle(this)" class="expandable">
      <span class="arrow">►</span>
      <span class="phrasetext">answer criticism/charges/accusations etc</span>
    </span>
    <div class="content"><ul class="exas"><li>…<span class="nodeword">answer</span>…</li></ul></div>
  </span>
```

要点：

- 提取锚点是 **`span.phrasetext`**，不是键
- 短语的例句在紧随的 `ul.exas > li`，例句里用 `span.nodeword` 标出词头位置
- 同一词条可能有多个 popup 盒子：`popcollo`（搭配）、`popthes`（同义词）、
  `popphrase`（短语）、`popwf`（词族）、`popexa`，**只要 popphrase 或 phrasetext**
- `span.phrasetext` 内部可能还有标签（如 `<span class="hs0">` 音节点），提取前先 `re.sub(r"<[^>]+>", "", t)`

### 已知的四种「脏」写法（必须处理，否则数量会虚高/虚低）

| 写法 | 例子 | 处理建议 |
|---|---|---|
| 斜杠变体 | `answer criticism/charges/accusations etc` | 拆成三条 + 保留原条；`etc` 标记为开放模式 |
| 括号可选 | `(hard/hot/close) on somebody's heels` | 生成带括号与去括号两种键；去括号版本用于比对 |
| `somebody/something` | `a shoulder to cry on` 里常带 `somebody` | 统一转成 `sb`/`sth` 还是原样保留，**先和用户确认口径** |
| 数字/单位模式 | `$100/50 a clip`、`1,300/15/30/18/05 hours` | 5++ 里有 5,389 条这类；建议单独归一类，不要混进正文短语 |

## 建议的产出

1. **`_tmp/phrases_ldoce6.tsv`** —— 全量短语索引，列建议：
   `phrase_raw` / `phrase_norm` / `headword` / `sense_num` / `source`（key 或 inline）/
   `popheader` / `example`（第一条例句，纯文本）
2. **与 5++ 的差集**：`_tmp/phrases_only6.tsv`（预期约 944 条，用于补 5++）
3. 若要进 Yomitan：按现有 `converter/ldoce6en2yomitan.py` 的 format-3 契约追加 term bank
  （该文件 `--limit N` 可抽样，`--revision` 控制包版本）

## 验收

- 短语总数应落在 **26,000 ± 1,500**（差异来自斜杠/括号展开口径）
- 只在 LDOCE6 的那批数量级应是 **900–1,200**；若差一个数量级，多半是归一化规则不一致
- 抽 10 条人工核对：`phrasetext` 与例句是否对应、`nodeword` 是否真的是短语里的词
- 与 5++ 比对时**必须两边用同一套归一化**，否则会出现几万条假差异（第一次跑就踩了）

## 环境与规范

```bash
# 读 mdx / mdd 用这个（装了 mdict_utils + bs4）
C:\workspace\ldoce\venv\Scripts\python.exe

# 只做 SQLite / 数据分析用这个
C:\Users\zitons\miniconda3\python.exe
```

- 网络要走代理：`curl -x http://127.0.0.1:7890 ...`（shell 里没有全局代理）
- Git：提交走分支 + PR，不要直接推 `main`。本机 git 建引用偶发静默失败，
  若 `git checkout -b` 后 `git branch` 里看不到新分支，用 `git write-tree` +
  `git commit-tree` + 手写 `.git/refs/heads/<名>`（详见 `HANDOVER.md` 的坑 67 附近）
- `LDOCE6EnEn.mdd`（图片 + 音频）**不在这个 zip 里**，readme 给了地址与
  MD5 `4b0f87f4a205d0226a1c1808a0138fc5`。没有 mdd 时，`img/*` 全部裂图 ——
  纯文本提取不受影响，但出成品包要补

## 不要做的事

- **不要把 `a (a) moment/hour or two` 这类当成「5++ 独有短语」** —— 那是模式展开
- **不要把「归一化后的去重数 52,220」当成词条数** —— 真实词条是 52,745
- **不要试图把例句音频搬进 Yomitan**：structured-content 没有 audio 标签，
  Hoshi 的本地音频库又只按 `expression` 查表，例句音频没有对应键（见 `AUDIO.md`）
