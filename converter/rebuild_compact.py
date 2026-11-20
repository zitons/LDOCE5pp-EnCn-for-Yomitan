"""重建一个干净、精简的库：只留 ode2024 + 5in1，只建 Hoshi 真正用到的两个索引。

为什么不用 DELETE + VACUUM：
  删 60 万行要把 WAL 写一遍，VACUUM 再把整库读一遍重写一遍，合计约 12 GB I/O。
  直接 ATTACH 一个新库、把要留的行 INSERT..SELECT 过去，只读 2.4 GB、写 2.9 GB，
  而且新库可以关掉日志和同步，快得多。旧库全程只读，出错不影响。

用法：
  python converter/rebuild_compact.py --dry-run
  python converter/rebuild_compact.py --apply
"""
import argparse
import os
import sqlite3
import sys
import time

SRC = "yomitan_audio/tld.db"
DST = "yomitan_audio/tld_new.db"
KEEP = ("ode2024", "cepd18", "lpd3", "webster", "vocab", "collins")

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()

if os.path.exists(DST):
    os.remove(DST)

con = sqlite3.connect("file:%s?mode=ro" % SRC, uri=True, timeout=600)
con.execute("attach database ? as n", (DST,))
con.execute("pragma n.journal_mode=off")     # 新库不要回滚日志，坏了重来即可
con.execute("pragma n.synchronous=off")
con.execute("pragma cache_size=-262144")     # 256 MB
con.execute("pragma n.cache_size=-262144")

t0 = time.time()
con.executescript("""
CREATE TABLE n.entries (
    id integer PRIMARY KEY NOT NULL,
    expression text NOT NULL,
    reading text,
    source text NOT NULL,
    speaker text,
    display text,
    file text NOT NULL
);
CREATE TABLE n.android (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file TEXT NOT NULL,
    source TEXT NOT NULL,
    data BLOB NOT NULL
);
""")
print("建表 %.1fs" % (time.time() - t0), flush=True)

ph = ",".join("?" * len(KEEP))
t1 = time.time()
con.execute("insert into n.android(file, source, data) "
            "select file, source, data from main.android where source in (%s)" % ph, KEEP)
con.commit()
print("android 拷贝完成 %.1fs" % (time.time() - t1), flush=True)

t2 = time.time()
con.execute("insert into n.entries(id, expression, reading, source, speaker, display, file) "
            "select id, expression, reading, source, speaker, display, file "
            "from main.entries where source in (%s) order by id" % ph, KEEP)
con.commit()
print("entries 拷贝完成 %.1fs" % (time.time() - t2), flush=True)

t3 = time.time()
con.executescript("""
CREATE INDEX n.expr_idx ON entries(expression);
CREATE INDEX n.file_idx ON android(file);
""")
con.commit()
print("建索引 %.1fs" % (time.time() - t3), flush=True)

na = con.execute("select count(*), sum(length(data))/1048576.0 from n.android").fetchone()
ne = con.execute("select count(*) from n.entries").fetchone()[0]
print("新库：entries %d 行  android %d 行  BLOB %.0f MB" % (ne, na[0], na[1]))
print("耗时 %.1f 分钟" % ((time.time() - t0) / 60))

if a.apply:
    con.execute("detach database n")
    con.close()
    bak = "yomitan_audio/tld_old.db"
    if os.path.exists(bak):
        os.remove(bak)
    os.replace(SRC, bak)
    os.replace(DST, SRC)
    print("已切换：新库 -> %s，旧库留作 %s（确认可播后再删）" % (SRC, bak))
else:
    con.execute("detach database n")
    con.close()
    print("（空跑，新库已生成但未替换；加 --apply 才切换）")
