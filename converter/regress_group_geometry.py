"""Rendered geometry of example GROUPS, measured in Yomitan's real context.

The hierarchy fix (77ccda7) moved a group head out of the example list: the head
is now a sibling BLOCK that takes one small step, and its own <ul> is pulled back
to the parent column so its examples land where every other example does. That is
a CSS-only invariant once the DOM is right, so nothing checked it: regress_hierarchy
proves the DOM shape, but a later tweak to the pull-back (or to the head's step)
would silently put the group's examples on a different column again -- exactly the
defect that started this round (measured l=106 vs l=81 on 'run').

Asserts, on every group head sampled from a built package:

  A. HEAD STEP   -- head.left - its own exlist.left == 1.1em of the head's font
                    size. One gutter step, not the 1.6em example indent and not a
                    second full level.
  B. LIST PARITY -- the group's exlist starts on the same column as a plain
                    exlist that is a sibling of the group.
  C. ITEM PARITY -- the first example of the group starts on the same column as
                    the first example of a sibling plain list.

Requires node + jsdom (scgen_test) and headless Chrome on CDP_TARGET, the same
harness as regress_alignment; exit 2 when they are missing.

Usage: python converter/regress_group_geometry.py <package.zip> [--sample N]
"""
import argparse
import json
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import regress_alignment as RA  # noqa: E402

TOL = 0.8       # px, geometry
STEP_EM = 1.1   # the head's small step, in em

EXPR = r"""
(() => {
  const out = [];
  const L = e => Math.round(e.getBoundingClientRect().left * 100) / 100;
  const cls = e => e.getAttribute('data-sc-class') || '';
  const painted = e => { try { return e.checkVisibility({checkOpacity:true, checkVisibilityCSS:true}); } catch(_) { return true; } };
  const GROUPS = ['ld-gramexa','ld-colloexa'];
  for (const holder of document.querySelectorAll('[data-case]')) {
    const rec = {id: holder.dataset.case, groups: []};
    for (const g of holder.querySelectorAll('[data-sc-class="ld-gramexa"], [data-sc-class="ld-colloexa"]')) {
      if (!painted(g)) continue;
      const list = [...g.children].find(k => cls(k) === 'ld-exlist');
      if (!list) continue;
      const fs = parseFloat(getComputedStyle(g).fontSize) || 0;
      const parent = g.parentElement;
      const sibs = parent ? [...parent.children].filter(k =>
          cls(k) === 'ld-exlist' && painted(k)) : [];
      const firstItem = sel => {
          const li = sel ? [...sel.children].find(k => k.tagName === 'LI' && painted(k)) : null;
          return li ? L(li) : null;
      };
      rec.groups.push({
        head: L(g), list: L(list), fs,
        sibLists: sibs.map(L),
        sibItem: firstItem(sibs[0]),
        ownItem: firstItem(list),
        headText: (g.textContent || '').trim().replace(/\s+/g,' ').slice(0, 30)
      });
    }
    if (rec.groups.length) out.push(rec);
  }
  return JSON.stringify(out);
})()
"""


def rows_with_groups(zip_path, sample):
    z = zipfile.ZipFile(zip_path)
    ids, seen = [], set()
    for n in sorted(z.namelist()):
        if not n.startswith("term_bank_"):
            continue
        for idx, r in enumerate(json.loads(z.read(n))):
            if r[4] <= 0:
                continue
            body = json.dumps(r[5], ensure_ascii=False)
            if "ld-gramexa" not in body and "ld-colloexa" not in body:
                continue
            rid = RA._row_id(r, n, idx)
            if rid in seen:
                continue
            seen.add(rid)
            ids.append(rid)
            if len(ids) >= sample:
                return ids
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip")
    ap.add_argument("--sample", type=int, default=12)
    ap.add_argument("--width", type=int, default=390)
    ap.add_argument("--scgen", default=None)
    ap.add_argument("--popup-css", default=None)
    a = ap.parse_args()

    root = RA.ROOT
    scgen = os.path.abspath(a.scgen or os.environ.get("SCGEN_DIR")
                            or os.path.join(root, "scgen_test"))
    popup = a.popup_css or os.environ.get("HOSHI_POPUP_CSS") \
        or os.path.join(root, "_hoshi", "popup.css")
    if not os.path.isdir(scgen):
        print(f"HARNESS: jsdom generator dir not found: {scgen}")
        return 2
    missing = RA.check_harness(scgen)
    if missing:
        print("HARNESS: cannot run this gate -- prerequisites are missing.\n")
        for what, remedy in missing:
            print(f"  * {what}\n      -> {remedy}")
        return 2

    css = zipfile.ZipFile(a.zip).read("styles.css").decode("utf-8")
    ids = rows_with_groups(a.zip, a.sample)
    print(f"package : {os.path.basename(a.zip)}")
    print(f"sample  : {len(ids)} row(s) carrying a group head")
    if not ids:
        print("nothing to check")
        return 1
    rows = RA.extract(a.zip, ids)

    records = []
    out_html = os.path.join(root, "_gg.html")
    ep = os.path.join(scgen, "_gg_expr.js")
    with open(ep, "w", encoding="utf-8") as f:
        f.write(EXPR)
    items = list(rows.items())
    for start in range(0, len(items), 3):
        part = dict(items[start:start + 3])
        if not RA.build_page(part, css, scgen, a.width,
                             popup if os.path.isfile(popup) else None, out_html):
            print("page build failed")
            return 2
        r = subprocess.run(["node", "cdp.mjs", "file:///" + out_html.replace("\\", "/"),
                            "_gg_expr.js"],
                           capture_output=True, text=True, encoding="utf-8", cwd=scgen,
                           env={**os.environ, "CDP_TARGET": RA.CDP_TARGET})
        if r.returncode != 0:
            print("render failed:", r.stderr[:600])
            return 2
        records += RA._parse_cdp(r.stdout)

    step_bad, list_bad, item_bad = [], [], []
    checked = with_parity = 0
    for rec in records:
        for g in rec["groups"]:
            checked += 1
            expected = STEP_EM * g["fs"]
            step = g["head"] - g["list"]
            if abs(step - expected) > TOL:
                step_bad.append((rec["id"], g["headText"], round(step, 2),
                                 round(expected, 2)))
            if g["sibLists"]:
                with_parity += 1
                delta = g["list"] - g["sibLists"][0]
                if abs(delta) > TOL:
                    list_bad.append((rec["id"], g["headText"], round(g["list"], 2),
                                     round(g["sibLists"][0], 2), round(delta, 2)))
            if g["sibItem"] is not None and g["ownItem"] is not None:
                delta = g["ownItem"] - g["sibItem"]
                if abs(delta) > TOL:
                    item_bad.append((rec["id"], g["headText"], round(delta, 2)))

    print(f"measured: {checked} group head(s), {with_parity} with a plain list beside them")
    print("\nA. head step == 1.1em")
    print(f"   {len(step_bad)} wrong")
    for s in step_bad[:8]:
        print(f"     step={s[2]} expected={s[3]}  {s[1]!r}")
    print("\nB. group list on the plain-example column")
    print(f"   {len(list_bad)} wrong")
    for s in list_bad[:8]:
        print(f"     group={s[2]} plain={s[3]} delta={s[4]}  {s[1]!r}")
    print("\nC. first example in the group on the same column as a plain one")
    print(f"   {len(item_bad)} wrong")
    for s in item_bad[:8]:
        print(f"     delta={s[2]}  {s[1]!r}")

    problems = []
    if not checked:
        problems.append("no group head was measured -- sample too small")
    if with_parity == 0:
        problems.append("no group had a plain sibling list -- parity never checked")
    if step_bad:
        problems.append(f"{len(step_bad)} head(s) not one 1.1em step from their list")
    if list_bad:
        problems.append(f"{len(list_bad)} group list(s) off the example column")
    if item_bad:
        problems.append(f"{len(item_bad)} group item(s) off the example column")
    if problems:
        print("\nGROUP GEOMETRY: FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print("\nGROUP GEOMETRY: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
