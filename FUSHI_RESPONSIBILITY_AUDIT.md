# Fushidicts 与词典入口的责任划分

本轮只做隔离试验与分类，没有修改正式 r4/r5 ZIP、词典生成规则或 fushidicts。结论是：r5 的大量回退可以通过少量、有限的词典入口恢复；剩余问题再交给引擎评估，不能把删掉的自动生成字符串都算成引擎缺陷。

## 分类数据

分母是上一轮固定随机抽取的 2,000 条原文例句中，r4 命中而 r5 未命中的 **497 条**。使用 scan=128、相同规范词条或完整原文释义覆盖的判分口径。按以下优先顺序分类，每条只计一次：

| 处理位置 | 数量 | 依据与状态 |
| --- | ---: | --- |
| 词典：有限入口 | **318** | 三条通用入口规则联合试验已恢复，约占回退的 64.0% |
| 词典：显式变体解析候选 | **3** | 原文明确列出变体，本轮三条规则未覆盖，尚未实测修复 |
| 引擎：通用匹配能力候选 | **154** | 有限入口试验后仍缺失；应评估参数槽位、固定短语词形、被动结构等能力 |
| 释义／评分待核 | **22** | 已返回其他短语，或受至少两个词的评分限制影响；不能计作确定的引擎缺陷 |
| 合计 | **497** | 分类基于检索代理指标，尚非逐例义项标注的准确率 |

词典方向共 321 条，其中只有 318 条经过本轮实验验证。引擎方向的 154 条是待评估案例，不是 154 个已定位的代码 bug，也不意味着引擎单侧修改就能全部解决。按条目表面结构优先标记，119 条含宾语／所有格／反身代词等槽位，35 条属于其余固定短语词形；同一例句可能同时需要词形、槽位与原文变体支持。

## 有限入口如何试验

从冻结的 r5 规范词条和保留别名生成入口；可分离语序另读取原文 evidence.tsv 的 `phrvbhwd` 与 `↔` 标记。生成过程不读取测试例句，也不读取 r4 被删别名清单。

1. 词首 `be` 提供查词入口，例如 `be a piece of cake → a piece of cake`。这是查词入口，并不宣称原句语法可以任意省略 be。
2. 只去掉末尾完整的通用宾语槽，例如 `look after somebody/something → look after`；不删除内部宾语或词汇成分。
3. 只有原文明确写作 `动词 + 通用宾语 ↔ 单个小品词` 时，才提供动词加小品词入口，例如 `throw something ↔ away → throw away`。小品词受固定集合约束。

入口必须至少两个词，不含未解析的斜杠、括号、占位符、etc；现有词条优先，不覆盖内容。词首 be 与末尾槽位可组合。大小写入口按现有索引方式补充。不枚举 her/him/you、任意名字、句子宾语或各种屈折词形。

例如 `endear somebody to somebody`、`put something at something` 不会被压成 `endear to`、`put at`；`give somebody a hand` 不会被压成 `give a hand`。边界测试覆盖这些情况。

总共添加 **4,665 个入口拼写、4,804 个入口与目标词条的关联**，数量约为 r4→r5 删除入口数 306,454 的 1.52%。这是另存的实验 ZIP，未更新正式构建。

## 实测结果

| 同一批原文例句 | 命中数 / 2,000 | 命中率 |
| --- | ---: | ---: |
| r4 | 1,455 | 72.75% |
| r5 | 958 | 47.90% |
| r5 加三条有限入口规则 | **1,277** | **63.85%** |

原 r5 的 958 条全部保住；在原 497 条回退中恢复 318 条；在原两版都未命中的 545 条中额外命中 1 条，其余 544 条仍未命中。958 + 318 + 1 = 1,277。因此“还有 179 条原 r4 命中未恢复”与“还比 r4 少 178 个总命中”是两个不同口径。

这里的“恢复”指能查到目标词条，不代表完整匹配范围全部恢复。在 318 条中，267 条与 r4 的起点和匹配文本相同，28 条同起点但匹配文本缩短，23 条起点或范围发生其他变化。例如 `looked after us` 在实验包只匹配 `looked after`，能查到目标条目，但未证明引擎识别了末尾宾语 us。

58 条控制正例中实验包命中 13 条，原 r4 为 35、r5 为 12。10 条控制负例中，实验包错误接受指定目标 1 条，与 r5 相同，r4 为 5 条；仍是 `being to do something`。10 条负例不足以证明整体误报率，本轮不宣称入口方案已经达到发布标准。

## 具体案例

| 方向 | 原文中的输入 | 规范目标 | 判断 |
| --- | --- | --- | --- |
| 词典已实测恢复 | `throw clothes away` | `throw something away` | 补 `throw away` 后，现有引擎已能处理插入宾语 |
| 词典已实测恢复 | `looked after us` | `look after somebody/something` | 补 `look after` 后还原动词头，实际匹配 `looked after`，未包含 us |
| 词典已实测恢复 | `kicked him out` | `kick somebody out` | 补原文明示的 `kick out` 入口即可，无需枚举 him |
| 词典已实测恢复 | `a piece of cake` | `be a piece of cake` | 查词入口去词首 be |
| 引擎候选 | `out of my depth` | `be out of your depth` | 词典已经提供 `out of your depth`，仍需所有格槽位匹配 |
| 引擎候选 | `made good` | `make good` | 已有固定短语入口，现有短语动词词形规则没有覆盖此结构 |
| 引擎候选 | `give me a shout` | `give somebody a shout` | 宾语位于短语内部，不能靠任意删除宾语解决 |
| 词典变体候选 | `tarred with the same brush` | `be/get tarred with the same brush` | 需先可靠解析原文明列的 be/get；未试验额外解析规则 |
| 词典变体候选 | `interested parties` | `interested party/group` | 需提供原文明列的 party/group 查词入口，再验证现有复数还原 |
| 词典变体候选 | `is simplicity itself` | `be patience/kindness/simplicity etc itself` | 原文变体边界与固定后缀需要词典侧处理，不能盲目做斜杠组合 |
| 待核 | `put the ball away` | `put somebody/something away` | 实验包已返回 `put something away`；需要逐义项确认是否已满足此句 |
| 评分边界 | `caught red-handed` | `red-handed` | 规范词条只有一个词，本轮要求至少匹配两个词，不能按缺失短语判为引擎 bug |

“引擎候选”表示应该集中汇报的通用能力需求；优先评估固定短语的词形还原、带类型的宾语／所有格／反身代词槽位、被动结构及匹配边界。现有引擎已具备部分短语动词还原和插入宾语匹配，因此不能按 r4 别名记录最后一步规则直接归因。

## 证据与复现

数据目录：`C:/workspace/ldoce/_tmp/r4-r5-fushi-benchmark/responsibility_audit/`。

- `report.json`：2,000 条逐例试验结果、控制正负例、原包与 DLL 哈希、实验包哈希。
- `responsibility.tsv`：497 条回退逐项分类、原句、目标、r4 匹配、试验匹配与残留返回。
- `classification.json`：分类总数、人工复核例外及哈希。
- `entrance_evidence.json`：每个新增入口对应的规则、原始写法与目标。
- `r5_bounded_heads_EXPERIMENT_ONLY.zip`：仅供复核的隔离实验包。
- `converter/phrase_responsibility_review.json`：3 条变体候选及 22 条评分／释义待核项，按固定样本 ID 与目标双重校验。

在工作树根目录运行：

```powershell
python converter/audit_phrase_responsibility.py --benchmark C:/workspace/ldoce/_tmp/r4-r5-fushi-benchmark --transforms C:/workspace/fushi/fushi/assets/transforms
python converter/summarize_phrase_responsibility.py --benchmark C:/workspace/ldoce/_tmp/r4-r5-fushi-benchmark
python -m unittest discover -s converter -p test_audit_phrase_responsibility.py
```

本次仍沿用检索代理指标：在例句任一单词起点，返回指定词条或完整原文释义覆盖词条，并匹配至少两个词。它不是逐义项、逐边界的人工金标准。规则设计参考了此前差异，重新测量同批样本证明的是可行性；正式采用前还需要未参与分析的留出例句、更多负例和义项审核。306,454 个被删自动生成字符串包含不自然或错误形式，未逐条审查，不能把其中未命中的数量直接解释为引擎问题数量。
