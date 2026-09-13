# A1–A6 修复报告（2026-09-12）

对 `REPORT.md` 六项发现的修复、以及每条修复的独立验证。缺陷编号在 `REVIEW.md` 中登记为 D23–D28。

> **注意（2026-09-13 补记）**：本文里的「修复后」包 `LDOCE5pp_Yomitan_2026.09.12.zip`
> （`d63a7ad9…`）**已不在磁盘上**。提交 `fd566aa` 之后，下一轮（提交 `136b65d`/`f120dbb`）
> 用同一个文件名重建过一次，现在 `yomitan_full/` 里的 09.12 包是那一版的 `bc067411…`。
> 因此本文记录的是**当时**的验证结果，`converter/audit_2026_09_12/diff_before_after.py`
> 也已按此标注为 DEPRECATED（它对 09.11 与当下的 09.12 做逐行比对，必然失败）。

## 基线与结果

| | 修复前 | 修复后 |
|---|---|---|
| 转换器 `converter/ldoce2yomitan.py` | `c5519d87…` | `5587b0f2a72089eda27bfb671dd5a8dae83274f9c81ac175e1736e508cece6d4` |
| 交付包 | `LDOCE5pp_Yomitan_2026.09.11.zip` 60,198,033 B `15aaa3b8…` | `LDOCE5pp_Yomitan_2026.09.12.zip` 60,209,514 B `d63a7ad99fcde2131982f5177b27237ec788034aa1c32cdca5d97665e44095f7` |
| 行数 | 245,933（64,659 内容 + 181,274 别名） | 同左，**逐行一致** |
| 全量构建 | — | 807.3 s（机器上当时有并发任务；A3 的提取开销实测 +4.7 ns/char ≈ +4 s） |

包体 +11,481 字节全部来自修复：816 个变形音标块 + 940 条别名规则 + 281 行 tags + 1 条 CSS 规则。

## 修复一览

| 编号 | 缺陷 | 修前 | 修后 |
|---|---|---|---|
| D23 (A1) | 校验失败仍发布，坏包覆盖好包 | 失败后仍打印 `[OK]`、退出码 0、好包被覆盖 | 先校验 `.part`，通过才发布；抛 `BuildValidationError`，CLI 退出码 **2** |
| D24 (A2) | 别名 rules 未按表达式取并集 | **940** / 181,274 条 | **0** |
| D25 (A3) | POS 正则被嵌套标签截断 | **281** 个词条 tags/rules 错误 | **0**（与 DOM 参考逐条一致） |
| D26 (A4) | 变形列表丢掉 PronCodes 文字音标 | **596** 词条 / **816** 发音块 | **0**；609/609 词条补回 |
| D27 (A5) | mono 模式泄漏中文 | **243** 个词条 | **0**（两处成因都修） |
| D28 (A6) | sequence 校验盲点（重复被当合法） | 重复/缺零/断档全部静默通过 | 四类负例全部拒绝 |

## 代码改动

`converter/ldoce2yomitan.py`，+207 / −31 行，集中在六处：

1. **发布门禁**：新增 `BuildValidationError`；`build()` 末尾改为"先校验 `zip_tmp`，通过才 `os.replace`"；失败路径删 `.part`、恢复 GC 阈值、打印 `[FAIL] Nothing published…` 后抛异常；`main()` 捕获后返回 2，`__main__` 改 `sys.exit(main())`。
2. **`key_rules` 保序累积**：`key_rules[k] = " ".join(dict.fromkeys((key_rules.get(k) or "").split() + rules.split()))`。只影响别名继承，内容行自身 rules 不变。
3. **POS 提取**：`POS_SCAN_RE` 改为只匹配开标签；新增 `_span_body()`（深度计数 + `limit` 兜底）、`_drop_portrait_spans()`；`extract_tags()` 改用它并跳过嵌套命中。
4. **变形音标**：`render_inflections()` 新增 `PronCodes`/`PRON`/`AMEVARPRON` 分支，输出 `ld-infl-pron`；`generate_css()` 增加对应规则。
5. **mono 过滤**：新增 `ZH_CLASSES` 常量与 `LdoceRenderer._label_text()`；`render_block_by_token()` 与 `render_box()` 的两处标题改走它；`render_div()` 开头在 mono 下丢弃 `cn_txt`/`cn_txt_ext`。
6. **sequence 校验**：`seqs` 由 set 改 list，判据改为"唯一值数 == 行数 且 min == 0 且 max == 行数 − 1"。

门禁同步：`converter/audit8_head_order.py` 的 in-sequence 忽略列表加入 `ld-infl-pron`（否则新类会被当成顺序错乱）。

## 验证

### 新增的回归脚本（本目录）

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'

venv\Scripts\python.exe -u converter/audit_2026_09_12/regress_gates.py    # D23 + D28，13 项
venv\Scripts\python.exe -u converter/audit_2026_09_12/regress_content.py  # D24–D27 打在新包上
venv\Scripts\python.exe -u converter/audit_2026_09_12/diff_before_after.py # 新旧包逐行比对
```

`regress_gates.py` 用注入式校验失败走完整 `build()` + `main()` 路径（不是 mock 掉发布逻辑）：

```
[OK] A1 failing build raises BuildValidationError
[OK] A1 failing build logged [FAIL]
[OK] A1 failing build never printed [OK] Dictionary package
[SKIP] A1 *.part cleanup: this sandbox blocks file deletion
[OK] A1 previous good package survived, byte-identical
[OK] A1 CLI exits non-zero on validation failure  rc=2
[OK] A1 CLI left the good package untouched
[OK] A1 good build still passes the real validator after the gate ran
[OK] A6 seq_ok.zip: sequences [0, 1, 2] -> accepted
[OK] A6 seq_duplicate.zip: sequences [0, 0, 1] -> rejected
[OK] A6 seq_duplicate_only.zip: sequences [0, 0] -> rejected
[OK] A6 seq_no_zero.zip: sequences [1, 2] -> rejected
[OK] A6 seq_gap.zip: sequences [0, 2] -> rejected
[OK] A6 40 gapless rows accepted
all gates passed
```

> `[SKIP]` 是环境限制而非代码问题：本沙箱拦截文件删除（fail-closed 回收站策略），
> 所以失败路径的 `os.remove(zip_tmp)` 无法生效，脚本改为探测该能力后再决定是否断言。
> 在普通 shell 下该行是 `[OK]`。**是否留下 `*.part` 与发布门禁无关** —— 关键断言是
> "没有发布、上一份好包字节不变、退出码非零"，三条都独立成立。

```
# regress_content.py
[OK] A2 alias rules == union of target rows (was 940)  0 bad
[OK] A3 all 281 reference entries carry reference tags/rules (was 281)  0 bad
      'above'    -> [('adv prep adj S2 W1 W3', 'adv adj')]
      'andante'  -> [('noun adj adv', 'n adj adv')]
      'amen'     -> [('noun', 'n')]
[OK] A4 no source/ZIP head pairing failures  []
[OK] A4 no inflection pronunciation block still missing (was 596 words/816)  0 blocks over 0 words
      entries in the A4 word list that now carry ld-infl-pron: 609 / 609
[OK] A5 mono headings free of CJK (was 243 records)  0 leak
[OK] CSS matches current generate_css()

# diff_before_after.py
[OK] expression / reading / score / sequence identical in every row  0 differ
[OK] every glossary change is a pure insertion of ld-infl-pron  634 ok, 0 structural
[OK] index.json carries only the revision bump  {'revision': ('2026.09.11', '2026.09.12')}
[OK] tag_bank_1.json identical
[OK] styles.css changes are one added rule
rows with tags changed      : 281
rows with rules changed     : 1605
rows with glossary changed  : 634
```

"glossary 变化是纯插入"的判据是：把新包里每一个 `ld-infl-pron` 节点连同它前面的 `·`
分隔符摘掉，再与旧包逐字节比对 —— 634 行全部结构相同。这一条同时证明 D26 **没有**夹带
任何别的渲染改动。

### 既有门禁（全部 exit 0）

| 门禁 | 结果 |
|---|---|
| `audit2_schema.py` | 官方 term-bank-v3 schema：抽样 50,402 行 **0 失败**；序列 0..245932 连续唯一；tag_bank 33 个 tag PASS |
| `audit3_reproduce.py` | 45 行采样 **100% 逐字节复现**；结构扫描：SC key 违规 0、链接目标 63,950 无悬挂、redirect 目标 52,138 无悬挂、CSS 缺类 0 |
| `audit4_structure.py` | 别名/内容行互遮蔽 0；CSS used=111 defined=126 missing=0 |
| `audit5_headword.py` | 词头污染 0 |
| `audit8_head_order.py` | 采样 2,994 词条 / 3,392 个头块：顺序一致 **2,982**、不一致 **0**、块数不符 **0** |
| `audit9_text_conservation.py` | 800 词条采样，未到达输出 3,060 → **3,050**（1.592% → 1.587%），TOP-20 与修前一致，无新增丢失 |
| `targeted_probe.py` | **历史证据，已加注**：其结尾断言的是"缺陷仍存在"，修复后重跑必然失败，故由上面两个 regress 脚本取代 |

### 源端对照（A3 的决定性证据）

`converter/_check_a3_all.py`：对每个被本修复改动的词条，用审计自己的 lxml DOM 参考实现重新提取
POS 并比对 —— **370 条改动词条中，"旧实现 ≠ 参考" 370 条，"新实现 ≠ 参考" 0 条**。
`converter/_check_a3_ref.py` 另外只针对审计的 281 条 findings：旧 281/281 不一致、新 0 不一致。

## 未覆盖 / 残余

- **没有真机导入验收**（Yomitan 扩展 + 真浏览器），这仍是唯一的最终验收缺口。
- **D27 只覆盖 mono**。双语路径有显式分支保证逐字符不变，并由 `audit3` 的逐字节复现佐证。
- 审计提到的其它已知项**未在本轮处理**：4,875 条因源库缺目标的降级链接（结论是不能解决，
  原版同样是死链）、`See picture`（D8，已修）、`ACTIV` 中文对照（源里无对照，按用户要求不加）。
- 构建耗时 807 s 含并发干扰，不是干净基线；A3 提取的净开销按微基准是 +4.7 ns/字符（约 +4 s，
  内容总量约 9.07 亿字符）。若要精确数字需在空载机器上重跑一次。
