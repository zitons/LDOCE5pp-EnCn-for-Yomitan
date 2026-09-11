# LDOCE5pp En-Cn → Yomitan

把《朗文当代高级英语辞典 5++（LDOCE5++ V2.15 En-Cn）》的 MDX/MDD 转成
[Yomitan](https://github.com/yomitan/yomitan) format-3 词典包。

**成品**（约 57 MB）——从 Release 下载，不入库（GitHub 大包推送会被链路重置）：

> **[⬇ 下载 `LDOCE5pp_Yomitan_2026.09.10.zip`](https://github.com/zitons/LDOCE5pp-EnCn-for-Yomitan/releases/download/v2026.09.10/LDOCE5pp_Yomitan_2026.09.10.zip)**
> 全部版本见 [Releases](https://github.com/zitons/LDOCE5pp-EnCn-for-Yomitan/releases)。

| | |
|---|---|
| 行数 | **245,933** = 64,390 词条 + 181,274 别名重定向行 |
| 语言 | 双语（英文释义 + 中文翻译/搭配中文） |
| 词头 | 音标（含英美差异与重音标记）、●●● 核心词等级（悬停提示）、S/W 频次徽标、词性、语法框、词形变化 |
| 词条内链接 | 1,946,990 条活链，**零悬挂**；4,875 条因源库缺目标而降级 |
| 频率元数据 | `term_meta_bank`，可在 Yomitan 里**按词频排序** |
| 排版 | 主题自适应（跟随 Yomitan 的明暗主题，不跟操作系统） |

## 安装

Yomitan → `Dictionaries` → `Load zip` → 选下载到的 `LDOCE5pp_Yomitan_2026.09.10.zip`。

## 仓库内容

本仓库只放**源码、文档与审计脚本**（约 2 MB），词典包走 Release 附件 ——
试过直接 `git push` 57 MB 的单次请求，无论是直连还是经代理，都会被链路在
约 19 秒后重置（`curl 55 Send failure: Connection was reset`），故改用 Release 附件的
上传端点（`uploads.github.com`），一次通过。

## 重建

```bash
# 依赖：Python 3.11+、beautifulsoup4、lxml、tqdm、mdict-utils
python converter/ldoce2yomitan.py \
  -i "extract/LDOCE5++ V 2-15.mdx.txt" \
  -o yomitan_full -m bilingual --revision 2026.09.10
```

源数据（`.mdx` / `.mdd` / 解包文本）**不入库**：体积过大且受版权保护。
自己准备时用 `mdict-utils` 解包 `.mdx`，并把 `LDOCE5pp_config.ini` 一类的
同目录文件放好。约 13 分钟一趟（12 核机上单进程）。

调试构建（只渲染指定词、JSON 带缩进，便于目检）：

```bash
python converter/ldoce2yomitan.py -i "extract/LDOCE5++ V 2-15.mdx.txt" \
  -o yomitan_debug -m bilingual --test-words "improve,the,child" --keep-json
```

## 文档

| 文件 | 内容 |
|---|---|
| [`HANDOVER.md`](HANDOVER.md) | **接手先读这个**。项目全景、Yomitan format-3 契约速查、32 条踩坑清单（多数跳过必返工） |
| [`REVIEW.md`](REVIEW.md) | 独立审查报告：D0–D9 逐条缺陷、影响面量化、复现命令、已排除的怀疑 |
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
| `audit9_text_conservation.py` | 逐词条文本守恒（找"悄悄丢内容"） | 缺口 **1.74%**，全部为有意取舍 |
| `build_ref_render.py` | 用 `.mdd` 里的原版 CSS 生成参考渲染页 | — |

内置校验器（每次构建自动跑）：`rows=245933 dangling=0 seq_ok=1`。

## 目录

```
converter/                   转换器与全部审计脚本（唯一事实来源：ldoce2yomitan.py）
yomitan_full/                构建输出（入库的只有 index/styles/tag_bank；zip 见 Release）
mdd_assets/                  从 .mdd 取出的原版 LM5style.css 等（用于排版核对）
scgen_test/                  Node+jsdom 里跑 Yomitan 真 structured-content 生成器的测试台
shot_*.png / preview.html    排版与内容的可视证据
```

## 说明

- 词典内容版权归 **Pearson Education Limited**；本仓库仅为**私有**的技术研究与个人使用，
  不分发源数据，也不主张内容权利。
- 所有验证均为"结构合法 + 能被 Yomitan 真生成器渲染"，**尚未做过真机导入验收**——
  这是当前最大的未覆盖风险，见 `HANDOVER.md` §9。
