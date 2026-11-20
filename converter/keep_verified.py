# -*- coding: utf-8 -*-
"""只保留「能确认读的是什么」的行：文件名可对上词头，或带英美标记。

规则：
  1. 整源可校验率 >= 99%  ->  该源全留（mw / snd / ode2024 / tld_uk）
     这些源里少数没通过检查的是缩写、连字符之类，删了是误伤。
  2. 其余源逐行判：
       文件名归一化后含词头前 5 字符（短词则要求整词出现在文件名里）
       或 speaker 非空
       或文件名带 gb / us / uk / ame / bre / en_gb / en_us 标记
     ->  留；否则删。

输出 _tmp/dropped_rows.tsv（被删的三元组，留档可查）。
用法：python converter/keep_verified.py [--apply]

建库之后必须跟 prune_blobs.py，再跟 reorder_entries.py。
"""
import collections
import csv
import re
import sqlite3
import sys

DB = r"C:\workspace\ldoce\yomitan_audio\tld.db"
BATCH = 2000
APPLY = "--apply" in sys.argv

ACC = re.compile(r"(?:^|[^a-z])(?:gb|us|uk|ame|bre)(?:[^a-z]|$)|en_gb|en_us", re.I)
SAFE_RATE = 0.99


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


con = sqlite3.connect(DB, timeout=300)
rows = con.execute("select id, source, file, expression, speaker from entries").fetchall()
print("总行", len(rows))

stats = collections.defaultdict(lambda: [0, 0])       # src -> [keep, drop]
ver = collections.defaultdict(lambda: [0, 0])         # src -> [verifiable, total]
for _i, s, f, e, sp in rows:
    w = norm(e)
    stem = norm(f.rsplit(".", 1)[0])
    ok = (len(w) >= 5 and w[:5] in stem) or (2 <= len(w) < 5 and w in stem)
    ver[s][1] += 1
    ver[s][0] += ok

safe = {s for s, (a, b) in ver.items() if b and a / b >= SAFE_RATE}
print("整源全留:", sorted(safe))

drop_ids = []
for i, s, f, e, sp in rows:
    if s in safe:
        stats[s][0] += 1
        continue
    w = norm(e)
    stem = norm(f.rsplit(".", 1)[0])
    ok = ((len(w) >= 5 and w[:5] in stem)
          or (2 <= len(w) < 5 and w in stem)
          or bool(sp) or bool(ACC.search(f)))
    if ok:
        stats[s][0] += 1
    else:
        stats[s][1] += 1
        drop_ids.append((i, s, f, e))

print()
print("%-12s %8s %8s %8s %7s" % ("源", "总行", "保留", "删除", "删除%"))
for s in sorted(stats, key=lambda x: -sum(stats[x])):
    k, d = stats[s]
    print("%-12s %8d %8d %8d %6.1f%%" % (s, k + d, k, d, d / (k + d) * 100))
print("合计删除", len(drop_ids), "行")

# 删后彻底失音的词条
alive = collections.defaultdict(bool)
for i, s, f, e, sp in rows:
    if s in safe:
        alive[e] = True
        continue
    if not alive[e]:
        w = norm(e)
        stem = norm(f.rsplit(".", 1)[0])
        alive[e] = ((len(w) >= 5 and w[:5] in stem)
                    or (2 <= len(w) < 5 and w in stem)
                    or bool(sp) or bool(ACC.search(f)))
dead = sorted(e for e, v in alive.items() if not v)
print("删后彻底没音的词条 %d / %d (%.1f%%)"
      % (len(dead), len(alive), len(dead) / len(alive) * 100))
print("  单字", sum(1 for e in dead if " " not in e), "| 样例:",
      ", ".join(dead[:12]))

with open("_tmp/dropped_rows.tsv", "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh, delimiter="\t")
    w.writerow(["source", "file", "expression"])
    for _i, s, f, e in drop_ids:
        w.writerow([s, f, e])
with open("_tmp/dead_expressions.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(dead))
print("留档: _tmp/dropped_rows.tsv / _tmp/dead_expressions.txt")

if not APPLY:
    print("\n[dry-run] 加 --apply 才真删")
    sys.exit(0)

ids = [i for i, _s, _f, _e in drop_ids]
for n in range(0, len(ids), BATCH):
    part = ids[n:n + BATCH]
    q = "delete from entries where id in (%s)" % ",".join("?" * len(part))
    con.execute(q, part)
    con.commit()
    print("  删除 %d/%d" % (min(n + BATCH, len(ids)), len(ids)), flush=True)
print("剩余 entries", con.execute("select count(*) from entries").fetchone()[0])
