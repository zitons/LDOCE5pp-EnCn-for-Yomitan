"""找出所有「一个词读一长串」的区块录音：不解码，直接读容器头算时长。

为什么需要这个：之前用「同源体积中位数」挑候选，tld_ame 是 32 kbps mp3、
tld_uk 是 spx，校准系数偏差导致漏掉大半（只查出 1,536 条，实际 4,000+）。
按容器头算时长是精确的，全库 40 秒。

判据：时长 > max(2.5s, 0.06 × 词长 + 0.4)，且排除 ode2024（它的长音是
pneumonoultramicroscopic... 这种真长词）。

输出 _tmp/block_clips.tsv：source / file / expression / dur / threshold
用法：python converter/find_block_clips.py [--out PATH]
"""
import argparse
import collections
import sqlite3
import struct

DB = "file:yomitan_audio/tld.db?mode=ro"
BR = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
      2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
SRT = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_dur(b):
    off = 0
    if b[:3] == b"ID3":
        off = 10 + ((b[6] & 0x7F) << 21 | (b[7] & 0x7F) << 14 |
                    (b[8] & 0x7F) << 7 | (b[9] & 0x7F))
    i = b.find(b"\xff", off)
    while i >= 0 and i + 4 <= len(b):
        h = b[i:i + 4]
        if h[1] & 0xE0 == 0xE0:
            ver, layer = (h[1] >> 3) & 3, (h[1] >> 1) & 3
            if layer == 1 and ver in (3, 2, 0):
                vkey = 1 if ver == 3 else 2
                bi, si = (h[2] >> 4) & 0xF, (h[2] >> 2) & 3
                if 1 <= bi <= 14 and si != 3:
                    br, sr = BR[vkey][bi] * 1000, SRT[ver][si]
                    spf = 1152 if ver == 3 else 576
                    tag = b[i + 4 + (32 if vkey == 1 else 17): i + 220]
                    k = tag.find(b"Xing")
                    if k < 0:
                        k = tag.find(b"Info")
                    if k >= 0 and k + 12 < len(tag):
                        if int.from_bytes(tag[k + 4:k + 8], "big") & 1:
                            return int.from_bytes(tag[k + 8:k + 12], "big") * spf / sr
                    return (len(b) - i) * 8 / br
        i = b.find(b"\xff", i + 1)
    return None


def ogg_dur(b):
    pos, last = 0, None
    while True:
        i = b.find(b"OggS", pos)
        if i < 0:
            break
        last, pos = i, i + 4
    if last is None:
        return None
    g = struct.unpack("<Q", b[last + 6:last + 14])[0]
    return g / 48000.0 if g < 2 ** 62 else None


ap = argparse.ArgumentParser()
ap.add_argument("--out", default="_tmp/block_clips.tsv")
ap.add_argument("--skip", default="ode2024,mwu2020")
a = ap.parse_args()
SKIP = {x.strip() for x in a.skip.split(",") if x.strip()}

con = sqlite3.connect(DB, uri=True)
head = collections.defaultdict(dict)
for src, f, e in con.execute("select source, file, expression from entries"):
    d = head[src]
    if f not in d or len(e) < len(d[f]):
        d[f] = e

rows = []
for (src,) in con.execute("select distinct source from entries order by 1"):
    if src in SKIP:
        continue
    for f, b in con.execute("select file, data from android where source=? group by file",
                            (src,)):
        d = ogg_dur(b) if b[:4] == b"OggS" else mp3_dur(b)
        if not d or d > 120:
            continue
        e = head[src].get(f, "")
        thr = max(2.5, 0.06 * len(e) + 0.4)
        if d > thr:
            rows.append((src, f, e, d, thr))

rows.sort(key=lambda r: -r[3])
with open(a.out, "w", encoding="utf-8", newline="") as fh:
    fh.write("source\tfile\texpression\tdur\tthreshold\n")
    for src, f, e, d, thr in rows:
        fh.write("%s\t%s\t%s\t%.2f\t%.2f\n" % (src, f, e.replace("\t", " "), d, thr))

print("区块录音候选 %d 条 -> %s" % (len(rows), a.out))
c = collections.Counter(r[0] for r in rows)
for s, n in c.most_common():
    tot = con.execute("select count(distinct file) from entries where source=?",
                      (s,)).fetchone()[0]
    print("  %-11s %5d / %6d 文件 (%.1f%%)" % (s, n, tot, n / tot * 100))
print("最长 10 条:")
for src, f, e, d, thr in rows[:10]:
    print("  %5.2fs %-11s %-26s %s" % (d, src, e[:26], f[:40]))
