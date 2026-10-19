"""Record-conservation ledger: does EVERY source MDX record land somewhere?

Every other gate in this repo is package-to-package (did this build change
anything relative to the last one). The source-facing audits
(`audit_source_coverage.py`, `audit_redirect_coverage.py`, `audit_skip_reasons.py`)
each answer one question and print their own partial tally, so no single number
says "285,017 source records -> 245,933 package rows, and here is exactly where
the difference lives". This script closes that ledger as an identity:

    source records
      = entry records + redirect records + skip records
    redirect records
      = empty-target + self-target + duplicate (key,target) records
        + multi-target folds + distinct alias keys
    distinct alias keys
      = redirect rows written + keys shadowed by their own entry row
        + keys with no representable target          <- must be 0
    entry records == content rows in the package     <- must hold exactly

so the residual is 0 by construction and a real drop shows up as a NAMED,
COUNTED bucket instead of a missing 15% of the corpus.

It also reconciles THIRD-PARTY entry counts against the ledger. The figure in
circulation for this dictionary is 283,110 (the widely copied "LDOCE5++ V2.15
by Farefear -- 283110 entries, 218252 cross-references" blurb, which is where
"the original MDX has 283,110 entries" comes from). Pass the number you are
comparing with `--expect-total` (repeatable) and the script tries every subset of
the ledger buckets, so an outside count is either explained by name or admitted
as unexplained -- instead of being compared against a number that measures
something else.

Usage:
    python converter/audit_record_conservation.py                    # defaults
    python converter/audit_record_conservation.py --package <zip> --expect-total 283110
    python converter/audit_record_conservation.py --mdx <mdx>        # header count
    python converter/audit_record_conservation.py --self-test        # no data needed
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter

# Derive the checkout root from this file, as the audit_2026_09_* scripts do, and
# reuse the converter's own classification instead of re-typing it.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "converter"))
import ldoce2yomitan as C  # noqa: E402

DEFAULT_SRC = os.path.join(ROOT, "extract", "LDOCE5++ V 2-15.mdx.txt")
DEFAULT_PKG = os.environ.get(
    "AUDIT_PKG",
    os.path.join(ROOT, "yomitan_fixed", "2026-10-09-margin-left", "bilingual",
                 "LDOCE5pp_Yomitan_2026.10.12.zip"))

# A skipped record is only benign if it carries no dictionary article. The probe
# has to look at the WHOLE record: `classify_record` already searches the first
# 8000 chars for these markers, so re-testing that window would be tautological
# -- a skip could never match it (the "audit that can only pass" trap, HANDOVER
# pitfall 63). Anything marked up beyond that window is a real finding.
ENTRY_MARKERS = ("entry_content", "ldoceEntry")
SENSE_MARKERS = ('class="Sense"', 'class="DEFN"')
IMAGE_KEY_RE = re.compile(r"^ldoce\d+jpg", re.IGNORECASE)
# Skips whose content is documented elsewhere in the package (see HANDOVER
# "L4" / REVIEW D9): dropping the ACTIV index pages loses a grouping, not text,
# because every sense on such a page is also rendered in its own entry.
BENIGN_SKIP_BUCKETS = {"ACTIV: topic index page", "image key (payload in the .mdd)",
                       # no key -> no expression to look it up by, so no row can
                       # exist for it; the source itself cannot resolve it either
                       "empty key"}


# --------------------------------------------------------------------- source
def scan_source(path, max_samples=5):
    """One pass over the unpacked MDX, mirroring Pass A of the build."""
    out = {"path": path, "records": 0, "kinds": Counter(),
            "entry_keys": set(), "entry_key_records": Counter(),
            "alias_records": Counter(), "alias_targets": {},
            "redirect_empty_target": 0, "redirect_self_target": 0,
            "skip_buckets": Counter(), "skip_samples": {},
            "skip_marker_by_bucket": Counter(), "skip_senses": Counter(),
            "skip_marker_samples": {},
            "all_keys": set()}
    for key, content in C.iter_records(path):
        out["records"] += 1
        k = C.strip_invisible(key).strip()
        out["all_keys"].add(k)
        kind, target = C.classify_record(key, content)
        out["kinds"][kind] += 1
        if kind == "entry":
            out["entry_keys"].add(k)
            out["entry_key_records"][k] += 1
        elif kind == "redirect":
            if not target:
                out["redirect_empty_target"] += 1
            elif target == k:
                # A key that points at itself resolves to nothing in the source
                # either; a row for it would have to target a non-existent entry.
                out["redirect_self_target"] += 1
            else:
                out["alias_records"][(k, target)] += 1
                out["alias_targets"].setdefault(k, set()).add(target)
        else:
            bucket = _skip_bucket(k)
            out["skip_buckets"][bucket] += 1
            if len(out["skip_samples"].get(bucket, [])) < max_samples:
                out["skip_samples"].setdefault(bucket, []).append(k)
            if any(m in content for m in ENTRY_MARKERS):
                out["skip_marker_by_bucket"][bucket] += 1
                if len(out["skip_marker_samples"].get(bucket, [])) < max_samples:
                    out["skip_marker_samples"].setdefault(bucket, []).append(k)
                out["skip_senses"][bucket] += sum(
                    content.count(m) for m in SENSE_MARKERS)
    return out


def _skip_bucket(key):
    if not key:
        return "empty key"
    if key.upper().startswith("ACTIV:"):
        return "ACTIV: topic index page"
    if IMAGE_KEY_RE.match(key):
        return "image key (payload in the .mdd)"
    if C.SKIP_KEY_RE.match(key):
        return "other SKIP_KEY_RE match"
    return "no entry_content / ldoceEntry marker"


# ------------------------------------------------------------------- package
def scan_package(path):
    """term_bank rows split into content rows and redirect-shaped rows."""
    pkg = {"path": path, "rows": 0, "banks": 0, "content": Counter(),
           "redirect": {}, "seqs": []}
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist()
                       if re.fullmatch(r"term_bank_\d+\.json", n))
        pkg["banks"] = len(names)
        for name in names:
            for row in json.loads(z.read(name)):
                pkg["rows"] += 1
                expr, score = row[0], row[4]
                gloss = row[5] if len(row) > 5 else []
                pkg["seqs"].append(row[6] if len(row) > 6 else None)
                if _is_redirect_row(score, gloss):
                    targets = [g[0] for g in gloss
                               if isinstance(g, list) and g and g[0]]
                    if expr in pkg["redirect"] and pkg["redirect"][expr] != targets:
                        pkg["conflicting_redirect_rows"] = (
                            pkg.get("conflicting_redirect_rows", 0) + 1)
                    pkg["redirect"][expr] = targets
                else:
                    pkg["content"][expr] += 1
    return pkg


def _is_redirect_row(score, gloss):
    """Recognised by SHAPE, not by a magic score (see audit_redirect_coverage.py:
    testing `score == 0` once reported 0 redirect rows against a build log that
    claimed 181,274, because content rows carry +10 and redirect rows -10)."""
    if not isinstance(score, (int, float)) or score >= 0:
        return False
    if not isinstance(gloss, list) or not gloss:
        return False
    return all(isinstance(g, list) and len(g) > 1 and isinstance(g[1], list)
               and "redirect" in g[1] for g in gloss)


# -------------------------------------------------------------------- ledger
def build_ledger(src, pkg):
    alias_keys = set(src["alias_targets"])
    content_exprs = set(pkg["content"])
    rows_written = len(pkg["redirect"])
    shadowed = alias_keys & content_exprs
    unresolved = {k for k in alias_keys
                  if k not in content_exprs and k not in pkg["redirect"]}
    kept_records = sum(src["alias_records"].values())
    distinct_pairs = len(src["alias_records"])
    collapsed = kept_records - distinct_pairs              # repeated (key,target)
    folded = distinct_pairs - len(alias_keys)              # >1 target on one key
    dup_entries = sum(n - 1 for n in src["entry_key_records"].values())

    buckets = {
        "content rows (entry records)": src["kinds"]["entry"],
        "redirect rows written": rows_written,
        "alias keys shadowed by their own entry row": len(shadowed),
        "alias keys with no representable target": len(unresolved),
        "duplicate (key,target) alias records": collapsed,
        "extra targets folded into multi-target rows": folded,
        "redirect records whose target is the key itself": src["redirect_self_target"],
        "redirect records with an empty target": src["redirect_empty_target"],
    }
    for bucket, cnt in src["skip_buckets"].most_common():
        buckets[f"skipped: {bucket}"] = cnt
    accounted = sum(buckets.values())
    return {
        "buckets": buckets,
        "alias_keys": len(alias_keys),
        "rows_written": rows_written,
        "shadowed": len(shadowed),
        "unresolved": unresolved,
        "collapsed": collapsed,
        "folded": folded,
        "dup_entries": dup_entries,
        "content_rows": sum(pkg["content"].values()),
        "accounted": accounted,
        "residual": src["records"] - accounted,
    }


# -------------------------------------------------------------------- checks
def check(src, pkg, ledger):
    """[(code, message, samples)]; an empty list means nothing was dropped."""
    fails = []
    if ledger["residual"]:
        fails.append(("L0", f"ledger does not close: {ledger['residual']:+,} source "
                      f"record(s) sit in no bucket", []))
    if src["kinds"]["entry"] != ledger["content_rows"]:
        fails.append(("C1", f"{src['kinds']['entry']:,} entry records vs "
                      f"{ledger['content_rows']:,} content rows", []))
    missing = sorted(k for k in src["entry_keys"] if k not in set(pkg["content"]))
    if missing:
        fails.append(("C2", f"{len(missing):,} source entries have no row", missing))
    if ledger["unresolved"]:
        fails.append(("C3", f"{len(ledger['unresolved']):,} alias keys resolve to "
                      f"nothing (no content row, no redirect row)",
                      sorted(ledger["unresolved"])))
    hard = {b: n for b, n in src["skip_marker_by_bucket"].items()
            if b not in BENIGN_SKIP_BUCKETS}
    if hard:
        risky = [k for b in hard for k in src["skip_marker_samples"].get(b, [])]
        fails.append(("C4", f"{sum(hard.values()):,} skipped record(s) carry "
                      f"dictionary markup beyond the classify probe {dict(hard)}",
                      risky))
    ti = C.TermIndex()
    for expr in pkg["content"]:
        ti.add(expr)
    ti.finalize_rendered(set(pkg["content"]))
    lost = []
    for word, targets in src["alias_targets"].items():
        row = pkg["redirect"].get(word)
        if row is None:
            continue
        have = set(row)
        lost += [f"{word!r} -> {t!r}" for t in targets
                 if ti.resolve(t) and ti.resolve(t) not in have]
    if lost:
        fails.append(("C5", f"{len(lost):,} alias target(s) present in the source "
                      f"but absent from the row", lost))
    shadow_loss = set(pkg["content"]) & set(pkg["redirect"])
    if shadow_loss:
        fails.append(("C8", f"{len(shadow_loss):,} expression(s) written as BOTH a "
                      f"content row and a redirect row", sorted(shadow_loss)))
    extra = sorted(e for e in (set(pkg["content"]) | set(pkg["redirect"]))
                   if e not in src["all_keys"])
    if extra:
        fails.append(("C6", f"{len(extra):,} package expression(s) with no source "
                      f"record", extra))
    seqs = [s for s in pkg["seqs"] if isinstance(s, int)]
    if seqs and sorted(seqs) != list(range(len(seqs))):
        fails.append(("C7", f"sequence is not 0..{len(seqs) - 1} contiguous", []))
    if pkg.get("conflicting_redirect_rows"):
        fails.append(("C9", f"{pkg['conflicting_redirect_rows']} duplicate "
                      f"redirect rows with conflicting targets", []))
    return fails


def reconcile(expected, buckets):
    """Which subset of ledger buckets has to be removed to reach `expected`?

    The ledger is a sum of named buckets, so an outside count is explained the
    moment it equals `total - some buckets`. Enumerating the subsets (2^n, n<=16)
    keeps it honest: a number that is not a subset sum stays flagged instead of
    being waved at with a percentage.
    """
    live = {k: v for k, v in buckets.items() if v}   # a 0 bucket explains nothing
    need = sum(buckets.values()) - expected
    if need < 0:
        return []
    names = list(live)
    hits = []
    for mask in range(1, 1 << len(names)):
        dropped = [names[i] for i in range(len(names)) if mask & (1 << i)]
        if sum(live[d] for d in dropped) == need:
            hits.append(dropped)
    hits.sort(key=len)
    return hits


# -------------------------------------------------------------------- report
def report(src, pkg, ledger, fails, expected_list, note):
    print(f"source : {src['path']}  ({os.path.getsize(src['path']):,} B)")
    print(f"package: {pkg['path']}  ({os.path.getsize(pkg['path']):,} B, "
          f"{pkg['banks']} term banks)")
    print()
    print("=" * 74)
    print("SOURCE")
    print("=" * 74)
    print(f"records scanned     : {src['records']:>9,}")
    for kind in ("entry", "redirect", "skip"):
        print(f"  {kind:<20}: {src['kinds'][kind]:>9,}")
    print(f"unique entry keys   : {len(src['entry_keys']):>9,}   (records sharing a "
          f"key: {ledger['dup_entries']:,} -> those become extra rows, not losses)")
    print()
    for bucket, cnt in src["skip_buckets"].most_common():
        marks = src["skip_marker_by_bucket"].get(bucket, 0)
        senses = src["skip_senses"].get(bucket, 0)
        flag = " (exempt)" if bucket in BENIGN_SKIP_BUCKETS else ""
        sample = ", ".join(repr(s[:32]) for s in src["skip_samples"].get(bucket, [])[:2])
        print(f"skip {bucket:<38}: {cnt:>7,}  with entry markup{flag}: {marks:>6,}"
              f"  sense/DEFN blocks: {senses:>7,}")
        print(f"     {'':<38}  e.g. {sample}")
    if note:
        print()
        print(note)
    print()
    print("=" * 74)
    print("LEDGER  (each source record lands in exactly one bucket)")
    print("=" * 74)
    for name, val in ledger["buckets"].items():
        print(f"  {name:<52}{val:>10,}")
    print("  " + "-" * 62)
    print(f"  {'accounted':<52}{ledger['accounted']:>10,}")
    print(f"  {'RESIDUAL (must be 0)':<52}{ledger['residual']:>10,}")
    print()
    print(f"package rows        : {pkg['rows']:>9,} = "
          f"{ledger['content_rows']:,} content + {ledger['rows_written']:,} redirect")
    if expected_list:
        print()
        print("=" * 74)
        print("RECONCILIATION against the figures you passed")
        print("=" * 74)
        for want in expected_list:
            hits = reconcile(want, ledger["buckets"])
            print(f"  {want:,}   (source records - this = "
                  f"{src['records'] - want:+,})")
            if hits:
                for dropped in hits[:3]:
                    what = " - ".join(f"{d} ({ledger['buckets'][d]:,})" for d in dropped)
                    print(f"           = {src['records']:,} - ({what})")
                    print(f"           = {want:,}")
                if len(hits) > 3:
                    print(f"           ... {len(hits) - 3} more combinations")
            else:
                print("           NO combination of ledger buckets equals this")
                print("           -> different corpus/edition, or an unexplained gap")
    print()
    print("=" * 74)
    print("CONSERVATION CHECKS")
    print("=" * 74)
    if not fails:
        for line in ("C1 entry records == content rows",
                     "C2 every source entry has a row",
                     "C3 every alias key is representable",
                     "C4 no skipped record holds a dictionary entry",
                     "C5 no alias target dropped",
                     "C6 no row without a source record",
                     "C7 sequence 0..N-1 contiguous",
                     "C8 no expression both content row and redirect row",
                     "C9 no conflicting duplicate redirect rows"):
            print(f"  [OK] {line}")
        print()
        print(f"VERDICT: ledger closed -- 0 of {src['records']:,} source records "
              f"unaccounted for; {pkg['rows']:,} package rows.")
        return 0
    for code, msg, samples in fails:
        print(f"  [{code}] {msg}")
        for s in samples[:10]:
            print(f"          {s!r}")
        if len(samples) > 10:
            print(f"          ... and {len(samples) - 10} more")
    print()
    print(f"VERDICT: {len(fails)} problem(s) -- see the codes above.")
    return 1


# ----------------------------------------------------------------------- mdx
def mdx_note(mdx_path, src_records):
    """num_entries as the MDX header itself declares it, for the same corpus."""
    try:
        from mdict_utils.reader import MDX
    except ImportError:
        return (f"mdx header : mdict-utils not installed; cannot read num_entries "
                f"from {os.path.basename(mdx_path)}")
    try:
        n = MDX(mdx_path).num_entries
    except Exception as exc:  # noqa: BLE001 - reader problems are not our bug
        return f"mdx header : could not read {os.path.basename(mdx_path)}: {exc!r}"
    return (f"mdx header   : num_entries = {n:,}   unpacked records = "
            f"{src_records:,}   delta = {src_records - n:+,}")


# ------------------------------------------------------------------ self-test
def _row(expr, score, gloss, seq):
    return [expr, "", "", "", score, gloss, seq, ""]


def self_test():
    """Ledger arithmetic + failure codes on a 14-record fixture. Needs no data."""
    import tempfile

    entry = '<div class="ldoceEntry"><div class="entry_content">DEF</div></div>'
    # classified "skip" (nothing in the first 8000 chars) but a full article body
    # follows -- exactly the shape a silent drop would have
    buried = "<!--" + "x" * 8100 + "-->" + entry
    sc = [{"type": "structured-content", "content": ["DEF"]}]
    with tempfile.TemporaryDirectory() as tmp:
        src_path = os.path.join(tmp, "src.txt")
        records = [("alpha", entry), ("alpha", entry), ("beta", entry),
                   ("gamma", "@@@LINK=beta"), ("delta", "@@@LINK=beta"),
                   ("delta", "@@@LINK=beta"), ("epsilon", "@@@LINK="),
                   ("zeta", "@@@LINK=zeta"), ("eta", "@@@LINK=nowhere"),
                   ("beta", "@@@LINK=alpha"), ("ACTIV:TOPIC X", entry),
                   ("ldoce001jpg", "<img>"), ("", entry), ("weird-page", buried)]
        with io.open(src_path, "w", encoding="utf-8") as h:
            for key, body in records:
                h.write(f"{key}\n{body}\n</>\n")

        pkg_path = os.path.join(tmp, "pkg.zip")
        with zipfile.ZipFile(pkg_path, "w") as z:
            z.writestr("term_bank_1.json", json.dumps([
                _row("alpha", C.ENTRY_SCORE, sc, 0),
                _row("alpha", C.ENTRY_SCORE, sc, 1),
                _row("beta", C.ENTRY_SCORE, sc, 2),
                _row("gamma", C.REDIRECT_SCORE, [["beta", ["redirect"]]], 3),
                _row("delta", C.REDIRECT_SCORE, [["beta", ["redirect"]]], 4),
            ]))
        src, pkg = scan_source(src_path), scan_package(pkg_path)
        led = build_ledger(src, pkg)
        codes = {c for c, _, _ in check(src, pkg, led)}
        assert src["records"] == 14, src["records"]
        assert src["kinds"]["entry"] == 3 and src["kinds"]["redirect"] == 7
        assert src["kinds"]["skip"] == 4, src["kinds"]["skip"]
        assert led["collapsed"] == 1 and led["folded"] == 0
        assert led["rows_written"] == 2 and led["shadowed"] == 1
        assert led["residual"] == 0, led["buckets"]
        # C3: `eta` has no row at all. C4: a skipped record carries an article.
        assert codes == {"C3", "C4"}, codes
        print(f"[self-test] fixture: {src['records']} records, residual "
              f"{led['residual']}, failures {sorted(codes)}")

        # the reconciler resolves an outside count to a named bucket, and refuses
        # to invent an explanation for a number that is no subset of the ledger
        buckets = {"a": 100, "b": 7, "c": 1907}
        assert reconcile(107, buckets) == [["c"]]
        assert not reconcile(999, buckets)
        print("[self-test] reconciler: subset found / bogus rejected")

        # give `eta` its row: the package side is then clean, and only the
        # source-side skip policy (C4) can still be failing
        pkg2 = os.path.join(tmp, "pkg2.zip")
        with zipfile.ZipFile(pkg2, "w") as z:
            z.writestr("term_bank_1.json", json.dumps([
                _row("alpha", C.ENTRY_SCORE, sc, 0),
                _row("alpha", C.ENTRY_SCORE, sc, 1),
                _row("beta", C.ENTRY_SCORE, sc, 2),
                _row("gamma", C.REDIRECT_SCORE, [["beta", ["redirect"]]], 3),
                _row("delta", C.REDIRECT_SCORE, [["beta", ["redirect"]]], 4),
                _row("eta", C.REDIRECT_SCORE, [["alpha", ["redirect"]]], 5),
            ]))
        pkgd2 = scan_package(pkg2)
        led2 = build_ledger(src, pkgd2)
        codes2 = {c for c, _, _ in check(src, pkgd2, led2)}
        assert codes2 == {"C4"}, codes2
        assert led2["residual"] == 0 and led2["unresolved"] == set()
        print("[self-test] repaired package: unresolved 0, residual 0, "
              f"leftover {sorted(codes2)}")

        # negative test: a package that quietly lost rows MUST trip the gate
        # (an audit that can only pass is not an audit -- HANDOVER pitfall 63)
        pkg3 = os.path.join(tmp, "pkg3.zip")
        with zipfile.ZipFile(pkg3, "w") as z:
            z.writestr("term_bank_1.json", json.dumps([
                _row("alpha", C.ENTRY_SCORE, sc, 0),
                _row("gamma", C.REDIRECT_SCORE, [["beta", ["redirect"]]], 1),
                _row("delta", C.REDIRECT_SCORE, [["beta", ["redirect"]]], 2),
            ]))
        pkgd3 = scan_package(pkg3)
        codes3 = {c for c, _, _ in check(src, pkgd3, build_ledger(src, pkgd3))}
        assert {"C1", "C2", "C3"} <= codes3, codes3   # C4 is source-side, always on
        print(f"[self-test] negative test: dropped rows -> {sorted(codes3)}")
    print("[self-test] OK")
    return 0


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sidecar", default=DEFAULT_SRC)
    ap.add_argument("--package", default=DEFAULT_PKG)
    ap.add_argument("--mdx", default=None,
                    help="original .mdx, to compare the header's num_entries")
    ap.add_argument("--expect-total", action="append", type=int, default=[],
                    metavar="N", help="third-party count to reconcile "
                    "(repeatable, e.g. 283110)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    for path, what in ((args.sidecar, "unpacked MDX text (extract/*.mdx.txt)"),
                       (args.package, "built Yomitan zip")):
        if not os.path.isfile(path):
            print(f"[FAIL] no {what} at {path}\n"
                  f"       unpack the mdx with:  python -m mdict_utils.unpack "
                  f"<dir> <mdx>\n"
                  f"       (or build the package first with "
                  f"converter/ldoce2yomitan.py)")
            return 2
    src = scan_source(args.sidecar)
    pkg = scan_package(args.package)
    ledger = build_ledger(src, pkg)
    fails = check(src, pkg, ledger)
    note = None
    mdx = args.mdx
    if mdx is None and args.sidecar.lower().endswith(".mdx.txt"):
        mdx = args.sidecar[:-4]
    if mdx and not os.path.isfile(mdx):
        note = f"mdx header   : {mdx} not found, skipped"
    elif mdx:
        note = mdx_note(mdx, src["records"])
    return report(src, pkg, ledger, fails, args.expect_total, note)


if __name__ == "__main__":
    sys.exit(main())
