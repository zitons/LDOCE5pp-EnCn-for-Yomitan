# 构建效率与代码改进清单

> 生成时间：2026-09-10 · 对象：`converter/ldoce2yomitan.py`（2058 → 2085 行）
> 标注规则：**【实测】** = 我跑出来的数字；**【估算】** = 基于代码结构的推断，待验证。

---

## 0. 现状基线

| 项 | 值 | 来源 |
|---|---|---|
| 上一次全量构建 | **915.7 s（15 分 16 秒）** | `full_build2.log` 【实测】 |
| 本次全量构建（含 head/cn_only 修复） | **约 22 分钟**（14:36 → 预计 15:00） | bank 文件时间戳推算 【实测】 |
| CPU 核数 | **12** | 【实测】 |
| Python | 3.13.5 | 【实测】 |
| 峰值内存 | **1.2 GB** | tasklist 【实测】 |
| 源文本 | 877.5 MB，285,017 条记录 | 【实测】 |
| 词条 HTML 总量 | 约 450 MB（64,659 条 × 平均 7 KB） | 【估算】 |
| 输出未压缩 | 475.1 MB / 25 个 bank | 【实测】 |

**结论：本次修复让构建慢了约 40%**（15.3 → 22 分钟）。原因是 `render_head()` 的芯片路径对每个未识别子元素改为走完整的 `_children_blocks()` 递归渲染，而不是原来一次廉价的 `get_text()`。

---

## 1. 时间花在哪（按代码结构定位）

| 阶段 | 现状 | 根本问题 |
|---|---|---|
| **Pass B 渲染** | 主耗时，约 17 分钟 | `BeautifulSoup(content, "html.parser")`（**纯 Python 解析器**）啃 450 MB HTML，实测吞吐只有 1–3 MB/s；且每次 `classes_of()` 都新建一个 `frozenset` |
| **校验 `validate_package`** | 2–4 分钟 | 每个 bank **`json.loads` 两次**（:1716-1722 收集表达式、:1725-1726 逐行查），475 MB 被解压+反序列化两遍 |
| **压缩** | 1–2 分钟 | `compresslevel=6` 单线程 deflate 475 MB，12 核只用 1 核 |
| **Pass A + count_lines** | 1–2 分钟 | 877 MB 文本被**完整读 3 遍**（`count_lines`、Pass A、Pass B） |
| **bank 落盘** | 含在上面 | `save_bank()` 写 65 MB 文件 → `zf.write()` 再读回来压缩，475 MB 写了又读 |

---

## 2. 改进项（按性价比排序）

### P0 — 高收益、低风险

#### 2.1 解析器换 `lxml`　【实测 1.3–1.5×，改 1 行】✅ 已实施

```python
soup = BeautifulSoup(content, HTML_PARSER)   # "lxml"，原为 "html.parser"
```

**⚠️ 我最初的估算是错的。** 我曾按 lxml 自身的解析吞吐（20–60 MB/s）推断有 5–10× 提速。实测：

| 场景 | html.parser | lxml | 加速 |
|---|---|---|---|
| 纯解析（54.4 MB / 2,158 条） | 48.88 s（1.11 MB/s） | 37.72 s（1.44 MB/s） | **1.3×** |
| 完整渲染（解析+遍历+序列化） | 54.74 s（0.99 MB/s） | 36.86 s（1.48 MB/s） | **1.5×** |

**为什么差这么多**：真正的瓶颈不是 HTML 解析，而是 **bs4 把 lxml 的树逐个包装成 Python 的 `Tag`/`NavigableString` 对象**——54 MB 里就有 48 万个元素，这一层纯 Python 的对象构造把 lxml 的 C 速度优势吃掉了。换解析器绕不开这层。

**等价性已验证**（`converter/audit7_parser_equiv.py`）：1,747 条分层样本（含最大 120 条、最小 120 条、1,500 随机）用两个解析器渲染，**逐字节完全一致**（差异 0 行、各自 0 异常、序列化总字节数完全相同）。所以这一行改动是安全的。

- 依赖：`lxml` **不在 PyPI 可达范围**（沙箱挡了 pypi.org 与清华镜像），本次是从同版本 Python（3.13.5）的 conda 环境复制 `lxml 6.1.1`（`cp313-win_amd64.pyd`，ABI 一致）到项目 venv。**换机器重建时要重新装 `lxml`**，否则 import 失败。

#### 2.2 校验器每个 bank 只解析一次　【预期省 1–2 分钟，约 10 行】

当前两遍解析的**唯一原因**是：pass 2 要知道"全部表达式的集合"，而这个集合要等所有 bank 都扫完才有。但**构建器本来就知道这个集合**（`rendered_keys` ∪ 别名 key ∪ 全部 alias word）。把它传进去即可：

```python
def validate_package(zip_path, term_index, revision, mode, full_rows=True, known_exprs=None):
    ...
    # 单遍：边解析边校验；known_exprs 作为 dangling 判据
```
顺带把 `zf.read(bank)` 从两次降到一次（475 MB 少解压一遍）。

#### 2.3 去掉多余的 `count_lines()`　【预期省 10–20 秒，3 行】

`n_lines = count_lines(input_path)`（:1787）只用来给 tqdm 一个 `total`，代价是**完整读一遍 877 MB**。Pass A 结束后已经有精确记录数，直接把它喂给 Pass B 的 tqdm 即可：

```python
est_records = max(n_lines // 2, 1)   # Pass A 用估算
...
est_records = seat_a_records          # Pass B 用精确值（去掉 count_lines）
```

#### 2.4 删掉 `render_record()` 里多余的 h1 清扫　【预期省几秒，2 行】

```python
for h1 in soup.find_all("h1"):     # 全树扫描，64,659 次
    h1.decompose()
```
`render_element()`（:586）和 `_has_block_child()` 都已经把 `h1` 处理成空，这次全树扫描纯属冗余，可直接删。

#### 2.5 `save_bank()` 直接流式写进 zip　【预期省一次 475 MB 落盘 + 回读，约 10 行】

```python
def save_bank(rows, idx):
    with zf.open(f"term_bank_{idx}.json", "w") as handle:   # 直接进 zip
        json.dump(sanitize_strings(rows), handle, ...)
```
省掉"写 65 MB 临时文件 → 再读回来压缩"，同时消掉 25 个中间文件（也顺手消掉 `--keep-json` 的删除逻辑）。

#### 2.6 `sanitize_strings()` 改成就地清理　【预期省 0.5–1.5 分钟，约 12 行】

`save_bank()` 里 `sanitize_strings(rows)` 会把整棵结构**深拷贝重建一遍**（每 bank 数百万个 dict/list）。但绝大多数字符串里根本没有不可见字符。就地版本可以只替换命中项、复用原容器：

```python
def sanitize_inplace(value):
    if isinstance(value, str):  return strip_invisible(value)
    if isinstance(value, list):
        for i, v in enumerate(value): value[i] = sanitize_inplace(v)
        return value
    if isinstance(value, dict):
        for k in value: value[k] = sanitize_inplace(value[k])
        return value
    return value
```
语义完全等价（`rows` 写完即弃），但省掉全部容器分配与峰值内存翻倍。

#### 2.7 调整 GC 阈值（**不是**关闭 GC）　【预期省 10–30%，2 行】✅ 已实施

构建过程有上亿个短命对象，`gc` 的分代扫描是开销。但——

**⚠️ 我最初建议的 `gc.disable()` 是错的、危险的**：BeautifulSoup 的树里每个节点都持有父节点引用，**构成引用环**，只有循环回收器才能释放。关掉 GC 意味着 64,659 棵解析树全部滞留，内存会一路涨到几个 GB。我原文写的"本项目无循环引用大户"是错的，特此更正。

安全做法是抬高阈值（减少扫描次数，但仍会回收）：

```python
gc_threshold = gc.get_threshold()
gc.set_threshold(50000, 100, 100)   # build() 开头
...
gc.set_threshold(*gc_threshold)     # build() 结尾恢复
```

### P1 — 收益大、需要重构

#### 2.8 Pass B 多进程并行　【预期 6–8×，12 核；约 80–120 行】

Pass B 是**逐记录独立**的（渲染 → 得到行），天然可并行。设计：

1. 先扫一遍源文件，记下每条记录的行号区间；
2. 按 `</>` 边界把 285,017 条记录切成 N 份（N ≈ 核数）；
3. `ProcessPoolExecutor` 分发；**每个 worker 需要 `TermIndex`** —— 父进程把索引 pickle 到临时文件，worker 用 initializer 加载（避免 Windows spawn 下重复传输）；
4. worker 返回 `(rows, key_rules, rendered_keys)`；
5. 主进程按分片顺序拼接、**统一分配 `sequence`**（保证可复现、连续），再生成别名行。

预期：Pass B 从 17 分钟 → **2–3 分钟**。

⚠️ 风险与验证：`sequence` 必须与单进程结果一致；`unknown_classes` 统计要合并；内存需限制在每 worker 1 个 bank（worker 自己落盘到临时文件比返回大对象更稳）。

#### 2.9 Pass A 索引落盘缓存　【迭代时每次省 1–2 分钟；约 15 行】

```python
cache = source + f".index-{os.path.getsize(source)}-{int(os.path.getmtime(source))}.pkl"
```
按（路径, 大小, mtime）缓存 `TermIndex` + `alias_rows`。**开发迭代时最痛的就是每次改渲染逻辑都要重跑 1–2 分钟的 Pass A**（我写 audit3 时每次都不得不重放，深有体会）。换源文件时缓存自动失效。

### P2 — 微优化

| 项 | 位置 | 收益 |
|---|---|---|
| `classes_of()` 结果缓存（按元素 `id()`） | 17 个调用点 | 每元素省 2–3 次 `frozenset` 分配 |
| `_has_block_child()` 结果复用 | :605 与 :1206 对同一元素算两遍 | 省一次全子元素扫描 |
| `CHIP_PRIORITY` / `INLINE_MAP` 线性扫描改集合求交 | `render_inline_node` | 每元素最多 85 次 set 查询 → 2 次集合运算 |
| 两个 `extract_tags` 正则合并为一次 `finditer` | :1546-1548 | 少扫一遍 450 MB |
| 压缩级别 6 → 1~3（或对各 bank 并行 `zlib.compress`） | :1977 | 压缩段 2–3×，体积 +5–10% |
| 本次 head 修复加"纯文本子元素"快速路径 | 新增的芯片分支 | 收回本次引入的约 40% 开销 |

---

## 3. 预期效果汇总

| 方案 | 全量耗时 | 改动量 | 风险 |
|---|---|---|---|
| 现状（head 修复后、未优化） | **约 22 分钟**【实测】 | — | — |
| P0（2.1–2.7） | **约 11–13 分钟**【估算】 | ~50 行 | 低 |
| P0 + 2.8 并行 Pass B | **4–6 分钟**【估算】 | ~150 行 | 中 |

**本轮的估算依据已修正**：lxml 实测只有 1.5×（不是 5–10×），所以 P0 的收益主要来自
① lxml 1.5×、② 校验器单遍解析、③ 去掉多余的整文件扫描、④ 就地 sanitize、⑤ bank 直写 zip。

**要真正压到 4–6 分钟，必须做 2.8 并行 Pass B。** 因为瓶颈已经被定位得很清楚：
bs4 的 Python 对象构造（约 1.5 MB/s，450 MB → 5 分钟起）+ 单核绑定。

---

## 4. 本轮已实施的改动

| # | 改动 | 位置 |
|---|---|---|
| 1 | 解析器 `html.parser` → `lxml`（新增 `HTML_PARSER` 常量） | 文件头 + `render_record` |
| 2 | 校验器单遍解析（新增 `known_exprs` 参数） | `validate_package` |
| 3 | 内嵌 **seq 唯一性/连续性**检查（原先只有 L2 审计才查） | `validate_package` |
| 4 | 删除多余的 `count_lines()` 全文件扫描 | `build()` Pass A |
| 5 | GC 阈值 50000/100/100（**非** disable） | `build()` |
| 6 | `sanitize_inplace()` 就地清理，取代 `sanitize_strings()` 深拷贝 | 新增 + `save_bank` |
| 7 | bank **流式直写 zip**，写到 `*.part` 后原子改名 | `build()` |
| 8 | 删除 `render_record()` 里多余的 `find_all("h1")` 全树扫描 | `render_record` |
| 9 | head 芯片加"纯文本子元素"快速路径（收回本次修复引入的开销） | `render_head` |
| 10 | `AUTHOR` 改纯 ASCII（修正 mono 包含中文） | 文件头 |
| 11 | `PROJECT_URL` 从无关的 OALD10 仓库改为数据来源论坛 | 文件头 |
| 12 | mono 的 `description` 不再包含中文 | `build()` |
| 13 | 死代码：删 `add_class()`、简化 `merge_adjacent_text()` 恒真/恒假分支、删 `render_div()` 两处重复死分支 | 多处 |

---

## 4. 建议的执行顺序

1. **先完成当前构建的正确性验证**（audit4 结构 / audit5 词头 / audit6 新旧对比）——性能优化绝不能盖在未验证的正确性改动上；
2. 装 `lxml`，跑 5,000 条**解析器等价性**检查；
3. 实施 P0（2.1–2.7），用同一脚本计时对比；
4. P0 通过后，再评估是否值得上 2.8 并行；
5. 顺手把 REVIEW.md 里那些**低风险待办**一起塞进同一次构建，避免多跑几轮 15 分钟：
   - D2 mono 元数据去中文（`AUTHOR` / `desc_bits` 按 mode 切换）
   - D3 `index.json` 的 `url` 指向修正
   - §4 补强：把 seq 唯一性/连续性检查内嵌进 L1 校验器
   - §3 的 13 项死代码清理（`add_class`、`TermIndex.rendered`、`current_key`、`render_div` 的 6 行不可达分支、`INLINE_MAP` 的 cn_txt 死条目等）
   - `part1.py` / `part2.py` 改名 `*_STALE`
   - README/HANDOVER 的三处数字订正

**注意**：第 5 步把"正确性小修"和"性能优化"混在同一次构建里，会让出问题时不好归因。建议顺序是 **P0 性能改动先单独验证一轮**（用 audit3 的 45 行逐字节复现做门禁），确认行内容零变化后，再把第 5 步的小修一起打进去。
