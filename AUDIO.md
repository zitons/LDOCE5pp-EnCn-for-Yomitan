# 本地音频数据库（Hoshi Reader）

给 [Hoshi Reader](https://github.com/HuangAntimony/Hoshi-Reader-Android) 用的
发音库。**与 Yomitan 词典包是两件独立成品。**

有三个版本：**单源版**（只用 LDOCE5 词头发音）、**合并版**（再并入第三方 OALD10
音频）、**TLD 版**（The Little Dict 全量，含 spx→opus 转码）。

## 为什么需要单独做

Yomitan 的 structured-content **没有 audio tag**，所以音频塞不进词典包
（详见 `HANDOVER.md` §9.9）。Hoshi 另有一套**本地音频数据库**机制绕开这个限制：
导入一个 `android.db`，它自己按词条查表取音频。

## TLD 版（The Little Dict）

### 它是什么

`The little dict/TLD.mdx` + 7 个 `.mdd`，作者 GaryPang，英英词典，3.8 GB 媒体文件。
**与 LDOCE5 无关**，是独立的英语词条覆盖。

### 为什么值得做

| | 英语词条覆盖 |
|---|---:|
| 现有合并版 | 71,260 |
| **+ TLD** | **310,918** |
| | **+239,658（4.36 倍）** |

TLD 有音频的词条绝大部分是 LDOCE 里**不存在的词**，所以对"扩大整个英语词条覆盖"
价值很大；但如果只问"提升 LDOCE 自己词头的覆盖率"，答案是没有（+0.57 pp），
因为 LDOCE 缺音频的 17,275 个词头里 17,116 个是短语词条，任何词典都不给配发音。

### 三个必须先知道的事实

**① 82% 是 `.spx`，Hoshi 不能播。** 824,116 个音频文件里 669,505 个是 Speex。
Hoshi 只接受 `.mp3`/`.opus`/`.ogg`，所以必须转码。

**② mdict-utils 读不了这些 .mdd。** 报
`zlib.error: invalid stored block lengths`。这不是文件加密 —— 手工按正确偏移解，
6,407/6,423 个块是纯 zlib（compression=2, encryption=0），TLD.1.mdd 第一块就解出
合法 MP3（`ff f3` 帧头）。mdict-utils 是把记录块 info 列表当成块读了。
所以 `build_tld_audio_db.py` 自己解析布局。

**③ 键名大多不可读，词条映射必须来自 MDX。** `4015093.spx`、`COLmp300002.spx`
这种 opaque ID 占 570,280 个。唯一权威映射是 MDX 条目自己引用的
`<audio src="...">` —— 靠猜键名会把 `p028-000001320.mp3` 剥成假词 `p028-`。

### 转码码率：为什么是 opus 16k

实测 TLD spx 的有效码率是 **13–15 kbps**。重新编码只要码率**不低于源**，就不可能
再丢信息（信息在第一次编码时就定死了）。

| 码率 | 相对 spx 体积 | 判断 |
|---|---|---|
| opus 8k | 58% | 低于源 → 确定丢 |
| opus 12k | 88% | 低于源 → 丢一些 |
| **opus 16k** | **~104%** | **≥ 源 → 不丢** |
| mp3 96k | ~314% | 远大于源，纯浪费 |

Speex 和 Opus 同属语音优先编解码器，效率接近；mp3 是通用音乐编解码器，对语音
效率差一大截（同内容 mp3 96k 是 spx 的 3 倍以上）。

### 7 个 source 标签

一个 `.mdd` 一个标签，因为它们是**不同词典**，不是英美音对立：

| .mdd | source | 内容 |
|---|---|---|
| `TLD.1.mdd` | `tld_ame` | `ameProns\*.mp3` 美音 |
| `TLD.2.mdd` | `tld_uk` | `media\english\uk_pron\*` 英音 |
| `TLD.3.mdd` | `tld_collins` | `COLmp3*.spx` 柯林斯发音库 |
| `TLD.4.mdd` | `tld_mw` | `mw_*.spx` |
| `TLD.5.mdd` | `tld_ids` | 纯数字 ID |
| `TLD.6.mdd` | `tld_uk2` | `uk_pron\ca2uk*.mp3` 第二套英音 |
| `TLD.mdd` | `tld_snd` | `snd*.spx` |

`speaker`/`display`/`reading` 全写 **NULL**，与合并版里 LDOCE 行的约定一致；
不标 `UK`/`US`，因为这 7 个不是英美音对立，硬标会误导。

### 构建

```bash
python converter/build_tld_audio_db.py --out yomitan_audio/tld.db
# 断点续跑：--from TLD.3.mdd
# 单文件冒烟测试：--only TLD.4.mdd --limit 3000
# 不转码（调试）：--keep-spx
```

依赖 `imageio-ffmpeg`（自带静态 ffmpeg，含 libspeex 解码 + libopus 编码，
不需要系统装 ffmpeg）。

### 三个性能要点

1. **批量转码**：一次 ffmpeg 进程处理整块（~24 个文件）。逐文件转码 94% 的时间
   耗在 Windows 进程启动上（~50 ms/次），824k 文件要 20 小时；批量后 **2.5 小时**。
2. **键区间用二分**：每块都遍历全部 154,737 个键是 O(块×键) ≈ 10 亿次迭代，
   改成 `bisect` 后常数级。
3. **MDX 索引缓存**：解析 4.36 M 条记录要 60–90 秒，pickle 缓存后二次运行命中。

### 已知问题

- **16/6,423 个块解不开**（TLD.1.mdd 的 block 1553 起），损失约 0.5% 音频。
  布局校验过（最后一块结束位置 == 文件大小），不是偏移漂移，是数据本身有问题。
- **30,041 个重复 `(source, file)`**：同一文件被多个词条引用，blob 存了多份，
  浪费约 120 MB。不影响功能（Hoshi 按 `file` 查）。
- **未做真机验证**：db 格式与契约逐项验过，但没在 Hoshi 里实际导入播放。

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
  --zip "yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip" \
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
