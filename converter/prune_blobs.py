# -*- coding: utf-8 -*-
"""删掉 entries 已不再引用的音频 BLOB，保持两表一一对应。

别用 `left join`：entries 没有 (file,source) 索引，SQLite 会退化成
android 每行扫一遍 entries（10 分钟都跑不完）。改成：
  entries 侧一次性读出 live 的 (source,file) 集合；
  android 侧走 idx_android_file_source 覆盖索引（只含 file/source/rowid，不碰 BLOB 页）；
  差集按 id 分批删。

用法：python converter/prune_blobs.py [--apply]
"""
import sqlite3
import sys

DB = r"C:\workspace\ldoce\yomitan_audio\tld.db"
BATCH = 1000
APPLY = "--apply" in sys.argv

con = sqlite3.connect(DB, timeout=600)
con.execute("pragma cache_size=-40000")

live = set(con.execute("select distinct source, file from entries"))
print("entries 引用的文件对", len(live), flush=True)

orphan = []
mb = 0
for fid, src, fname, n in con.execute(
        "select id, source, file, length(data) from android "
        "indexed by idx_android_file_source"):
    if (src, fname) not in live:
        orphan.append(fid)
        mb += n

print("孤儿 BLOB %d 条 / %.0f MB" % (len(orphan), mb / 1048576), flush=True)
if not APPLY:
    print("[dry-run] 加 --apply 才真删")
    sys.exit(0)

for i in range(0, len(orphan), BATCH):
    part = orphan[i:i + BATCH]
    con.execute("delete from android where id in (%s)" % ",".join("?" * len(part)),
                part)
    con.commit()
    if i % 20000 == 0:
        print("  %d/%d" % (i + len(part), len(orphan)), flush=True)

print("entries %d / android %d" % (
    con.execute("select count(*) from entries").fetchone()[0],
    con.execute("select count(*) from android").fetchone()[0]))
print("文件 %.2f GB" % (__import__("os").path.getsize(DB) / 1073741824))
