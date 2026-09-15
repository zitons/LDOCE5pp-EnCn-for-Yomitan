# 本地音频数据库（Hoshi Reader）

给 [Hoshi Reader](https://github.com/HuangAntimony/Hoshi-Reader-Android) 用的
词头发音库，从同一份 `LDOCE5_V_2-15.mdd` 生成。**与 Yomitan 词典包是两件独立成品。**

## 为什么需要单独做

Yomitan 的 structured-content **没有 audio tag**，所以音频塞不进词典包
（详见 `HANDOVER.md` §9.9）。Hoshi 另有一套**本地音频数据库**机制绕开这个限制：
导入一个 `android.db`，它自己按词条查表取音频。

## 成品

| 文件 | 大小 | 说明 |
|---|---:|---|
| `android.db` | 436.4 MiB | 91,559 条音频、92,544 行索引 |

- **音源**：`ldoce_ame`（美音 46,139 个文件）、`ldoce_bre`（英音 45,428 个）
- **覆盖率**：64,390 个词条中 **46,841 个有发音 = 72.75%**
- **常用词实测**：25/25 全部命中（improve / abandon / child / run / the / water / happy / computer / money / world / year / life / man / woman …）
- 未覆盖的是 `$100/50 cents etc a clip`、`a bad/difficult patch` 这类**模式化短语/词族变体**，原版词典本身没有录音

## 怎么用

Hoshi Reader → `Settings` → `Advanced` → `Audio` → `Local Audio: Enable` →
`Import` → 选 `android.db`。Hoshi 会自动把 `Local` 源排到默认源之前。

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
