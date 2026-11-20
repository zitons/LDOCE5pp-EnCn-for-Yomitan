# 本地音频数据库（Hoshi Reader）

给 [Hoshi Reader](https://github.com/HuangAntimony/Hoshi-Reader-Android) 用的
发音库。**与 Yomitan 词典包是两件独立成品。**

当前成品只有一份：**`yomitan_audio/tld.db`**（2026-11-18 重建，6 个源）。
更早的两版（LDOCE 单源版、LDOCE+OALD 合并版）留在文件里作历史参考。

## 为什么需要单独做

Yomitan 的 structured-content **没有 audio tag**，所以音频塞不进词典包
（详见 `HANDOVER.md` §9.9）。Hoshi 另有一套**本地音频数据库**机制绕开这个限制：
导入一个 `android.db`，它自己按词条查表取音频。

## 当前成品（2026-11-18 重建）

| 文件 | 大小 | 内容 |
|---|---:|---|
| `yomitan_audio/tld.db` | **3.01 GiB** | 819,439 行 / 809,089 条音频 / **221,641 个词头** / 6 个源 |

整个库只有 **6 个源，全部逐词录音**，没有任何一个是从连续朗读里切出来的：

| source | 内容 | 行数 | 音频文件 | 体积 | 中位时长 | 串烧率 |
|---|---|---:|---:|---:|---:|---:|
| `webster` | 韦氏 | 223,337 | 222,389 | 807 MB | 1.04 s | 0.7% |
| `lpd3` | 朗文发音词典 3 版 | 135,575 | 134,551 | 435 MB | 1.02 s | **0.1%** |
| `cepd18` | 剑桥英语发音词典 18 版 | 120,948 | 119,320 | 386 MB | 0.97 s | **0.0%** |
| `vocab` | Vocabulary.com | 84,796 | 82,973 | 316 MB | 1.26 s | 1.1% |
| `collins` | 柯林斯 | 71,416 | 66,489 | 200 MB | 1.26 s | 1.2% |
| `ode2024` | 牛津 ODE 2024 | 183,367 | 183,367 | 258 MB | 1.08 s | **0.02%** |

前五个源来自同一个包 **5 in 1 English Pronunciation Dictionary**（281,569 词条，
`Sound.mdd` 3.0 GB / 735,715 个 `.spx`），包内已经按词典分节标注，所以按词典拆成
5 个 source，而不是并成一个 —— Hoshi 的音源选择器因此能分别试听、单独禁用。

`speaker` 列的口音来源：`ode2024` 是词典自带字段；5in1 的英美靠路径
（`uk_pron/` / `us_pron/`）与文件名（`_Uk` 后缀、`uk_` 前缀）；**`collins` 在包内
只有一个喇叭、没有任何口音标记，所以 `speaker` 留 NULL，不猜**。

### 为什么换掉 TLD 七包

2026-11-11 ~ 15 那版（见下文「历史」）用的是 The Little Dict 的 7 个包。实测下来
它们**同源同病**：都是拿词典方的连续朗读素材按文件名切块，切点卡在词头、结尾不管，
于是 0.3%–1.73% 的音频会「一个词读一长串」（`ideally` 那条 16.33 秒，读了 17 个
相邻词头；`convokes` 9.86 秒读 7 个）。而且这批缺陷**在 mdd 原始数据里就有**，
不是构建脚本引入的 —— 从 `TLD.1.mdd` 里取出的 `\ameProns\ideally.mp3` 与库内副本
逐字节相同（md5 `65d0b48c…`）。

5 in 1 的听感和体检都更好：

| 指标 | TLD 七包 | 5 in 1 |
|---|---|---|
| 串烧率（各源加权） | 0.3%–1.73% | **0.0%–1.2%** |
| 最长单条 | 33.29 s（`tld_mw`） | 9.43 s |
| 采样率 | 统一 16 k（spx） | 11k / 16k / 22k / 32k / 44.1k |
| 英美标记 | 靠文件名猜 | 包内分节 + `_Uk` / `uk_` 前缀 |
| 词头覆盖 | 301,559 | 221,641 |

代价是**丢 77,572 个词头**：`tld_snd`（Vocabulary.com）那 51,201 个化学名/缩写
（`19-nortestosterone`、`2,4-D`、`A1c`）、`tld_uk` 那 18,103 个**屈折形式**
（`abandoning`、`abandons`）。换来的是常用词全部有 5–6 条跨词典录音，且没有串烧。

### 构建

```bash
# 1) 灌 5in1 五个源（单 writer 架构，见脚本 docstring）
python converter/build_five1_audio2.py --apply --workers 6

# 2) 重建精简库：只留 6 个源，只建 Hoshi 真正用到的两个索引
python converter/rebuild_compact.py --apply
```

第 1 步 **66 分钟**跑完 627,091 条音频（缺的 189 个是包里本来就没有的 Vocabulary
数字编号）；第 2 步 **49 秒**完成（`INSERT..SELECT` 到新库 + 索引最后建 + 关日志，
不走 DELETE+VACUUM）。

## 历史成品（LDOCE 单源 / 合并版，2026-09）

> ⚠️ 下面两份是 2026-09 的产物，已被 `tld.db` 取代；文件仍在
> `yomitan_audio/` 下，仅供回退参考。

### 合并版（2026-09，已废弃）


| 文件 | 大小 | 说明 |
|---|---:|---|
| `android_merged.db` | 1611.0 MiB | 214,273 条音频、216,862 行索引，**3 个音源** |

```
sha256  47ba6517515abaa6c3a4ee7561f0e2c5db5f3190de6c09e8a4dc054184dcd5a6
bytes   1,689,235,456
```

| 音源 | 来源 | 说明 |
|---|---|---|
| `ldoce_ame` | LDOCE5++ | 美音 |
| `ldoce_bre` | LDOCE5++ | 英音 |
| `oald10` | 第三方 OALD10 音频库 | 牛津高阶 10；UK/US 由 `speaker` 区分 |

- **覆盖率**：64,390 个词条中 **47,074 个有发音 = 73.11%**
  （比单源版略高，OALD10 补了少数 LDOCE5 没有的词）
- Hoshi 的**音源选择器会列出三条**，可分别试听、单独禁用
- 换词条查词时按 `source` 字母序取第一个命中的：`ldoce_ame` → `ldoce_bre` → `oald10`

### 单源版（2026-09，已废弃）

| 文件 | 大小 | 说明 |
|---|---:|---|
| `android.db` | 436.4 MiB | 91,559 条音频、92,544 行索引 |

```
sha256  45f1b31062eb7c929cd33abe7e24ace40e6f2b802bb2d822498e31eb69da8ca1
bytes   457,568,256
```

- **音源**：`ldoce_ame`（美音 46,135 个文件）、`ldoce_bre`（英音 45,424 个）
- **覆盖率**：**46,841 / 64,390 = 72.75%**
- **常用词实测**：25/25 全部命中（improve / abandon / child / run / the / water / happy / computer / money / world / year / life / man / woman …）
- 未覆盖的是 `$100/50 cents etc a clip`、`a bad/difficult patch` 这类**模式化短语/词族变体**，原版词典本身没有录音

## 怎么用

Hoshi Reader → `Settings` → `Advanced` → `Audio` → `Local Audio: Enable` →
`Import` → 选 **`yomitan_audio/tld.db`**。
Hoshi 会自动把 `Local` 源排到默认源之前。

导入后建议先查这几个词试听（每个词都有 6 个源的录音可选）：`apple`、`schedule`、
`four`、`tomato`、`improve`。

## 数据库格式

依据 Hoshi 的 Kotlin 源码（`features/audio/LocalAudioRepository.kt`）与
`yomidevs/local-audio-yomichan` 的 `plugin/db_utils.py`：

```sql
CREATE TABLE entries (          -- Hoshi: findAudio()
    id integer PRIMARY KEY,
    expression text NOT NULL,   -- 查询键：WHERE expression = ?
    reading text,               -- 本词典无读音，留 NULL
    source text NOT NULL,       -- ldoce_ame / ldoce_bre
    speaker text,
    display text,
    file text NOT NULL          -- 必须是 .mp3/.opus/.ogg，否则 Hoshi 不认
);
CREATE TABLE android (          -- Hoshi: loadAudio()
    id integer PRIMARY KEY,
    file text NOT NULL,
    source text NOT NULL,
    data blob NOT NULL          -- 原始音频字节
);
```

几个**必须遵守的点**（都是读源码得来的，不是猜的）：

1. **文件名必须是 `android.db`** —— `AudioSettings.LocalAudioPath = "Audio/android.db"`，
   导入校验只认 `.db` 扩展名。
2. **`file` 只能是 `.mp3` / `.opus` / `.ogg`** —— Hoshi 用
   `lower(file) LIKE '%.mp3' OR '%.opus' OR '%.ogg'` 发现音源。本库的 `.spx` 因此跳过。
3. **`reading` 留空是有意的** —— Hoshi 在 `reading` 为空时走 `WHERE expression = ?`
   分支，正是我们要的精确匹配。若填假读音反而会引入错误匹配。
4. **`entries` 的每一行都必须能在 `android` 里取到 blob** —— 否则 Hoshi 匹配成功却播不出声。
   生成器对此有硬断言（`assert orphan == 0`）。
5. **索引只需要两个** —— `expr_idx(expression)` 与 `file_idx(android.file)`，正好对应
   Hoshi 的 `WHERE expression = ?` 和 `WHERE file = ?`。旧库还挂着 `src_idx`、
   `idx_entries_expr_read`、`idx_android_file_source` 三个用不上的索引，白占
   300–400 MB（`entries` 141 万行、`android` 140 万行，每个索引都要存一遍键）。
   `rebuild_compact.py` 只建前两个。

## 重建（LDOCE 单源版，历史）

```bash
# 依赖：mdict-utils（.mdd 读取）、Python 3.11+
python converter/build_audio_db.py \
  --mdd "LDOCE5_V_2-15.mdd" \
  --src "extract/LDOCE5++ V 2-15.mdx.txt" \
  --zip "yomitan_full/LDOCE5pp_Yomitan_2026.10.03.zip" \
  --out "yomitan_audio/android.db"
```

`--limit N` 只取前 N 个词条，用于抽样验证管线。

独立审计（不 import 生成器，从外部核实产物）：

```bash
python converter/audit_audio_db.py --db yomitan_audio/android.db
```

覆盖了：schema 列名、`integrity_check`、双向孤儿、Hoshi 的音源发现查询、
blob 是否真是音频（ID3/MPEG 帧同步/OggS）、重复行、与词典包的覆盖率、查询延迟。

> ### ✅ `build_audio_db.py` / `audit_audio_db.py` 的遗留已修复（2026-09-15 晚）
>
> 上面"评估后决定暂不修"的三条，当晚经用户拍板全部修掉，**并全量重建验证**：
>
> 1. **校验晚于发布** → 已改为与合并器同款：校验私有 `.part`（integrity_check +
>    双向孤儿），失败删 `.part` 拒绝发布，通过才 rename。
> 2. **孤儿检查只有单向** → `ent−blob` 与 `blob−ent` 都进判据。
> 3. **`<out>.part` 清理** → 改为**两条守卫，且都按"同一文件身份"判定**
>    （`os.path.samefile`，一侧不存在时回退规范化比较），不再用 `abspath` 字符串
>    比较 —— Windows 上 `Src.MDD` / `src.mdd` 是同一个文件，字符串比较抓不到，
>    symlink 与硬链接同理。两条是：
>    1. `<out>.part` 不得是某个输入 —— 它会被**无条件删除**；
>    2. **`--out` 本身也不得是某个输入** —— 读完之后 `os.replace(tmp, out_path)`
>       会把它**覆盖掉**，而且因为是先读后写，全程不会报任何错。
>
> 另修（审查同批）：**HWD 文本改为深度感知提取**（原 `(.*?)</span>` 在 51% 的
> 词头上被嵌套 `HYP` 中点截断）；`--limit` 死参数清除；`audio_in` 的 re.I 大小写
> 崩溃风险；`head_region` 的 `idx > 0` 边角。`audit_audio_db.py` 同步升级：
> blob 载荷检查从"按 rowid 前 4000 条"（merged 库的 1.9%）改为**逐条前 16 字节**、
> 接受 `OggS`（否则将来接 ogg 源会假 FAIL）、`blob−ent` 死重也计入 FAIL、
> 连接改为 `mode=ro` 并先查文件存在；`data` 为 NULL 时（库可读、但列上没有
> `NOT NULL` 约束）按**非法载荷**计入 FAIL，而不是让 `ln >= 100` 抛 `TypeError`
> 把整个审计打崩。
>
> **重建结果：产物逐字节不变。** 重跑生成器得到与记录完全相同的
> `android.db`（sha256 `45f1b310…`、92,544 行 / 91,559 blobs、457,568,256 B），
> 与旧代码产物 0 表达式换文件——HWD 完整文本与 key 形式高度重合，原截断
> 在真实数据上从未造成漏收或错配（截断形式总含 `·`，不可能命中表达式）。
> 因此 `android_merged.db` 无需重做，两个已记录哈希继续有效。
>
> 过程教训（HANDOVER 坑 67 详述）：第一版深度感知提取把"切到匹配闭合"写成了
> "从最后一个内层闭合之后切"，产出词头**后缀**（`car·rot`→`rot`），后缀形式
> 抢占 `variants` 后把 2,091 个表达式配到了别的词条的音频——靠"新旧库逐表达式
> 对比文件分配"抓出，而只比较匹配/不匹配集合的探针对此完全盲目。

## 合并多个音频库（历史用法，当前成品用不上）

```bash
python converter/merge_audio_db.py \
  --db "yomitan_audio/android.db" \
  --db "local_audio_1783304412795.db" \
  --out "yomitan_audio/android_merged.db"
```

`--db` 可重复，**每个输入都被原样追加**（包括第一个）。

> 输出**始终使用本脚本的固定 schema 与索引**，不会沿用任何输入的 schema 或索引。
> 若输入库有自定义 schema/索引，它们不会被保留。

**硬门禁**（任一不满足即中止，且不产出文件）：

1. **`--out` 不得与任何 `--db` 相同** —— 否则合并结果会覆盖那个输入库本身
   （实测：把 436 MB 的双源库同时当输入和输出，它被 1.6 GB 的合并库取代，原文件丢失）
2. **同一个 `--db` 不得传两次** —— 自合并会让每个 `(source, file)` 重复，
   破坏 `android` 表赖以定位音频的唯一性
3. **输入之间不得有 `(source, file)` 碰撞** —— `android` 以该组合为键，
   碰撞会让一个源静默盖住另一个
4. **列名必须齐全** —— 缺列若留到 INSERT 才报错，`.part` 已经写了一半

合并完成后、**发布之前**校验：`integrity_check`、**双向**孤儿（`entries` 无 blob
与 `android` 无引用都算）、`(source,file)` 唯一性。任一项不过就删除 `.part`
并拒绝发布，保留上一份可用产物。

### 两库的英美音编码方式不同（合并时保持原样）

| 库 | 英美区分方式 |
|---|---|
| LDOCE5（本项目生成） | `source='ldoce_ame'` / `'ldoce_bre'`，`speaker=NULL` |
| OALD10（第三方） | `source='oald10'` 单一源，`speaker='UK'` / `'US'` |

合并**不改动第三方行的任何字段**，所以其它读 `source`/`speaker` 的消费者
（如 AnkiConnect Android）不受影响。Hoshi 按 `source` 分源，因此它的音源列表
会出现三条：`ldoce_ame`、`ldoce_bre`、`oald10`。

### 孤立行的处理

两个输入都有「`entries` 有行但 `android` 无 blob」的记录
（LDOCE5 8 行；**OALD10 有 661 行，去重后是 654 个 `(source,file)` 对** ——
7 个对各自覆盖 2 行），合并时**丢弃**。
留着会让 Hoshi 匹配成功却播不出声、且不报错。

合并器对**双向**孤儿都有断言：`entries` 无 blob（索引指向空）、
`android` 无 entries（无人引用的死负载）都必须为 0。

实测合并结果：

```
blobs    91,559 + 122,714 = 214,273  →  214,273        （一条不差）
entries  92,544 + 124,979 = 217,523  →  216,862        （差 661 行）
         丢弃的孤儿：654 个 (source,file) 对，覆盖 661 行
逐字节   三音源各抽样 40 个 blob 与原始库比对：byte-differ 0，not-found 0
```

## TLD 音频库（The little dict）—— 历史，已被 5 in 1 取代

> ⚠️ 本节记录 2026-11-11 ~ 15 的 TLD 七包方案。**2026-11-18 起已整体废弃**：
> 库里只剩 `ode2024` + 5in1 五个源。保留本节是因为下面这些坑（错误匹配、
> 区块录音、chained 逻辑流、文件名不可校验）换任何源都可能再遇到。


第三份成品：`yomitan_audio/tld.db`，把 The little dict 的 7 个媒体包 + ODE 2024
并成一个库，给 LDOCE 覆盖不到的词做补充（合并顺序见本节末尾）。
构建器 `converter/build_tld_audio_db.py`（TLD 七源）+ `converter/build_ode_audio.py`（ODE）。

现状：**778,478 行 / 301,559 词条 / 4.73 GB 文件**。2026-11-11 两轮清理后只剩
5 个源在库（`tld_uk2` 整源删、`tld_ids` 整源筛掉、`tld_collins` 只留三分之一）。
`entries` 行序即优先级，`android` 无被遗弃的 BLOB。

### 现在库里是哪 5 个源

词典只有一份 `TLD.mdx`，音频却分散在 7 个 `.mdd` 里。2026-11-11 按
「文件名能不能对上词头」筛过一轮，7 个包里只剩 5 个还有内容：

| .mdd | source | 现存行 | 原文件数 | 处理 |
|---|---|---:|---:|---|
| `TLD.1.mdd` | `tld_ame` | 108,191 | 95,615 | 逐行筛，删 15,262 |
| `TLD.2.mdd` | `tld_uk` | 152,070 | 152,154 | 全留（100% 可校验） |
| `TLD.3.mdd` | `tld_collins` | 34,751 | 101,727 | 逐行筛，删 64,857 |
| `TLD.4.mdd` | `tld_mw` | 153,943 | 154,737 | 全留（100% 可校验） |
| ~~`TLD.5.mdd`~~ | ~~`tld_ids`~~ | ~~0~~ | ~~118,174~~ | **整源筛掉：0% 可校验** |
| ~~`TLD.6.mdd`~~ | ~~`tld_uk2`~~ | ~~0~~ | ~~78,879~~ | **整源删（体检垫底）** |
| `TLD.mdd` | `tld_snd` | 146,156 | 149,212 | 全留（100% 可校验） |
| — | `ode2024` | 183,367 | — | 全留（100% 可校验，带 UK/US） |

不能并成一个 `tld` 标签：`android` 的主键语义是 `(source, file)`，而 **TLD.1 与 TLD.6
有 8,753 个同名文件**（同一个词的美音版和英音版都叫 `xxx.mp3`）。合成一个 source
会让它们互相覆盖，Hoshi 不报错，但播出来的声音是错的。

`.spx`（Speex）不入库原样，先转 Opus——Hoshi 只发现 `.mp3/.opus/.ogg`。

### 构建

```bash
# 单个源（调试用）
python converter/build_tld_audio_db.py --only TLD.1.mdd --out yomitan_audio/tld.db
# 全部 6 个（TLD.6 已在 MDD_SOURCES 里注释掉，不在其中）
python converter/build_tld_audio_db.py --out yomitan_audio/tld.db
# spx 转码需要 ffmpeg；没装 imageio-ffmpeg 时用 --ffmpeg 直接给路径
```

参数：`--only <mdd>` 只处理一个包、`--limit N` 前 N 条、`--ffmpeg PATH`、`--tld DIR`、
`--missing-only`（只补库里还没有的文件）、`--blacklist PATH`（默认 `converter/bad_clips.tsv`）。
产物是**追加写入**已有库的，逐源重灌前先 `delete from entries/android where source=?`。

**重建完整流程（顺序不能换）**：

```bash
python converter/build_tld_audio_db.py --out yomitan_audio/tld.db   # 灌 TLD 六包
python converter/build_ode_audio.py --ode "..."                     # 追加 ode2024
python converter/keep_verified.py --apply      # 只留能确认的行（先空跑看数）
python converter/prune_blobs.py  --apply       # 清掉失去引用的 BLOB
python converter/reorder_entries.py            # 行序 = 优先级（最后跑）
```

`keep_verified.py` 会把整源可校验率 < 99% 的源逐行筛，所以**每次重建都必须跑**，
否则 `tld_ids` 那 11 万条纯编号录音会被灌回来。

### ODE 2024（第八个源，单独构建器）

`converter/build_ode_audio.py` 读 `C:\baidunetdiskdownload\ODE now opus\2024`（Oxford
ODE 的 opus 包），写入 `ode2024` 源。它和 TLD 没有关系，只是**同一个库里的另一个源**，
所以 `apply_blacklist.py` / `reorder_entries.py` 对它一样生效。

```bash
python converter/build_ode_audio.py --ode "C:/baidunetdiskdownload/ODE now opus/2024" \
       --out yomitan_audio/tld.db
```

两条要点：

- **只收「音频词干 == 词条自身词头」的引用**。ODE 的条目页会顺带列出邻近词的音频
  （`four` 页面里带 `four_by_four` 的发音），不筛就会把别的词的音挂到自己头上 ——
  这跟上面 `four` 的错误是同一个坑。
- 键的形态是 `<词>_<条目号>_<gb|us>_<n>`，**条目号经常省略**（`improve_gb_1` 与
  `3d_printer_1_gb_1` 并存）。只认省略形式会少一半（61,971 → 93,590）。
- mdx 里用下划线代空格（`four_by_four`），TLD 用空格（`four by four`）—— 多词条在
  阅读器里会查不中，22,771 个表达式受影响，**尚未处理**。

码率很低（opus 48 kHz，约 11 kbps，1.26 KB/条），体积小是这个原因，不是音质好。

### 两道门禁（都是被 bug 逼出来的）

1. **音频头**：入库前与转码后都校验 `OggS` / `ID3` / `0xFFEx` / `RIFF`，
   不合格计数并在结束时非零即 `SystemExit`。
2. **时长**：`|源时长 − Opus 时长| ≤ 0.12 + 5%·源时长`，不过就**复核**（见下），
   复核仍不符才丢弃并计入 `duration-gate rejects`。

> 只用第一道是不够的：接错的音频同样是合法 Opus（见 `HANDOVER.md` 2026.10.23 节）。

时长门禁本身也踩过一个坑，值得记下来：源侧时长不能用「最后一张 Ogg 页的 granule」
来算。有些Collins / snd 条目把「单词 + 几个例句」串成了**多条 chained 逻辑流**，
最后一页的 granule 只覆盖最后一条链，比如 9.9 秒的音频只报 1.2 秒——于是门禁把
**3,149 个完好的文件判成错配丢掉**（1.0%）。现在改成：

- 首选**按 Ogg 段表数包**：每包 `frames_per_packet × frame_size` 个采样，按各链自己的
  `rate` 折算，再减掉每条链的头部包；实测与解码时长偏差 ≤ 2%，远小于 12% 容差。
- 仍不符时**解码复核**：`ffmpeg -i <src> -f null -` 读实际解码时长，与 Opus 时长对比。
  只有解码也对不上才丢。复核只对极少数候选跑一次，不影响吞吐。

### 验收

```bash
# 每源抽 200 条：mp3 比字节、opus 比包络相关，并与「下一条记录」对照
python _tmp/accept.py
# 走 Hoshi 的真实查询逻辑，看能不能取到可解码的 blob
python converter/validate_audio_db.py --db yomitan_audio/tld.db --words "improve,abandon,ocelot"
```

判据：mp3 源要 **byte-exact 200/200**；opus 源要 **corr_own ≥ 0.8**（实测 0.980 起），
且明显高于 `corr_nxt`（0.48–0.69 才是正常值——若两者接近，说明音频整体错位）。
只查 magic 无法发现「声音是别人的」。

`_tmp/fast_audit.py` 里的 `Mdd` 类可以按文件名**只解压所属的那一个块**取记录，
比整包遍历快两个数量级，写新的抽检脚本时直接用。

### 已知损失

全部 7 个源重灌 + 补齐后，行数与修前完全一致（881,796），**没有因为门禁丢音频**。

| 项 | 数量 | 原因 |
|---|---:|---|
| TLD.1.mdd 坏块 | 17 块 / 219 键（0.23%） | mdd 本身数据损坏，非切片问题 |
| mdd 有文件、mdx 无对应词 | 9,023（逐源见下） | 词缀表、裸 ID、未被引用的录音，本来就不该入库 |

逐源缺口（mdd 去重文件名 − 库内文件名）：ame 718、uk 85、collins 3,560、mw 795、
ids 334、uk2 474、snd 3,057。抽样检查过，这些文件能解码，只是 `TLD.mdx` 里没有词条
引用它们（`_ance_suf`、`a0028000`、`COLmp3en_us_*` 这类）。

### 错配音频（录音内容 ≠ 词头）

有一类问题**任何结构校验都抓不到**：mdd 记录完好、mdx 引用完好、解码零错误，
但录音本身念的是别的词。典型是 `four` 播成 "Four by four."：

- `TLD.6.mdd` 的 `ukl30144.mp3` / `usl30139.mp3` 录音内容是 **"Four by four."**
- `TLD.mdx` 的 `four` 条目却把这两条挂成自己的 cuk/cus 音源
- 相邻记录没有错位：`ukl30143.mp3` 确实是 `foundation course`，`ukl30145` 也正常
  → 不是整表偏移，是**单条数据标错**（打包时按"前缀最像"回填，`four by four`
  比别的候选更像 `four`）

处理方式：**人工/ASR 确认后进黑名单**，不猜、不做模糊匹配修正。

```bash
# 1) 找候选（不给结论，只给清单）
python converter/clip_audit.py            # -> _tmp/clip_audit.tsv
python converter/clip_audit.py --sample 40 # 随机导 40 条供试听/ASR

# 2) 把确认的写进 converter/bad_clips.tsv（TAB 分隔：source/file/expression/原因）

# 3) 从现有库删（幂等，可反复跑）
python converter/apply_blacklist.py --dry-run
python converter/apply_blacklist.py
```

`build_tld_audio_db.py` 也读同一份 `bad_clips.tsv`（`--blacklist` 可改路径），
**重灌时自动跳过**，不会复活。

`clip_audit.py` 只能给两类线索，都需要人听：`shared`（一个文件被多个不相关词头
共用，至少一条错）、`prefix`（stem 与词头在词边界上互相为前缀，如 `for` → `four`、
`air` → `air_ambulance`）。打包时 stem 被截断到 14 字符、以及 `bling bling` 这类
叠词都会误报，脚本里已按这两条豁免。

当前已知错配：**5 条**已确认并删除（`tld_uk2` 的 `four` 英/美两条——该源现已整源
移除，这两条记录留作档案、`apply_blacklist.py` 对它们已是空操作；`tld_ame` 的
`cache` ← "Cachet."、`tld_collins` 的 `grandad` ← "Granddaddy."、`tld_collins` 的
`tout` ← "Two."），全部在 `bad_clips.tsv` 里留了 ASR 依据。同音词共用一条录音
（`for` / `fore` / `four` 在 Collins 里同音）不算错配，保留。

**221 条静态候选已逐类核过，绝大多数是误报**（分堆脚本 `_tmp/classify_audit.py`）：

| 类别 | 条数 | 定性 |
|---|---:|---|
| 短语词条，录音就是整句 | 75 | **误报**。ASR 实测 `ld41communication_.mp3` = "Communication cord."、`ld5_mickey_mouse_.mp3` = "The Mickey Mouse club."，文件名只是截断 |
| Collins 同音异形共用 | ~100 | **设计如此**。实测 `COLmp3en_us_moral_2.opus` = "Morale."，挂 `morale` 正确 |
| 一文件挂多个读音不同的词条 | ~35 | 至少一条必错，本轮由此抓出 `tout` |

全库「一个文件被多个词条引用」共 **3,268 组 / 6,975 行**：

- **同音异形 2,367 组**（`air|ere|err|heir`、`bi|buy|by|bye`、`carat|carrot|karat`）——
  Collins 与 LDOCE 的音频按**发音**组织，同音词共用一条录音，不是错配。
- **单词与短语混用 698 组**，其中 948 条是短语词条：词条 `bird louse`，录音只有
  `louse`（实测 `L0388600.opus` = "louse"、`T0358300.opus` = "ton"）。这属于
  **录音不完整**（听到的是词条的基础词），不是错到别的词，保留不删。
- 真正「文件名词干严格长于词条」的只有 **9 条**。除已删的 `cache` / `grandad`，
  其余是 `cyclic` ← cyclical、`hoot` ← hoots、`surtitle` ← surtitles 这类只差后缀的。

结论：静态线索只能**缩小范围**，不能当结论。`prefix` 规则会把文件名下划线切碎的
情况也报出来（`tld_uk` 那 24 条 `blankety blank` ← `blank` 全是这一类）。逐条听过的
结论记在 `converter/asr_findings.tsv`（OK / PARTIAL / UNSURE / FAIL 四档）。

### 合并顺序

Hoshi 对一个词只取**一条**命中行 —— 取到哪条取决于它遍历 `entries` 的顺序，
可能是行序（rowid），也可能是 `source` 字母序，两者并不保证一致。所以行序必须
显式等于优先级：

```bash
python converter/reorder_entries.py --dry-run   # 只报告
python converter/reorder_entries.py             # 重写 entries（android 不动）
```

优先级（`reorder_entries.py` 的 `PRIORITY`）：

```
ode2024 → ldoce_ame → ldoce_bre → oald10 → tld_uk → tld_ame → tld_collins
        → tld_mw → tld_ids → tld_snd
```

`tld_uk2` 原本垫底，现已整源删除，理由见下一节。

### 砍源决策（2026-11-11）

判据只有三条：**真实播放占比**、**独占词条**、**能不能自校验**。体积和码率单独看会
误判（uk2 码率最高 65 kbps，反而最没用）。

| 源 | 首选播放 | 独占词条 | 占用 | 文件名可自校验 | KB/词条 |
|---|---:|---:|---:|---:|---:|
| `ode2024` | 27.7% | 36,974 | 258 MB | 100% | 2.8 |
| `tld_mw` | 24.4% | 40,990 | 370 MB | 100% | 2.5 |
| `tld_snd` | 20.7% | 70,030 | 838 MB | 100% | 5.9 |
| `tld_uk` | 11.7% | 8,950 | 630 MB | 100% | 9.0 |
| `tld_ids` | 6.8% | 20,922 | 248 MB | 0% | 2.3 |
| `tld_collins` | 5.1% | 15,029 | 402 MB | 39% | 6.5 |
| `tld_ame` | 3.6% | 5,223 | 496 MB | 89% | 11.0 |
| ~~`tld_uk2`~~ | ~~0.7%~~ | ~~2,291~~ | ~~649 MB~~ | ~~30%~~ | ~~28.7~~ |

`tld_uk2` 三项全垫底：只负责 0.7% 的播放，独占 2,291 条（全库 338,029 的 0.68%），
却吃 649 MB；70% 的文件名是 `ukl30144.mp3` 这种纯编号，错位无法被结构校验发现——
`four` ← "Four by four." 就是这么漏进来的；同一条录音还按 65 kbps 存 mp3，体积是同
内容 opus 的五六倍。

处置：`DELETE FROM entries/android WHERE source='tld_uk2'`，分批 2,000 行提交
（`_tmp/drop_source.py`），**不 VACUUM**——页会被标空闲、后续写入复用，但文件不缩小。
代价是 2,291 个词条（其中 672 个单字，如 `Blairite`、`BFPO`、`Aga saga`）从此没有
音频，这是事先确认过的取舍。

**没动其他源的理由**：`tld_ids` 文件名 0% 可校验，但独占 20,922 条、扛 6.8% 播放，
砍了比留着更疼；`tld_ame` 是第二差的，可它的独占里是 `AT&T`、`Aeroflot`、
`Abbottabad` 这类专有名词，496 MB 换这些还算值。

体检里还有一个反直觉的结果：**「一个词读好几个词」不是某个源的系统性问题**。
每源随机抽 12 个单词词条量时长，中位数全在 0.85–1.41 s，最长 2.19 s，没有一条
超过 3 s。真正的长尾个例来自 `_tmp/long_clips.tsv`（同源内体积 > 3 倍中位数的
4,260 条），只能逐条听，不能按源定罪。

### 第二轮：只留「能确认读的是什么」的行（2026-11-11）

用户口径：**文件名能对上词头（完全了解），或者带英美标记的，留下；其余删。**

规则（`converter/keep_verified.py`）：

1. 整源可校验率 ≥ 99% 的源全留 —— `ode2024` / `tld_mw` / `tld_snd` / `tld_uk`。
   这几个源里有几百条缩写、连字符、短语因为检查太死没过，删了是误伤，所以整源豁免。
2. 其余源逐行判，满足任一即留：
   - 文件名归一化后含词头前 5 字符（短词要求整词出现）
   - `speaker` 非空
   - 文件名带 `gb` / `us` / `uk` / `ame` / `bre` / `en_gb` / `en_us` 标记

结果：

| 源 | 原行 | 删 | 留 |
|---|---:|---:|---:|
| `tld_ids` | 119,012 | 119,012 | **0** |
| `tld_collins` | 99,608 | 64,857 | 34,751 |
| `tld_ame` | 123,453 | 15,262 | 108,191 |
| 其余四源 | 635,536 | 0 | 635,536 |

合计删 **199,131 行**，36,470 个词条（10.8%，其中单字 20,950）彻底没音。失音的大头
是 `tld_ids` 那批古语与缩写（`'cept`、`'nuff`、`'sblood`、`Abbasside`）。

随后清掉因此变成孤儿的 BLOB：**198,920 条 / 575 MB**（`converter/prune_blobs.py`）。
清洗后 778,478 行 / 301,559 词条 / 4.73 GB。被删的三元组留档在
`_tmp/dropped_rows.tsv`，失音词条清单在 `_tmp/dead_expressions.txt`。

**注意这里踩的坑**：孤儿统计写成 `android left join entries` 会退化成对每一行
android 扫一遍 entries（entries 没有 `(file,source)` 索引），10 分钟都跑不完。
正确写法是从 entries 取 live 集合，再用 `indexed by idx_android_file_source`
扫覆盖索引（只含 file/source/rowid，不碰 BLOB 页），秒级完成。

### 尚未处理：同文件名多份 BLOB

`android` 里同一 `(source,file)` 存了多份不同的录音，点名 `tld_ame`：

- `tld_ame` 30,615 条重复、`tld_collins` 880 条，其余源 0
- 例：`tld_ame/ld45four.mp3` 同时有 1,728 B 和 2,299 B 两份
- 成因仍是 `basename()`：不同目录下的同名文件（`/ameProns/four.mp3` 与别处的
  `four.mp3`）进了同一个 key，播哪份取决于查询先返回哪行——**不确定**

没动，因为无法判断哪份才是对的。

### 区块录音：一个词读一长串（2026-11-15）

`tld_mw` / `tld_snd` 里混着一批「区块录音」：一个单词的音频里，先读自己，接着
不停顿地读十几个相邻词头。实测 `cap` 是 `"Cap, cap. off, cap opener, cap screw
capability. Capable. capableness. capably, capacious..."`，`boot` 是
`"Boot, boot. bootable boot black."`。

关键在于**第一句永远是这个词本身**（而且常读两遍），所以不用删，剪掉后面的就行。

**候选**（1,536 条）：跨源比体积 + 时长，条件 `est_sec >= 2.5 + 0.06 × 词长`，
并排除 `ode2024`（它那 19 条全是 `pneumonoultramicroscopic...` 这类超长词，
3.86 秒本来就是正常时长）。

**两轮剪法**：

| 轮次 | 判据 | 结果 |
|---|---|---|
| 第一轮 | `silencedetect -35 dB / 0.2 s`，第一个静音点 +0.1 s，上限 3.2 s | 剪 1,517 条 |
| 第二轮 | 对仍 >2.0 s 的短词（无空格、≤10 字符），阈值放宽到 -30 dB / 0.12 s，**从原始备份重剪** | 改 112 条，跳过 28 条 |

**回退策略**（比剪得准更重要）：找不到静音点就**不切**，原样保留。实测这类多半
不是区块录音，而是逐字母读的缩写（`XSCID`、`NTIS`、`DCCP`）、缩写念完整词组
（`EBITDA` → `"Earnings before interest, taxes, depreciation and amortization"`）
或单纯的长词，盲切会把尾音砍断。第一轮曾按 2.5 s 硬切，已把这 19 条全部回退。
第二轮另加词长下限（`0.055 × len + 0.35`），切点早于下限就不切。

**最终实测**（1,536 条逐条 ffmpeg 量，不是按字节估）：

| 区间 | 条数 |
|---|---|
| < 1 s | 617 |
| 1–2 s | 756 |
| 2–3 s | 83 |
| 3–4 s | 72 |
| > 4 s | 8（全是回退项，保持原样） |

中位 **1.07 s**，p90 2.06 s，p99 3.21 s。残余 96 条 >2.5 s，集中在 `tld_mw`
（`boot` 这类词与词之间没有静音，靠能量检测切不开；再往下切就开始断字，停在这里）。

**原始音频备份**在 `_tmp/trim_backup/`（923 + 613 份，47 MB），可单条还原；
日志 `_tmp/trimmed.tsv` / `_tmp/trim2.tsv`。

脚本：`converter/trim_block_clips.py`（第一轮）、
`converter/trim_block_clips_pass2.py`（第二轮）。两个都必须**先写备份再 update**，
日志逐条 flush —— 上一版把结果攒在内存里，被中断后 923 条改动没有任何记录。

## 音频是怎么定位的

源 HTML 里音频挂在两种元素上，**两条都要认**（只认一条会丢 16 个百分点）：

```html
<a class="speaker amefile fa fa-volume-up" href="sound://media/english/ameProns/improve.mp3">
<a class="speaker brefile fa fa-volume-up" href="sound://media/english/breProns/improve0205.mp3">
<a class="PronCodes"                      href="sound://media/english/ameProns/ld5_12.mp3">
```

另外**词头块要按 class token 匹配**，不能用 `class="Head"` 精确匹配 ——
源里有 `class="Head suppressedLEXVAR"`（如 `A1, the`），精确匹配会把它漏掉。

## 边界

- **未做真机 Hoshi 导入验收**：格式依据是源码 + 本地 SQL 复现 Hoshi 的查询逻辑，
  尚未在 Android 设备上实际导入播放（2026-11-18 这版同样没做）。
- 5in1 的音频在包内全是 `.spx`，构建时统一转 **Opus 24 kbps / 48 kHz 单声道**
  （源本身只有 18–30 kbps，转码不降质）。Hoshi 只发现 `.mp3/.opus/.ogg`。
- 未收录 5in1 里的 189 个缺失文件（Vocabulary 数字编号等，包里本来就没有）。
- 未做例句音频，只做词头发音。
- 音频版权归各词典出版方（Merriam-Webster / Cambridge / Pearson / Collins /
  Vocabulary.com / Oxford），同词典本体，仅供私有研究使用。
