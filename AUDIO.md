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
  --zip "yomitan_full/LDOCE5pp_Yomitan_2026.09.13.zip" \
  --out "yomitan_audio/android.db"
```

`--limit N` 只取前 N 个词条，用于抽样验证管线。

独立审计（不 import 生成器，从外部核实产物）：

```bash
python converter/audit_audio_db.py --db yomitan_audio/android.db
```

覆盖了：schema 列名、`integrity_check`、双向孤儿、Hoshi 的音源发现查询、
blob 是否真是音频（ID3/MPEG 帧同步）、重复行、与词典包的覆盖率、查询延迟。

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
