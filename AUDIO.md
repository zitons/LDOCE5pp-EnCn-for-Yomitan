# 本地音频数据库（Hoshi Reader）

给 [Hoshi Reader](https://github.com/HuangAntimony/Hoshi-Reader-Android) 用的
发音库。**与 Yomitan 词典包是两件独立成品。**

有两个版本：**单源版**（只用 LDOCE5 词头发音）与**合并版**（再并入第三方 OALD10 音频）。

## 为什么需要单独做

Yomitan 的 structured-content **没有 audio tag**，所以音频塞不进词典包
（详见 `HANDOVER.md` §9.9）。Hoshi 另有一套**本地音频数据库**机制绕开这个限制：
导入一个 `android.db`，它自己按词条查表取音频。

## 成品

### 合并版（推荐）

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

### 单源版

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
`Import` → 选 `android.db`（或 `android_merged.db`）。
Hoshi 会自动把 `Local` 源排到默认源之前。

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

## 重建

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

## 合并多个音频库

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

## TLD 音频库（The little dict）

第三份成品：`yomitan_audio/tld.db`，把 The little dict 的 7 个媒体包 + ODE 2024
并成一个库，给 LDOCE 覆盖不到的词做补充（合并顺序见本节末尾）。
构建器 `converter/build_tld_audio_db.py`（TLD 七源）+ `converter/build_ode_audio.py`（ODE）。

现状：**1,065,161 行 / 340,320 词条 / 5.07 GB**，`entries` 行序即优先级，
`android` 与 `entries` 一一对应（0 孤立行）。

### 为什么是 7 个音源

词典只有一份 `TLD.mdx`，音频却分散在 7 个 `.mdd` 里，每个包是一个**独立来源**：

| .mdd | source | 文件数 | 格式 | 内容 |
|---|---|---:|---|---|
| `TLD.1.mdd` | `tld_ame` | 95,615 | mp3 | `/ameProns/*` 美音 |
| `TLD.2.mdd` | `tld_uk` | 152,154 | spx | `media/english/uk_pron/*` 英音 |
| `TLD.3.mdd` | `tld_collins` | 101,727 | spx | `COLmp3*` 柯林斯 |
| `TLD.4.mdd` | `tld_mw` | 154,737 | spx | `mw_*` |
| `TLD.5.mdd` | `tld_ids` | 118,174 | spx | 纯数字 ID |
| `TLD.6.mdd` | `tld_uk2` | 78,879 | mp3 | `uk_pron/ca2uk*` 第二套英音 |
| `TLD.mdd` | `tld_snd` | 149,212 | spx | `snd*` |

不能并成一个 `tld` 标签：`android` 的主键语义是 `(source, file)`，而 **TLD.1 与 TLD.6
有 8,753 个同名文件**（同一个词的美音版和英音版都叫 `xxx.mp3`）。合成一个 source
会让它们互相覆盖，Hoshi 不报错，但播出来的声音是错的。

`.spx`（Speex）不入库原样，先转 Opus——Hoshi 只发现 `.mp3/.opus/.ogg`。

### 构建

```bash
# 单个源（调试用）
python converter/build_tld_audio_db.py --only TLD.1.mdd --out yomitan_audio/tld.db
# 全部 7 个
python converter/build_tld_audio_db.py --out yomitan_audio/tld.db
# spx 转码需要 ffmpeg；没装 imageio-ffmpeg 时用 --ffmpeg 直接给路径
```

参数：`--only <mdd>` 只处理一个包、`--limit N` 前 N 条、`--ffmpeg PATH`、`--tld DIR`、
`--missing-only`（只补库里还没有的文件）、`--blacklist PATH`（默认 `converter/bad_clips.tsv`）。
产物是**追加写入**已有库的，逐源重灌前先 `delete from entries/android where source=?`。

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

当前已知错配：**5 条**已确认并删除（`tld_uk2` 的 `four` 英/美两条、`tld_ame` 的
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
        → tld_mw → tld_ids → tld_snd → tld_uk2
```

`tld_uk2` 垫底：它 87,551 条只贡献 2,291 个别处没有的词，却是唯一一个有
"录音≠词头"实证的源（见上）。

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
  尚未在 Android 设备上实际导入播放。
- 未做 `.spx`（1,842 个）—— Hoshi 不支持，转码会引入额外依赖且收益 <1%。
- 未做例句音频（`exaProns`，86,450 个）—— 按要求只做词头发音。
- 音频版权归 **Pearson Education Limited**，同词典本体，仅供私有研究使用。
