"""Benchmark: html.parser vs lxml on real records.

Also caches a stratified sample of raw entry contents to a pickle so later
comparisons (old code vs new code) reuse the same input instead of re-scanning
the 877 MB source.

Usage:
    python bench_parse.py [n_total]
"""
import json
import os
import pickle
import random
import sys
import time

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from bs4 import BeautifulSoup  # noqa: E402
from ldoce2yomitan import (  # noqa: E402
    TermIndex, LdoceRenderer, classify_record, iter_records, strip_invisible,
    extract_tags, pos_tags_rules, sc, merge_adjacent_text, sanitize_strings,
    ENTRY_SCORE,
)

SIDE = r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt"
CACHE = r"C:\workspace\ldoce\converter\_bench_sample.pkl"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
random.seed(3)

if os.path.exists(CACHE):
    with open(CACHE, "rb") as fh:
        sample = pickle.load(fh)
    print(f"[*] loaded cached sample: {len(sample)} records, "
          f"{sum(len(c) for _, c in sample) / 1048576:.1f} MB")
    ti = TermIndex()
    for key, content in iter_records(SIDE):
        k = strip_invisible(key).strip()
        if not k:
            continue
        kind, _ = classify_record(k, content)
        if kind == "entry":
            ti.add(k)
    print(f"[*] index built ({len(ti.exact)} entries)")
else:
    ti = TermIndex()
    sizes = []
    for key, content in iter_records(SIDE):
        k = strip_invisible(key).strip()
        if not k:
            continue
        kind, _ = classify_record(k, content)
        if kind == "entry":
            ti.add(k)
            sizes.append((len(content), k, content))
    sizes.sort()
    picks = sizes[-80:] + sizes[:80] + random.sample(sizes, min(N, len(sizes)))
    seen = set()
    sample = []
    for _, k, c in picks:
        if k in seen:
            continue
        seen.add(k)
        sample.append((k, c))
    with open(CACHE, "wb") as fh:
        pickle.dump(sample, fh)
    print(f"[*] built and cached sample: {len(sample)} records, "
          f"{sum(len(c) for _, c in sample) / 1048576:.1f} MB")

TOTAL_MB = sum(len(c) for _, c in sample) / 1048576
print(f"[*] payload = {len(sample)} records / {TOTAL_MB:.1f} MB of HTML\n")


def bench_parse(parser):
    t0 = time.time()
    n = 0
    for _, c in sample:
        soup = BeautifulSoup(c, parser)
        n += len(soup.find_all(True))
    dt = time.time() - t0
    print(f"  parse only  {parser:12} {dt:7.2f}s   {TOTAL_MB / dt:6.2f} MB/s   ({n} elements)")
    return dt


def bench_full(parser):
    r = LdoceRenderer(ti, mode="bilingual")
    tags = {k: extract_tags(c) for k, c in sample}
    t0 = time.time()
    out = 0
    for k, c in sample:
        soup = BeautifulSoup(c, parser)
        for h1 in soup.find_all("h1"):
            h1.decompose()
        root = (soup.find("div", class_="entry_content")
                or soup.find("span", class_="lm5ppbody") or soup)
        nodes = merge_adjacent_text(r._children_blocks(root))
        pos_tokens, freq_tokens = tags[k]
        tt, rr = pos_tags_rules(pos_tokens, freq_tokens)
        gloss = [{"type": "structured-content", "content": sc("div", nodes, cls="ld")}]
        out += len(json.dumps(sanitize_strings(
            [k, "", tt, rr, ENTRY_SCORE, gloss, 0, ""]), ensure_ascii=False))
    dt = time.time() - t0
    print(f"  full render {parser:12} {dt:7.2f}s   {TOTAL_MB / dt:6.2f} MB/s   ({out} bytes out)")
    return dt


print("== parse only ==")
a = bench_parse("html.parser")
b = bench_parse("lxml")
print(f"  -> lxml is {a / b:.1f}x faster\n")

print("== full render (parse + walk + serialise) ==")
c = bench_full("html.parser")
d = bench_full("lxml")
print(f"  -> lxml is {c / d:.1f}x faster")
print(f"\n  extrapolated to the whole 450 MB corpus:")
print(f"    html.parser : {c / TOTAL_MB * 450 / 60:.1f} min")
print(f"    lxml        : {d / TOTAL_MB * 450 / 60:.1f} min")
