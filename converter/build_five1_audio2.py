"""5in1 建库（单 writer 架构）。

结构：
  worker × N : 各自打开 Sound.mdd，按分片取音频 -> 批量转 opus -> 把
               (source, accent, name, blob, [expression...]) 塞进结果队列
  主进程     : 唯一持有数据库连接，从队列取结果、批量写库

为什么这么拆：实测四个进程同时写库时，单条要多花约 8 ms 等锁（19 ms -> 27 ms），
而 SQLite 单进程连续插入能到 14,000 行/秒（0.07 ms/行）——写锁是纯粹的内耗。
拆开之后 worker 只读只转码，瓶颈回到 CPU，实测约 300 行/秒。

用法：
  python converter/build_five1_audio2.py --dry-run
  python converter/build_five1_audio2.py --apply [--workers 6] [--limit N]
断点续跑：已入库的 (source, file) 会跳过。
"""
import argparse
import csv
import multiprocessing as mp
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_tmp"))

DB = "yomitan_audio/tld.db"
MAP = "_tmp/five1_map.tsv"
MDD_PATH = r"C:\baidunetdiskdownload\5 in 1 English Pronunciation Dictionary\Sound.mdd"
FF = r"C:/Users/zitons/AppData/Local/Hibiki/ffmpeg.exe"

SRC_NAME = {"Webster": "webster", "CEPD18": "cepd18", "LPD3": "lpd3",
            "Vocabulary": "vocab", "Collins": "collins"}
ARGV = ["-c:a", "libopus", "-b:a", "24k", "-compression_level", "0",
        "-ac", "1", "-ar", "48000"]
BATCH = 40


def out_name(f):
    return re.sub(r"\.spx$", ".opus", f.lower())


def load_items(only=""):
    items = {}
    for r in csv.DictReader(open(MAP, encoding="utf-8"), delimiter="\t"):
        expr = r["expression"].strip()
        if not expr:
            continue
        for x in r["items"].split(","):
            p = x.split("|")
            if len(p) < 3:
                continue
            src = SRC_NAME.get(p[0])
            if not src or (only and src != only):
                continue
            acc = p[1] if p[1] in ("UK", "US") else None
            if src == "collins":
                acc = None
            items.setdefault((src, acc, p[2]), []).append(expr)
    return items


def worker(idx, total, todo, out_q, counters):
    """只读 + 转码，结果丢进队列。"""
    try:
        _worker(idx, total, todo, out_q, counters)
    except Exception:
        import traceback
        traceback.print_exc()
        out_q.put(None)


def _worker(idx, total, todo, out_q, counters):
    from fast_mdd import FastMDD

    d = FastMDD(MDD_PATH)
    work = tempfile.mkdtemp(prefix="five1w%d_" % idx)
    mine = [k for i, k in enumerate(todo) if i % total == idx]
    for start in range(0, len(mine), BATCH):
        chunk = mine[start:start + BATCH]
        srcs, outs, good = [], [], []
        for i, (src, acc, f, exprs) in enumerate(chunk):
            raw = d.get(f)
            if not raw:
                with counters.get_lock():
                    counters[0] += 1        # skip
                continue
            p = os.path.join(work, "i%d.spx" % i)
            with open(p, "wb") as fh:
                fh.write(raw)
            srcs.append(p)
            outs.append(os.path.join(work, "o%d.opus" % i))
            good.append((src, acc, f, exprs))
        if not srcs:
            continue
        cmd = [FF, "-v", "error", "-y"]
        for p in srcs:
            cmd += ["-i", p]
        for i, o in enumerate(outs):
            cmd += ["-map", "%d:a" % i] + ARGV + [o]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode:
            for p, o in zip(srcs, outs):
                subprocess.run([FF, "-v", "error", "-y", "-i", p] + ARGV + [o],
                               capture_output=True)
        for (src, acc, f, exprs), o in zip(good, outs):
            if not os.path.exists(o) or os.path.getsize(o) == 0:
                with counters.get_lock():
                    counters[1] += 1        # fail
                continue
            with open(o, "rb") as fh:
                blob = fh.read()
            out_q.put((src, acc, out_name(f), blob, exprs))
            os.remove(o)
        for p in srcs:
            os.remove(p)
    shutil.rmtree(work, ignore_errors=True)
    out_q.put(None)




def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()

    items = load_items(a.only)
    print("待处理音频 %d 个" % len(items), flush=True)

    con = sqlite3.connect(DB, timeout=900)
    con.execute("pragma cache_size=-64000")
    con.execute("pragma wal_autocheckpoint=20000")
    con.execute("pragma temp_store=MEMORY")
    have = {(s, f) for s, f in con.execute("select distinct source, file from android")}
    todo = [(k[0], k[1], k[2], tuple(items[k])) for k in items
            if (k[0], out_name(k[2])) not in have]
    if a.limit:
        todo = todo[:a.limit]
    print("已入库 %d，本轮 %d，worker %d" % (len(have), len(todo), a.workers), flush=True)
    if not todo:
        return

    ctx = mp.get_context("spawn")
    out_q = ctx.Queue(maxsize=400)
    counters = ctx.Array("i", 3)      # skip / fail / rows
    procs = []
    for i in range(a.workers):
        p = ctx.Process(target=worker, args=(i, a.workers, todo, out_q, counters))
        p.start()
        procs.append(p)

    t0 = time.time()
    pa, pe, done, alive = [], [], 0, a.workers
    last = 0
    while alive:
        try:
            msg = out_q.get(timeout=60)
        except queue.Empty:
            if not any(p.is_alive() for p in procs):
                break
            continue
        if msg is None:
            alive -= 1
            continue
        src, acc, name, blob, exprs = msg
        pa.append((name, src, blob))
        for e in exprs:
            pe.append((e, None, src, acc, None, name))
        done += 1
        if len(pa) >= 500:
            if a.apply:
                con.executemany("insert into android(file, source, data) values(?,?,?)", pa)
                con.executemany("insert into entries(expression, reading, source, speaker, "
                                "display, file) values(?,?,?,?,?,?)", pe)
                con.commit()
            counters[2] += len(pe)
            pa.clear()
            pe.clear()
        if done - last >= 5000:
            last = done
            el = time.time() - t0
            print("  %d/%d  剩余约 %.1f 分钟"
                  % (done, len(todo), (len(todo) - done) / max(done / el, 1e-6) / 60),
                  flush=True)

    for p in procs:
        p.join()
    if pa and a.apply:
        con.executemany("insert into android(file, source, data) values(?,?,?)", pa)
        con.executemany("insert into entries(expression, reading, source, speaker, "
                        "display, file) values(?,?,?,?,?,?)", pe)
        con.commit()
    print("完成：音频 %d  行 %d  跳过 %d  失败 %d  耗时 %.0f 分钟"
          % (done, counters[2] + len(pe), counters[0], counters[1],
             (time.time() - t0) / 60))


if __name__ == "__main__":
    main()
