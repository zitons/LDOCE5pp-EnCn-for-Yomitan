# -*- coding: utf-8 -*-
"""第二轮：对「第一轮切在 3.2 秒上限、实际还在多读」的短词重剪。

第一轮用 -35 dB / 0.2 s 找静音，有些录音词与词之间停得很轻，检测不到，只能
被 3.2 s 上限截住（实测 `boot` 仍读出 "Boot, bootable boot black T."）。

这一轮改成宽松阈值（-30 dB / 0.12 s，再退到 -26 dB / 0.10 s），并且**从原始
备份重剪**，避免在已重编码的文件上二次转码。找不到任何静音点就跳过，保持原样
—— 宁可长一点也不要把词切断。

只处理：无空格、长度 <= 10、当前时长 > 2.0 s、且不是第一轮回退（cut=2.50）的条目。
"""
import csv
import os
import re
import sqlite3
import subprocess
import threading

BASE = r"C:\workspace\ldoce"
FF = r"C:/Users/zitons/AppData/Local/Hibiki/ffmpeg.exe"
DB = os.path.join(BASE, "yomitan_audio", "tld.db")
DUR = os.path.join(BASE, "_tmp", "trim_dur.tsv")
BKUP = os.path.join(BASE, "_tmp", "trim_backup")
WORK = os.path.join(BASE, "_tmp", "trim2work")
LOG = os.path.join(BASE, "_tmp", "trim2.tsv")
APPLY = "--apply" in __import__("sys").argv

os.makedirs(WORK, exist_ok=True)


def sign(src, expr):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", expr)[:40]
    return "%s__%s.opus" % (src, safe)


rows = [r for r in csv.DictReader(open(DUR, encoding="utf-8"), delimiter="\t")
        if float(r["dur_now"]) > 2.0
        and r["cut_sec"] != "2.50"
        and " " not in r["expression"]
        and len(r["expression"]) <= 10]
print("第二轮候选", len(rows), flush=True)

con = sqlite3.connect(DB, timeout=900)


def first_pause(path, noise, dur):
    err = subprocess.run(
        [FF, "-hide_banner", "-i", path,
         "-af", "silencedetect=noise=%s:duration=%s" % (noise, dur),
         "-f", "null", "-"],
        capture_output=True, text=True, errors="replace").stderr
    for m in re.finditer(r"silence_start: ([\d.]+)", err):
        t = float(m.group(1))
        if t >= 0.30:
            return t
    return None


n = ok = skip = 0
with open(LOG, "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh, delimiter="\t")
    w.writerow(["source", "file", "expression", "before_sec", "after_sec", "note"])
    for r in rows:
        p = os.path.join(BKUP, sign(r["source"], r["expression"]))
        if not os.path.exists(p):
            w.writerow([r["source"], r["file"], r["expression"],
                        r["dur_now"], "", "无备份"])
            skip += 1
            continue
        pause = first_pause(p, "-30dB", "0.12")
        if pause is None:
            pause = first_pause(p, "-26dB", "0.10")
        if pause is None:
            w.writerow([r["source"], r["file"], r["expression"],
                        r["dur_now"], "", "无静音点-未改"])
            skip += 1
            continue
        cut = max(0.70, min(2.40, pause + 0.08))
        # 词长下限：短词 0.62s 处的静音很可能是词中间的气口，切了就断字。
        # 低于下限不切，保持 3.2 s 原样 —— 宁可长，不可残。
        floor = 0.055 * len(r["expression"]) + 0.35
        if cut < floor:
            w.writerow([r["source"], r["file"], r["expression"],
                        r["dur_now"], "", "切点太早(%.2f<%.2f)-未改" % (cut, floor)])
            skip += 1
            continue
        out = os.path.join(WORK, "o.opus")
        subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", p,
                        "-map", "0:a:0", "-t", "%.2f" % cut,
                        "-c:a", "libopus", "-b:a", "24k", "-ac", "1",
                        "-ar", "48000", out], capture_output=True)
        if not os.path.exists(out):
            w.writerow([r["source"], r["file"], r["expression"],
                        r["dur_now"], "", "编码失败"])
            skip += 1
            continue
        new = open(out, "rb").read()
        if APPLY:
            con.execute("update android set data=? where source=? and file=?",
                        (new, r["source"], r["file"]))
            con.commit()
        w.writerow([r["source"], r["file"], r["expression"],
                    r["dur_now"], "%.2f" % cut, "%d B" % len(new)])
        fh.flush()
        ok += 1
        n += 1
        if n % 20 == 0:
            print("  %d/%d" % (n, len(rows)), flush=True)

print("改 %d 条，跳过 %d 条%s" % (ok, skip, "" if APPLY else "（空跑）"))
print("日志 ->", LOG)
