"""整源删除：把某个 source 的 entries / android 行按批删掉。

分批提交（每批 2000 行），避免 5 GB 的库一次性回滚日志把机器拖死。
删完**不会**自动 VACUUM —— DELETE 只把页标成空闲，文件不会缩小；
要真正还回磁盘空间得另外跑 VACUUM（长时间占 I/O）。
孤儿 BLOB 用 prune_blobs.py 清。

用法：
  python converter/drop_source.py tld_mw tld_snd --dry-run
  python converter/drop_source.py tld_mw tld_snd --apply
"""
import argparse
import sqlite3

DB = "yomitan_audio/tld.db"
BATCH = 2000

ap = argparse.ArgumentParser()
ap.add_argument("sources", nargs="+")
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()

con = sqlite3.connect(DB, timeout=600)
con.execute("pragma temp_store=MEMORY")
con.execute("pragma cache_size=-40000")

total_e = total_a = 0
for src in a.sources:
    n_e = con.execute("select count(*) from entries where source=?", (src,)).fetchone()[0]
    n_a = con.execute("select count(*) from android where source=?", (src,)).fetchone()[0]
    mb = con.execute("select sum(length(data))/1048576.0 from android where source=?",
                     (src,)).fetchone()[0] or 0
    print("%-11s entries %7d  android %7d  %6.0f MB" % (src, n_e, n_a, mb))
    total_e += n_e
    total_a += n_a
print("合计 entries %d / android %d" % (total_e, total_a))

if not a.apply:
    print("（空跑，加 --apply 才真删）")
    raise SystemExit

for src in a.sources:
    for tbl in ("android", "entries"):
        done = 0
        while True:
            cur = con.execute(
                "delete from %s where id in "
                "(select id from %s where source=? limit %d)" % (tbl, tbl, BATCH),
                (src,))
            con.commit()
            if cur.rowcount == 0:
                break
            done += cur.rowcount
        print("  %-11s %-8s 删 %6d" % (src, tbl, done), flush=True)

print("\n剩余 entries %d / android %d" % (
    con.execute("select count(*) from entries").fetchone()[0],
    con.execute("select count(*) from android").fetchone()[0]))
print("现存源:", [r[0] for r in con.execute(
    "select distinct source from entries order by 1")])
con.close()
