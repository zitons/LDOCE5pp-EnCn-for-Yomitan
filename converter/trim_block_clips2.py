"""按 _tmp/block_clips.tsv 剪掉「一个词读一长串」的尾巴，**原地替换音频，不删任何行**。

规则（沿用 2026-11-15 那轮的教训）：
1. 找第一个静音段（-32 dB / ≥0.12 s），切在它结束 +0.06 s；
2. 切点必须 ≥ 按词长算的下限（0.055×len + 0.35 s），否则**不切**——
   否则会把 possessed 切成 "posse-"；
3. 找不到静音点就**原样保留**，绝不硬切上限（EBITDA 那类缩写会被砍残）；
4. 容器保持原样：tld_ame 是 mp3 就输出 mp3，其余是 opus。

用法：
  python converter/trim_block_clips2.py --dry-run
  python converter/trim_block_clips2.py --apply [--limit N] [--only SRC]
"""
import argparse
import csv
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

FF = r"C:/Users/zitons/AppData/Local/Hibiki/ffmpeg.exe"
DB = "yomitan_audio/tld.db"
LIST = "_tmp/block_clips.tsv"
BACKUP = "_tmp/trim2_backup"
LOG = "_tmp/trim3.tsv"

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--only", default="")
ap.add_argument("--max-cut", type=float, default=3.2)
a = ap.parse_args()

os.makedirs(BACKUP, exist_ok=True)
rows = list(csv.DictReader(open(LIST, encoding="utf-8"), delimiter="\t"))
if a.only:
    rows = [r for r in rows if r["source"] == a.only]
if a.limit:
    rows = rows[:a.limit]
print("待处理 %d 条" % len(rows), flush=True)

con = sqlite3.connect(DB, timeout=900)
con.execute("pragma cache_size=-16000")

logf = open(LOG, "a", encoding="utf-8", newline="")
logw = csv.writer(logf, delimiter="\t")
if os.path.getsize(LOG) == 0:
    logw.writerow(["source", "file", "expression", "orig_sec", "cut_sec", "size"])


def first_pause(data, ext):
    """返回静音段结束时间（秒），找不到返回 None。"""
    p = subprocess.run([FF, "-hide_banner", "-i", "pipe:0", "-af",
                        "silencedetect=noise=-32dB:d=0.12", "-f", "null", "-"],
                       input=data, capture_output=True)
    err = p.stderr.decode("utf-8", "replace")
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", err)]
    if not ends:
        return None
    return ends[0] if starts else None


def encode(data, ext, cut):
    if ext == ".mp3":
        args = ["-c:a", "libmp3lame", "-b:a", "32k", "-ac", "1", "-ar", "22050"]
    else:
        args = ["-c:a", "libopus", "-b:a", "24k", "-ac", "1", "-ar", "48000"]
    p = subprocess.run([FF, "-v", "error", "-i", "pipe:0", "-map", "0:a:0", "-t",
                        "%.2f" % cut] + args + ["-f", "mp3" if ext == ".mp3" else "opus",
                                                "pipe:1"], input=data, capture_output=True)
    return p.stdout if p.returncode == 0 else None


done = skip = fail = 0
t0 = time.time()
for r in rows:
    src, f, e, orig = r["source"], r["file"], r["expression"], float(r["dur"])
    ext = os.path.splitext(f)[1].lower()
    got = con.execute("select id, data from android where source=? and file=? "
                      "order by length(data) desc", (src, f)).fetchall()
    if not got:
        skip += 1
        continue
    data = got[0][1]
    pause = first_pause(data, ext)
    floor = 0.055 * len(e) + 0.35
    if pause is None or pause + 0.06 < floor or pause > a.max_cut:
        logw.writerow([src, f, e, "%.2f" % orig, "skip", "%d B" % len(data)])
        logf.flush()
        skip += 1
        continue
    cut = pause + 0.06
    new = encode(data, ext, cut)
    if not new:
        fail += 1
        continue
    logw.writerow([src, f, e, "%.2f" % orig, "%.2f" % cut,
                   "%d->%d B" % (len(data), len(new))])
    logf.flush()
    if a.apply:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", "%s__%s" % (src, os.path.basename(f)))[:70]
        with open(os.path.join(BACKUP, safe), "wb") as fh:
            fh.write(data)
        for rid, _d in got:
            con.execute("update android set data=? where id=?", (new, rid))
        con.commit()
    done += 1
    if done % 100 == 0:
        print("  %d/%d  跳过 %d  已用 %.0fs" % (done, len(rows), skip, time.time() - t0),
              flush=True)

logf.close()
print("完成：剪 %d  跳过 %d  失败 %d  耗时 %.0fs" % (done, skip, fail, time.time() - t0))
if a.apply:
    print("原始备份 ->", BACKUP)
