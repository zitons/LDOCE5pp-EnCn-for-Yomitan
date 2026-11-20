> 最新：r8 已解决原先剩余的 3 个斜杠案例，并修复 149 例中的另外 4 例。两批固定例句比 r7 多命中 10、7 条，原有命中无丢失。剩余 145 例已有逐条对照和中文分类清单，含 1 例词典选项与被动匹配的混合问题。详见 [PHRASE_REPAIRS_R8.md](PHRASE_REPAIRS_R8.md)。下文保留历史记录。

> 最新：r7 已修复同名正文漏义项和短语动词入口漏接。40 张卡片恢复 65 条原文释义；23 个已确认词典问题修复 20 个，3 个斜杠范围问题保留。两批各 2,000 条固定例句分别多命中 26、19 条，没有丢失原有命中。详见 [PHRASE_REPAIRS_R7.md](PHRASE_REPAIRS_R7.md)。下文 r6 诊断和规则是历史记录。

# 剩余问题实际出在哪里

目前正式做过的修改只有：在 r6 补入三条有限查词入口规则，新增 4,665 个入口。正文继承 r5，fushi 没有改。这一轮只诊断剩余问题，**没有更新正式 r6**。

这次查明：r6 仍有词典构建缺陷，不能把剩余案例都交给 fushi。“正文与 r5 一样”只证明没有改变旧数据，不能证明原文义项完整。

## 一、词典本身能处理，但 r6 还没做好

### 同名独立词条把短语动词的正文挡掉了

原代码认为独立词条的正文更完整，存在独立词条时就只选它，没有合并同名短语动词正文。

| 写法 | 原文另有的短语动词内容 | r6 该短语卡片实际保留 |
| --- | --- | --- |
| `put out` | 16 个原文动词释义，如扑灭、给人添麻烦等 | 1 个独立词条释义：感到不快／受冒犯 |
| `cut up` | 5 个原文动词释义 | 2 个独立词条释义，未合并那份动词正文 |
| `lie down` | 2 个原文动词释义 | 1 个独立词条释义，未合并那份动词正文 |

这是同写法不同词性／来源正文的合并问题。正确方向是保留各自的原文义项和词性，不是覆盖掉其中一份。这里的释义数量是不同原文字面释义数，不意味着彼此语义完全不重叠。其他卡片或主词条上下文可能仍含对应内容，问题是直接命中的这张短语卡片不完整。

依据：`build_ldoce6_phrases.py` 中 `candidates=dedicated or ...` 的二选一逻辑；提取数据库中三项均有短语动词正文，成品没有并入。逐项证据见 `diagnosis/source_sense_shadowing.json`。

### 查词入口只连到部分义项

例如 `put away` 现在指向 `put something away`，有收东西、存钱、进球等意思，却没有接到含“关进监狱”的总条目。因此 `put you away for life` 没打开正确义项。

原因分两层，不能混为一句“入口冲突”：

1. r6 要求原文有 `↔` 才提取内部带宾语的短语动词入口。`↔` 是宾语换位置的语法标记；用于提取**查词入口**时，这个条件过严。原文已经明确标为短语动词的总标题，也能提供有限的固定部分入口。
2. 新入口一旦与已有入口同名，`collect_heads` 就整项跳过；已有别名可补接合法目标，与已有正文不能被覆盖应分别处理。另查得 19 个被跳过的候选关联，但尚未逐项证明这 19 个都造成实际漏义项。

本轮另存实验包，依据原文 `phrvbhwd` 标题，仅去掉明确的通用宾语槽，保留全部固定词，再补接已有别名的目标。例子：

- `put somebody/something away → put away`，可打开“关进监狱”的原文释义。
- `put somebody/something off → put off`，可打开“让乘客下车”“干扰注意力”等遗漏义项。
- `drag something out of somebody → drag out of`，保留完整固定部分 `out of`，现有引擎能处理 `dragged a confession out of ...`。
- `put something at something → put at`，原文标题明确标为短语动词，例句本身是 `Her fortune was put at ...`。不能把这个有来源的入口与任意删除普通动词内部宾语混同。

这是诊断实验，还没有把扩大后的规则接入正式生成器，也未做这套实验规则的完整误报评估。不能把去占位符操作推广到所有普通短语；`endear somebody to somebody → endear to` 之类不因这一试验获得许可。

### 原文变体还没解析

`interested party/group`、`be/get tarred with the same brush`、`be patience/kindness/simplicity etc itself` 的具体入口可用。实验包分别补了 `interested party`、`tarred with the same brush`、`simplicity itself`，三条原句都能查回。

这只验证了明确写法的入口有效，通用斜杠边界解析尚未实现。不能据此批准任意斜杠交叉组合。

## 二、确实需要匹配能力的例子

以下成对输入已用同一 DLL 查询，并核对条目存在：

| 原句中的写法 | 词典里能查到的写法 | 实际问题 | 应处理的位置 |
| --- | --- | --- | --- |
| `made good` | `make good` | 原形能查到，过去式只返回单词 made/make，没有查回这条短语 | 引擎对固定短语的动词头还原；当前短语动词还原要求后一个词在介词／小品词集合中，good 不满足 |
| `out of my depth` | `out of your depth` | 只有 your 的字面入口能打开正确短语 | 引擎需要识别词典明确的所有格变量位置 |
| `give me a shout` | `give somebody a shout` | 引擎不能把内部 me 对应到 somebody | 引擎需要识别内部宾语槽，保留固定部分 a shout |
| `given himself over to pleasure` | `give yourself over to something` | 现在返回 give over／be given over to 等其他意思 | 反身代词、词形与完整短语结构的配合 |
| `modelled himself on ...` | `model yourself on somebody` | 现在返回 be modelled on，释义是设计上仿照，不是以某人为榜样 | 反身代词、词形与词典模式匹配 |

“匹配变量”应以词典的具体模式和来源为依据，不是把所有 my/your/me/him 全局互换。固定说法中的人称和所有格可能本来就不能任意换。

主词条上下文可能包含相关义项，但这里要求直接查回对应短语卡片。不能把“返回了 make/give 的整份主词条”说成已完成短语命中。

## 三、有些缺口是测试算错了

22 条原“待核”已逐条对照原句和返回卡片的释义：

| 结论 | 数量 | 例子 |
| --- | ---: | --- |
| r6 原本已返回适合原句的意思 | 6 | `put the ball away` 返回卡片已有进球义；比赛 `put off` 已有推迟义 |
| 单词被“两词起算”的评分排除 | 1 | `red-handed` 本身能查到，不需要造 caught red-handed 别名 |
| 可从词典入口／正文合并处解决 | 13 | 包括 put away 漏监禁义、put out 丢动词正文、drag out of 入口等 |
| 现有入口办法仍未解决的匹配问题 | 2 | give yourself over to、model yourself on |

另一个评分限制：`knocked him back ... dollars` 在实验包已返回含“花费很多钱”义的总条目，但评分要求另一卡片必须覆盖完整释义且至少一条释义达到 8 词；目标释义 `to cost you a lot of money` 只有 7 词，因此仍不计入。它在上表计入词典可处理的 13 条，不能仅凭自动分数把它继续算成引擎问题。

## 四、剩余 179 条的更正归类

| 分类 | 数量 | 证据强度 |
| --- | ---: | --- |
| 词典侧可处理 | **23** | 13 条来自上述义项审核；原“154 引擎候选”又有 7 条被原文短语动词入口试验查回；另有 3 条明确变体入口试验 |
| 本来能用／评分误判 | **7** | 逐例核对过的 6 条，加 red-handed 的单词评分问题 |
| 仍待定位的匹配候选 | **149** | 包括原 154 中剩下的 147 条，以及上述 2 条反身代词匹配；尚未全部逐条定位，不能叫 149 个已证实的 fushi bug |

实验包按原有自动判分能查回 26 条；其中 4 条在人工按本句义项判断时，r6 原本就已可用。加上人工确认的短释义例子与其他评分误判后，得到上面的责任划分。**不把这 26 条全称为新修复。**

## 这次实际完成与未完成的事

完成的是：原句与释义审核、两个词典构建缺陷的定位、三处同名正文遗漏的扫描、隔离实验包验证、固定短语词形与代词槽位的成对查询，以及更正此前分类。

尚未完成的是：把这次发现的正文合并和入口目标合并修入正式版，并做全量及留出样本回归；剩余 149 条匹配候选的逐项定位；fushi 的代码修改。**正式 r6 保持原样，仍有上述已知缺陷，不能称为最终完成版。**

下一步优先修词典正文合并与入口连接；这两处确定属于词典构建。之后再用修过的词典定位引擎问题，避免继续把词典缺陷转交给 fushi。

证据目录：`C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/diagnosis/`。

- `sense_review_evidence.json`：22 条原句、原目标释义、r6 返回卡片释义与人工结论。
- `corrected_remaining_179.tsv`：179 条更正分类。
- `source_sense_shadowing.json`：三处同名正文遗漏。
- `native_probe_evidence.json`：成对输入、r6 与实验包实际返回及相关释义。
- `diagnosis.json`：分阶段试验、逐例结果、实验包哈希与原包哈希。
- `summary.json`：最终计数与原包未改校验。

诊断脚本：`converter/diagnose_remaining_phrase_gaps.py`；人工义项结论：`converter/remaining_sense_review.json`；证据导出：`converter/summarize_remaining_diagnosis.py`。
