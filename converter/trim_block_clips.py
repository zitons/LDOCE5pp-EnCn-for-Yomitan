# -*- coding: utf-8 -*-
"""把「区块录音」剪到第一句 —— 保留词本身，扔掉后面跟着的相邻词头。

区块录音的特征：一个单词却读出 15-30 秒，开头是「词. 词.」然后接着别的词
（实测 `cap` = "Cap, cap. off, cap opener, cap screw capability. Capable..."）。
剪法：silencedetect 找第一处 >=0.2s 的静音（起点 >=0.4s），在那里切断 +0.1s。

用法：
  python converter/trim_block_clips.py --limit 6      # 预览，写到 _tmp/trim_preview/
  python converter/trim_block_clips.py --apply        # 全部处理并写回库

原始 BLOB 先备份到 _tmp/trim_backup/（约 110 MB），出错可单条还原。
"""
import argparse
import csv
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import queue

FF = r"C:/Users/zitons/AppData/Local/Hibiki/ffmpeg.exe"
DB = r"C:\workspace\ldoce\yomitan_audio\tld.db"
LIST = r"C:\workspace\ldoce\_tmp\longblocks.tsv"
PREV = r"C:\workspace\ldoce\_tmp\trim_preview"
WORK = r"C:\workspace\ldoce\_tmp\trimwork"
BKUP = r"C:\workspace\ldoce\_tmp\trim_backup"
LOG = r"C:\workspace\ldoce\_tmp\trimmed.tsv"
THREADS = 1
SLEEP = 0.05

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--only", default="")
ap.add_argument("--expr", default="")
ap.add_argument("--min-cut", type=float, default=0.8)
ap.add_argument("--max-cut", type=float, default=3.2)
ap.add_argument("--threads", type=int, default=THREADS)
ap.add_argument("--sleep", type=float, default=SLEEP,
                help="每处理完一条歇多少秒，给磁盘喘口气")
a = ap.parse_args()


def sign(r):
    """备份/预览文件名：source__清洗后的词条.opus。也是断点续跑的键。"""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", r["expression"])[:40]
    return "%s__%s.opus" % (r["source"], safe)

for d in (PREV, WORK, BKUP):
    os.makedirs(d, exist_ok=True)

rows = list(csv.DictReader(open(LIST, encoding="utf-8"), delimiter="\t"))
# ode2024 不用剪：它那 19 条全是 pneumonoultramicroscopic... 这类超长词，
# 3.86 秒本来就是正常时长，剪了就残。
rows = [r for r in rows if r["source"] != "ode2024"]
# 按词长自适应下限：mw 里有一批「把整条短语连写成一个 token」的词条
# （sijeunessesavaitsivieillessepouvait），4-5 秒也是正常的。
rows = [r for r in rows
        if float(r["est_sec"]) >= 2.5 + 0.06 * len(r["expression"])]
if a.only:
    rows = [r for r in rows if r["source"] == a.only]
if a.expr:
    want = set(a.expr.split(","))
    rows = [r for r in rows if r["expression"] in want]
if a.limit:
    rows = rows[:a.limit]

# 断点续跑：备份目录里有记录的，说明上轮已经改完（备份先写、再 update），跳过。
# 没有这一步的话，中断后重跑会把已剪过的再剪一遍（叠加一次无损→有损转码）。
if a.apply:
    done = set(os.listdir(BKUP)) if os.path.isdir(BKUP) else set()
    before = len(rows)
    rows = [r for r in rows if sign(r) not in done]
    print("已改过 %d 条，跳过；待处理 %d 条" % (before - len(rows), len(rows)),
          flush=True)
else:
    print("待处理", len(rows), flush=True)

con = sqlite3.connect(DB, timeout=900, check_same_thread=False)
lock = threading.Lock()
out = queue.Queue()
done_n = [0]
LOG_HEADED = os.path.exists(LOG) and os.path.getsize(LOG) > 0
logfh = open(LOG, "a", encoding="utf-8", newline="")
logw = csv.writer(logfh, delimiter="\t")
if not LOG_HEADED:
    logw.writerow(["source", "file", "expression", "orig_sec", "cut_sec", "size"])
    logfh.flush()


def logrow(*row):
    """逐条落盘。绝不能像上一版那样攒在内存里 —— 中途被杀就全丢。"""
    with lock:
        logw.writerow(row)
        logfh.flush()
        done_n[0] += 1
        if done_n[0] % 25 == 0:
            print("  %d/%d" % (done_n[0], len(rows)), flush=True)


def first_pause(path):
    err = subprocess.run(
        [FF, "-hide_banner", "-i", path,
         "-af", "silencedetect=noise=-35dB:d=0.2", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace").stderr
    for m in re.finditer(r"silence_start: ([\d.]+)", err):
        t = float(m.group(1))
        if t >= 0.4:
            return t
    return None


def work(slot):
    src_in = os.path.join(WORK, "in%d.bin" % slot)
    src_out = os.path.join(WORK, "out%d.opus" % slot)
    while True:
        try:
            r = out.get_nowait()
        except queue.Empty:
            return
        got = None
        with lock:
            got = con.execute("select id, data from android where source=? and file=? "
                              "order by length(data) desc limit 1",
                              (r["source"], r["file"])).fetchone()
        if not got:
            continue
        rid, data = got
        with open(src_in, "wb") as fh:
            fh.write(data)
        pause = first_pause(src_in)
        # 找不到静音点就不要硬切。实测这类往往不是区块录音，而是逐字母读的缩写
        # （XSCID）、缩写念完整词组（EBITDA -> "Earnings before interest, ..."）
        # 或单纯的长词，盲切会把尾音砍断。宁可长，不可残。
        if pause is None:
            logrow(r["source"], r["file"], r["expression"], r["est_sec"],
                   "", "无静音点-未改")
            continue
        cut = max(a.min_cut, min(a.max_cut, pause + 0.10))
        # -map 必须显式写死：历史上漏写 -map 导致输出与输入不成对
        p = subprocess.run(
            [FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src_in,
             "-map", "0:a:0", "-t", "%.2f" % cut,
             "-c:a", "libopus", "-b:a", "24k", "-ac", "1", "-ar", "48000",
             src_out], capture_output=True, text=True, errors="replace")
        if p.returncode or not os.path.exists(src_out):
            logrow(r["source"], r["file"], r["expression"], r["est_sec"], "", "FAIL")
            continue
        new = open(src_out, "rb").read()
        if a.apply:
            # 备份先落盘，再改库 —— 顺序不能反，否则中断后没有还原依据
            with open(os.path.join(BKUP, sign(r)), "wb") as fh:
                fh.write(data)
            with lock:
                con.execute("update android set data=? where id=?", (new, rid))
                con.commit()
        else:
            open(os.path.join(PREV, sign(r)), "wb").write(new)
        logrow(r["source"], r["file"], r["expression"],
               r["est_sec"], "%.2f" % cut, "%d->%d B" % (len(data), len(new)))
        if a.sleep:
            time.sleep(a.sleep)


for r in rows:
    out.put(r)
ts = [threading.Thread(target=work, args=(i,), daemon=True) for i in range(a.threads)]
for t in ts:
    t.start()
for t in ts:
    t.join()

logfh.close()
print("完成 %d 条" % done_n[0])
print("日志 ->", LOG)
if a.apply:
    print("原始备份 ->", BKUP)
