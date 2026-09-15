# LDOCE5pp En-Cn → Yomitan

把《朗文当代高级英语辞典 5++（LDOCE5++ V2.15 En-Cn）》的 MDX/MDD 转成
[Yomitan](https://github.com/yomitan/yomitan) format-3 词典包。

> **开发修复版（2026-09-14）已验收**：空记录发布门禁、5 个词条的断词及 Anki 暗色继承已修复。
> 本地新包在 `yomitan_fixed/2026-09-14-n1-n3/`，详见 [修复与完整验证](converter/audit_2026_09_14/FIXES.md)。
> **尚未更新 Release**：下方 09.13 下载链接及 `yomitan_full/` 旧包不包含这三项新修复。

**已发布成品**（双语 ~61 MB / 纯英文 ~52 MB）——从 Release 下载，不入库
（GitHub 大包推送会在约 19 秒后被链路重置，实测非偶发）：

> **[⬇ 双语 `LDOCE5pp_Yomitan_2026.09.13.zip`](https://github.com/zitons/LDOCE5pp-EnCn-for-Yomitan/releases/download/v2026.09.13/LDOCE5pp_Yomitan_2026.09.13.zip)**
> **[⬇ 纯英文 `LDOCE5pp_Yomitan_2026.09.13_EN.zip`](https://github.com/zitons/LDOCE5pp-EnCn-for-Yomitan/releases/download/v2026.09.13/LDOCE5pp_Yomitan_2026.09.13_EN.zip)**
> 全部版本见 [Releases](https://github.com/zitons/LDOCE5pp-EnCn-for-Yomitan/releases)。

| | |
|---|---|
| 行数 | **245,933** = 64,659 条内容行（64,390 个不同词头，其中 269 个词头有两条内容行）+ 181,274 条别名重定向行（双语与纯英文同） |
| 语言 | 双语（英文释义 + 中文翻译/搭配中文）；纯英文版（`_EN`）零 CJK |
| 词头 | 音标（含英美差异与重音标记）、●●● 核心词等级（悬停提示）、S/W 频次徽标、词性、语法框、词形变化 |
| 词条内链接 | 1,949,979 条活链，**零悬挂**；4,875 条因源库缺目标而降级 |
| 频率元数据 | `term_meta_bank`，可在 Yomitan 里**按词频排序** |
| 排版 | 主题自适应（跟随 Yomitan 的明暗主题，不跟操作系统） |
| **无样式表可用** | 义项用原生 `<ol><li>`、例句用嵌套 `<ul><li>` —— **Anki 制卡/纯 HTML 导出等没有样式表的环境下仍有列表层级与缩进**；编号和例句标记以内文保留，不依赖 CSS |

## 安装

Yomitan → `Dictionaries` → `Load zip` → 选下载到的 zip。

> ⚠️ **尚未做真机导入验收**（见下文「说明」）。所有验证是"结构合法 + 能被 Yomitan
> 真生成器渲染成 DOM"，不等于扩展 UI 内交互全部正确。

## 词头发音（Hoshi Reader，另一件成品）

Yomitan 的 structured-content **没有 audio 标签**，音频无法塞进词典包。
[**Hoshi Reader**](https://github.com/HuangAntimony/Hoshi-Reader-Android)（Android/iOS）
有自己的**本地音频数据库**机制，因此发音以**独立成品**交付：

| 文件 | 大小 | 内容 |
|---|---:|---|
| `android.db` | 436.4 MiB | 91,559 条音频 / 92,544 行索引 |

- **音源**：`ldoce_ame`（美音）、`ldoce_bre`（英音）—— 每个词条英美发音各一份
- **覆盖率**：64,390 个词条中 **46,841 个有发音（72.75%）**；常用词抽验 **25/25 命中**
- 未覆盖的是 `$100/50 cents etc a clip` 这类**模式化短语**，原版词典本身没有录音

安装：Hoshi Reader → `Settings` → `Advanced` → `Audio` → `Local Audio: Enable` →
`Import` → 选 `android.db`。

生成与验证脚本在 `converter/`（`build_audio_db.py` / `audit_audio_db.py` /
`validate_audio_db.py`），细节见 [`AUDIO.md`](AUDIO.md)。

## 无 CSS 环境（Anki 制卡等）

导出的卡片若不带词典样式表，本包仍保有结构，这是**刻意设计**：义项是 `<ol><li>`、
例句是嵌套 `<ul><li>`，浏览器保留列表层级和默认缩进；编号使用词典自身的**源编号**，
例句标记以内文保留。两种模式都关闭 UA 自动编号，避免义项 `7、8、9、10` 被重编为 `1、2、3、4`。
色彩以行内样式兜底（中文绿、词性蓝、字段绿粗）。

加载样式表后，CSS 提供绿色编号芯片、例句伪元素和紧凑的悬挂缩进；无样式表时，源编号和
内嵌标记仍然可见。两种环境都有验证脚本：

```bash
python converter/regress_render_contract.py <package.zip>   # 真 Chrome 双模式
python converter/regress_inline_vs_css.py   <package.zip>   # 行内兜底与类规则等值
python converter/regress_list_validity.py   <package.zip>   # 列表嵌套合法（孤儿 li = 0）
```

## 仓库内容

本仓库只放**源码、文档与审计脚本**，词典包走 Release 附件 —— 试过直接 `git push`
60 MB 的单次请求，无论直连还是经代理，都会在约 19 秒后被链路重置
（`curl 55 Send failure: Connection was reset`），故改用 Release 附件的上传端点
（`uploads.github.com`），一次通过。

## 重建

```bash
# 依赖：Python 3.11+、beautifulsoup4、lxml、tqdm、mdict-utils
python converter/ldoce2yomitan.py \
  -i "extract/LDOCE5++ V 2-15.mdx.txt" \
  -o yomitan_full -m bilingual --revision 2026.09.14-review-fixes

# 纯英文（源里 cn_txt 全剥；校验器强制全 bank 零 CJK）
python converter/ldoce2yomitan.py \
  -i "extract/LDOCE5++ V 2-15.mdx.txt" \
  -o yomitan_full -m mono --revision 2026.09.14-review-fixes
```

源数据（`.mdx` / `.mdd` / 解包文本）**不入库**：体积过大且受版权保护。
自己准备时用 `mdict-utils` 解包 `.mdx`，并把 `LDOCE5pp_config.ini` 一类的
同目录文件放好。约 15 分钟一趟（单进程）。

调试构建（只渲染指定词、JSON 带缩进，便于目检）：

```bash
python converter/ldoce2yomitan.py -i "extract/LDOCE5++ V 2-15.mdx.txt" \
  -o yomitan_debug -m bilingual --test-words "improve,the,child" --keep-json
```

## 文档

| 文件 | 内容 |
|---|---|
| [`HANDOVER.md`](HANDOVER.md) | **接手先读这个**。项目全景、Yomitan format-3 契约速查、70 条踩坑清单（多数跳过必返工）、内容守恒验证方法、Hoshi 音频库附录 |
| [`REVIEW.md`](REVIEW.md) | 独立审查报告：D0–D41 + N1–N3 逐条缺陷、影响面量化、复现命令、已排除的怀疑 |
| [`AUDIO.md`](AUDIO.md) | **Hoshi 本地音频库**：使用、db 格式（读源码所得的三条硬约束）、重建、边界 |
| [`TYPOGRAPHY.md`](TYPOGRAPHY.md) | 排版/CSS 层审查（T1–T8），含"原版 CSS 用不了"的原因 |
| [`IMPROVEMENTS.md`](IMPROVEMENTS.md) | 性能改进清单与实测数据 |
| [`README-yomitan.md`](README-yomitan.md) | 成品说明与审计链 |

## 验证

审计脚本在 `converter/`，全部可独立复跑（**刻意不复用转换器自带的校验器**）：

| 脚本 | 作用 | 最近一次结果 |
|---|---|---|
| `audit2_schema.py` | 官方 JSON Schema（index / tag / term / **term_meta**） | term-bank 抽样 50,402 行 failures **0** |
| `audit3_reproduce.py` | 重渲染抽样行与交付 zip **逐字节**比对 | **45/45 一致，0 差异** |
| `audit4_structure.py` | 独立结构扫描（seq、SC 契约、链接/重定向悬挂、CSS 覆盖） | 违规 `NONE`、悬挂 **0**、CSS `missing=[]` |
| `audit5_headword.py` | 词头污染门禁 | **0 (0.00%)** |
| `audit8_head_order.py` | 词头顺序 vs 源 DOM（逐 head 块配对） | 不一致 **0** / 数量不符 **0** |
| `audit9_text_conservation.py` | 逐词条文本守恒（找"悄悄丢内容"） | 缺口 1.74%，全部为有意取舍 |
| `regress_list_validity.py` | 列表嵌套合法（孤儿 `<li>`、列表内非法子节点） | 836,768 个 `<li>` **零孤儿** |
| `regress_head_separation.py` | 无 CSS 时芯片不得粘连（真 Chrome） | 样本 **0 粘连** |
| `regress_inline_vs_css.py` | 行内兜底在有 CSS 时必须是 no-op | 22 条声明全部等值 |
| `regress_render_contract.py` | 真 Chrome 渲染契约（主题色 / 源编号 / 标记） | **PASS** |
| `regress_review_followup.py` | 发布门禁与文本处理的 14 组单元回归 | **14/14 OK** |
| `audit_2026_09_14/regress_new_findings.py` | 空记录门禁、词内接缝及正反例 | **14/14 OK** |
| `audit_2026_09_14/official_schema.mjs` | 实际 Yomitan AJV 全量校验 | 新双语/mono 全部 **491,866 行通过** |
| `audit_subsequence_loss.py` | 内容守恒：剥空白后旧文本须为新文本有序子序列 | **245,664 词条 0 损失** |
| `build_audio_db.py` | Hoshi 音频库生成（扫源 HTML → 建两表 → 从 mdd 抽 blob） | 92,544 行 / 91,559 条音频 |
| `audit_audio_db.py` | 音频库独立审计（schema、integrity、双向孤儿、blob 真伪、覆盖率、延迟） | **exit 0**，孤儿 **0/0** |
| `validate_audio_db.py` | 复现 Hoshi 的 SQL 与排序 rank 逐词验证 | **25/25 词命中** |

内置校验器（每次构建自动跑）：`rows=245933 dangling=0 seq_ok=1`，且
**渲染异常或空记录都会中止发布**（连 `--skip-validation` 也拦）。

## 目录

```
converter/                   转换器与全部审计脚本（唯一事实来源：ldoce2yomitan.py）
yomitan_full/                构建输出（入库的只有 index/styles/tag_bank；zip 见 Release）
yomitan_fixed/               各轮修复的验证包（按日期分目录）
yomitan_audio/               Hoshi 音频库输出（android.db，不入库，走 Release）
mdd_assets/                  从 .mdd 取出的原版 LM5style.css 等（用于排版核对）
scgen_test/                  Node+jsdom 里跑 Yomitan 真 structured-content 生成器的测试台
```

## 说明

- 词典内容版权归 **Pearson Education Limited**；本仓库仅为**私有**的技术研究与个人使用，
  不分发源数据，也不主张内容权利。
- 已完成隔离 Chrome 中的实际 Yomitan 导入器/IndexedDB 全量导入；**完整扩展 UI、Anki 客户端仍未验收**，不把组件级验收等同于整个应用。
