## 本地音频数据库（词头发音）

给 [Hoshi Reader](https://github.com/HuangAntimony/Hoshi-Reader-Android) 使用的
`android.db`。**与同仓库的 Yomitan 词典包是两件独立成品**，词典包不需要装它。

| 文件 | 大小 | 内容 |
|---|---:|---|
| `android.db` | 436.4 MiB | 91,559 条音频 / 92,544 行索引 |

### 内容

- **音源**：`ldoce_ame`（美音，46,139 个文件）、`ldoce_bre`（英音，45,428 个）
  —— 每个词条英美发音各一份，可在 Hoshi 里分别试听
- **覆盖率**：词典包 64,390 个词条中 **46,841 个有发音（72.75%）**
- **常用词抽验**：25/25 全部命中
  （improve / abandon / child / run / the / water / happy / computer / money / world / year / life / man / woman …）
- **未覆盖的 27.25%**：`$100/50 cents etc a clip`、`a bad/difficult/sticky patch`
  这类**模式化短语与词族变体** —— 原版 LDOCE5++ 本身就没有为它们录音，不是提取遗漏

### 安装

Hoshi Reader → `Settings` → `Advanced` → `Audio` → `Local Audio: Enable` →
`Import` → 选择 `android.db`。

Hoshi 会自动添加 `Local` 音源并把它排在默认源之前。

> 参考：官方那套 `android.db` 约 5.79 GB（日语，含多个音源）。
> 本库 436 MiB，只含 LDOCE5++ 的词头发音。

### 格式依据

表结构取自 Hoshi 的 Kotlin 源码（`features/audio/LocalAudioRepository.kt`、
`LocalAudioResolver.kt`、`AudioSettings.kt`）以及
[yomidevs/local-audio-yomichan](https://github.com/yomidevs/local-audio-yomichan)
的 `plugin/db_utils.py`，不是推测：

```sql
CREATE TABLE entries (id, expression, reading, source, speaker, display, file);
CREATE TABLE android (id, file, source, data);   -- data = 音频 blob
```

三条硬约束（读源码所得）：

1. 文件必须叫 **`android.db`**（导入校验只认 `.db`）
2. `file` 只能以 **`.mp3` / `.opus` / `.ogg`** 结尾，否则 Hoshi 发现不了该音源
3. `reading` **故意留空** —— Hoshi 在 reading 为空时走 `WHERE expression = ?`
   精确匹配分支；填假读音反而会引入错误匹配

### 验证

生成器与审计脚本在同仓库 `converter/`，可独立复跑：

```bash
python converter/build_audio_db.py --out yomitan_audio/android.db
python converter/audit_audio_db.py --db yomitan_audio/android.db
```

审计结果（exit 0）：

```
integrity_check          ok
孤儿 entries / blobs     0 / 0      （双向对称）
blob 抽样 4,000 个       0 个损坏   （全部 ID3 或 MPEG 帧同步）
重复行                   0
db 内 expression         全部属于词典，无多余
查询延迟                 0.063 ms   （Hoshi 每次查词的耗时）
```

### ⚠️ 边界

- **未做真机 Hoshi 导入验收**。格式依据是源码 + 本地以 SQL 复现 Hoshi 的查询逻辑，
  尚未在 Android 设备上实际导入播放。
- 未含例句音频（`exaProns`，86,450 个）—— 本库只做词头发音。
- 未含 `.spx`（1,842 个）—— Hoshi 不支持该格式。
- 音频版权归 **Pearson Education Limited**，与词典本体一致，仅供私有研究使用。
