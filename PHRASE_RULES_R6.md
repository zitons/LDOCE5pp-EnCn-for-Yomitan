> 最新：r8 已解决原先剩余的 3 个斜杠案例，并修复 149 例中的另外 4 例。两批固定例句比 r7 多命中 10、7 条，原有命中无丢失。剩余 145 例已有逐条对照和中文分类清单，含 1 例词典选项与被动匹配的混合问题。详见 [PHRASE_REPAIRS_R8.md](PHRASE_REPAIRS_R8.md)。下文保留历史记录。

> 最新：r7 已修复同名正文漏义项和短语动词入口漏接。40 张卡片恢复 65 条原文释义；23 个已确认词典问题修复 20 个，3 个斜杠范围问题保留。两批各 2,000 条固定例句分别多命中 26、19 条，没有丢失原有命中。详见 [PHRASE_REPAIRS_R7.md](PHRASE_REPAIRS_R7.md)。下文 r6 诊断和规则是历史记录。

# r6：修复查词入口，规则与别名清单

> 后续诊断：r6 还存在同名正文未合并、入口漏接义项的问题；“与 r5 正文一致”并不能证明原文义项完整。put out、cut up、lie down 三处已定位，正式 r6 尚未修正。最新责任划分和已验证案例见 [PHRASE_REMAINING_DIAGNOSIS.md](PHRASE_REMAINING_DIAGNOSIS.md)。下文记录的是 r6 当时的变更与测试结果，不应当作所有问题均已解决。

这次补回的是有原文依据的通用查词入口，没有恢复代词和词形的穷举。像 `kick out` 只需建一个入口，`kicked him out` 交给现有 fushi 处理。r4、r5 原包保持冻结，r6 单独生成。

成品：[LDOCE6_Phrases_2026.11.18-r6.zip](/C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/LDOCE6_Phrases_2026.11.18-r6.zip)。

## 这次修了什么

| 通用规则 | 例子 | 边界 |
| --- | --- | --- |
| 原文标明宾语可换位置的短语动词，提供动词加小品词入口 | `kick somebody ↔ out → kick out` | 必须是原文短语动词标题，必须有 ↔；不猜普通动词的宾语能不能省 |
| 去掉词典记号中的末尾通用宾语 | `look after somebody/something → look after` | 只去末尾完整槽位，保留所有固定词和内部宾语 |
| 去掉词首 be，提供查词入口 | `be a piece of cake → a piece of cake` | 这是查词入口，不是宣称句子中 be 可以随意省略 |

入口至少两个词，不能残留未解析括号、斜杠、通用宾语或 etc。已有正文词条优先，不用别名覆盖内容。每个原始写法只处理一轮，不递归扩张，不组合实际代词、名字或动词词形。

因此不会生成 `give somebody a hand → give a hand`、`endear somebody to somebody → endear to`、`put something at something → put at` 这样的无依据删除。相应边界有回归测试。

新增 **4,665 个入口**；别名总数从 33,912 变成 **38,577**。32,889 个规范词条、7,346 个来源上下文，以及所有正文内容逐行与 r5 相同；r5 原有别名及其目标集合也完全保留。

这轮先交付验证过的三条规则。`be/get tarred with the same brush`、`interested party/group`、`be patience/kindness/simplicity etc itself` 的变体解析仍列候选，没有凭猜测扩大斜杠拆分。

## 测试结果

| 原文例句测试，scan=128 | r5 | r6 | 新增命中 | 原有命中丢失 |
| --- | ---: | ---: | ---: | ---: |
| 之前分析的 2,000 条 | 958 | **1,277** | 319 | **0** |
| 排除前一批后另抽的 2,000 条 | 942 | **1,280** | 338 | **0** |

新例句样本与旧样本的 `(目标词条, 原句)` 交集为零，固定种子 20261119；排除原 2,000 条后从其余 21,506 条中抽取。不保证短语类型互不重复，也不是独立外部语料测试。

小扫描窗口也单独测过：scan=16 时，旧样本 832→1,120，新样本 790→1,095，原有命中同样没有丢失。数据文件沿用原脚本字段名称，其中 `r4` 表示本轮基线 **r5**，`r5` 表示本轮候选 **r6**；以 manifest 包哈希为准，勿混作历史 r4/r5。

这里“命中”是能查到原文对应词条或含相同完整释义的词条，不保证每次都匹配整段短语。之前 497 条回退中找回了 318 条，其中 267 条匹配起点和文本与 r4 相同，28 条同起点但缩短，23 条范围或起点有其他变化。例如 `looked after us` 在 r6 实际匹配的是 `looked after`，已能打开对应条目，但没有证明引擎识别了 us。另新增 1 条，合计增加 319。

其他验证：

- 32,889 个规范词条、33,912 个原别名、4,665 个新入口，共 **71,466 次完整输入查询全部命中对应目标**；该控制检查允许别名多个原文目标中的任意一个，不宣称全部义项都同时出现在前 32 个结果。
- 58 条控制正例 r5/r6 为 12/13；10 条控制负例两版都错误接受 1 条，未增加该小组误报。`being to do something` 仍被引擎错误还原为 `be to do something`，已记录，并未建此别名。
- 16 项回归测试通过，包含禁止乱删词、原文 ↔ 约束和已有内容冲突测试。
- 全量源覆盖、内部链接检查、78,812 行官方 Schema、13 个实际 structured-content 渲染样例通过。

这说明有限入口规则在所测例句上有效，仍不能代替逐义项、逐边界的人工准确率评估；10 条负例也不足以估计整体误报率。

## 有用、无须单建和不可靠的规则

| 规则类型 | 处理 | 理由 |
| --- | --- | --- |
| 本轮三条有限入口规则 | **启用** | 实测改善，严格保留固定词和来源边界 |
| 明确括号可选项、可确定边界的原文备选、例句支持的变体 | **保留** | 来源能解释入口；有歧义的继续列 review |
| 原文 ↔ 标明的调序、明确声明的拼写／词汇变体／复数 | **保留** | 属于原文事实，不能与推测复数混在一起删掉 |
| 小写查询键、引号等标点编码规范化、明确后置冠词索引 | **保留** | 处理索引表示；不猜大小写人名顺序或任意改连字符 |
| him/her/you、所有格、反身代词逐个枚举并交叉组合 | **继续停用** | 入口膨胀，仍接不住任意名字；还会生成主宾格不合的形式 |
| 对短语穷举动词词形、推测名词复数 | **继续停用** | 已能由引擎处理的没必要单建；处理不了的集中报告，不用几十万入口补洞 |
| 无依据删除内部宾语、所有格或其他固定词 | **继续停用** | 会造出 `endear to`、`a word in ear` 之类错误入口 |
| 一律把连字符改为空格、仅凭词性相同批准斜杠组合、凭大写逗号猜人名顺序 | **继续停用** | 这些推断不能保证是同一词或正确的原文变体 |
| sb/sth 等词典记号入口 | **保留并单列用途** | 可用于手动输入记号查词；不把它们宣传为自然句匹配能力 |

“停用”不等于这些规则生成过的每个字符串都错误；可靠来源入口可以由其他有限规则保留。尤其不能把尚未命中的自动生成形式全部说成 fushi 的问题。

## 别名逐条清单

以下均在 `C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/alias_audit/`：

| 清单 | 数量 | 含义 |
| --- | ---: | --- |
| [restored_lookup_heads.tsv](/C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/alias_audit/restored_lookup_heads.tsv) | **4,665** | 本次补入的有限入口，附目标与规则 |
| [redundant_aliases.tsv](/C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/alias_audit/redundant_aliases.tsv) | **20,396** | 不必恢复的旧入口：冻结 r5 不建这些别名，仍已完整匹配输入并返回其全部原目标 |
| [known_bad_aliases.tsv](/C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/alias_audit/known_bad_aliases.tsv) | **5** | 已有控制负例证实不应生成的旧入口 |
| [not_restored_aliases.tsv](/C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/alias_audit/not_restored_aliases.tsv) | **301,834** | r4 中有而 r6 中没有的全部别名，附分类；不是 301,834 个都“没用” |
| [manual_notation_aliases.tsv](/C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/alias_audit/manual_notation_aliases.tsv) | **19,445** | 当前含词典记号的别名，供手动模式查询；不计作自然用法枚举成果 |

20,396 个无需恢复的别名中，14,605 个来自动词词形、5,574 个来自名词词形、212 个来自代词替换、5 个来自词性斜杠展开。这里证明的是“这个入口不用单建也能查到全部原目标”，不保证输入本身合乎语法、排名不变或对应义项一定适合某个句子。

例如 `A levels → A level`，无需专建复数入口。反例 `AS to Z → A to Z` 虽然引擎也会还原并命中，但输入本身很可疑，更不能以“能命中”为理由恢复这种机械入口。

5 个已知错误入口是 `a word in ear`、`being to do something`、`endear to`、`how can her do it?`、`how can me do something`。其余未恢复项中，108 个只有部分原目标被引擎覆盖，281,325 个仍需来源、语法或引擎能力分析；它们均有明细，不冒充已确认的“无用别名”。

## 留给 fushi 与继续审核的内容

本轮从 r6 实际重新查询后导出：

- [154 条引擎能力候选](/C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/fushi_handover/engine_candidates.tsv)：有原句、应查到的词条、r4 匹配范围、r6 查询与实际返回。包括固定短语词形、内部宾语、所有格及反身代词槽位、被动结构等；尚不等于 154 个已定位 bug。
- [3 条原文变体解析候选](/C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/fushi_handover/dictionary_notation_candidates.tsv)：未在本轮猜拆。
- [22 条释义或评分待核](/C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6/fushi_handover/sense_or_scoring_review.tsv)：例如已返回另一短语条目，需要人工判定义项，或规范词条只有一个词而被“两词”评分限制排除。

另有 `being to do something` 的错误还原，完整记录在 `validation/release_checks.json` 的控制负例结果中。本轮没有修改 fushi。

## 构建与复核位置

代码在 `C:/workspace/ldoce/_tmp/ldoce6-phrases-work`，分支 `feat/ldoce6-phrases`；三条规则集中在 `converter/phrase_lookup_heads.py`，生成器与隔离试验共用同一实现。r6 复用了冻结 r5 的提取数据库副本，未重采或改变源词条范围。

包 SHA256：`9b125999e0a357ac6dfd1a09e7db3b01c037fcd3c1d62af4101cc21a10e1e9d0`。

验证目录 `validation/` 保存旧样本、新样本和全量查询明细；`alias_audit/alias_decisions.json` 保存清单计数及 r4/r5/r6 哈希；`fushi_handover/manifest.json` 保存交接计数与 r6、DLL 哈希。官方 Schema 与渲染结果在 r6 构建目录。

在实施工作树中复跑构建：

```powershell
C:/workspace/ldoce/venv/Scripts/python.exe -X utf8 converter/build_ldoce6_phrases.py -i C:/workspace/ldoce/_tmp/phrase_audit/records.jsonl --cache --reuse-extraction -o C:/workspace/ldoce/yomitan_phrases/2026.11.18-r6 --revision 2026.11.18-r6
python -m unittest discover -s converter -p 'test_*phrase*.py'
```

留出样本测试用 `benchmark_phrase_source_examples.py` 的 `--seed 20261119 --exclude-sample 原2000条sample.json`；实际包哈希、抽样种子、排除样本哈希及 DLL 哈希均在各组 manifest 中。
