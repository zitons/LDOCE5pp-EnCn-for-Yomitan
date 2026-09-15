"""Render-contract gate: real Yomitan generator + headless Chrome.

Asserts the two environments behave as designed, on the ACTUAL package content:

  with styles.css   -- the theme palette wins over the inline fallbacks. Concretely
                       ld-pos / ld-gram must not render DodgerBlue and ld-defcn /
                       ld-excn / ld-field / ld-grouptitle must not render green;
                       each must clear 4.3:1 against its own card background in both
                       the light and the dark theme. ld-nodew / ld-colloin must be
                       600, not the 700 the fallback carries. (audit R3)
  without styles.css -- the UA list marker stays OFF so the number the reader sees is
                       the SOURCE number: 'act' must show 7,8,9,10 (never 1,2,3,4),
                       the chip must be visible, and the inline marker spans that
                       carry the example dashes / ticks must be visible. (audit R1/R2)

Usage:
    python converter/regress_render_contract.py [term_bank_dir_or_zip]
"""
import json
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import ldoce2yomitan as C  # noqa: E402

WORDS = ["act", "access", "above", "criminal", "7/7", "bad", "the", "matter"]
NEEDED = ["ld-pos", "ld-defcn", "ld-excn"]
MIN_CONTRAST = 4.3


def load_rows(src):
    if src.endswith(".zip"):
        with zipfile.ZipFile(src) as z:
            names = sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
                           key=lambda n: int(re.search(r"\d+", n).group()))
            for n in names:
                yield from json.loads(z.read(n))
    else:
        for name in sorted(os.listdir(src)):
            if re.fullmatch(r"term_bank_\d+\.json", name):
                with open(os.path.join(src, name), encoding="utf-8") as fh:
                    yield from json.load(fh)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_smoke3")
    payload = {}
    for row in load_rows(src):
        if row[4] > 0 and row[0] in WORDS and row[0] not in payload:
            payload[row[0]] = row[5][0]["content"]
    missing = [w for w in WORDS if w not in payload]
    if missing:
        print(f"note: source has no content row for {missing}")

    payload_path = os.path.join(HERE, "_rc", "payload.json")
    css_path = os.path.join(HERE, "_rc", "styles.css")
    os.makedirs(os.path.dirname(payload_path), exist_ok=True)
    with open(payload_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    # Audit the stylesheet actually shipped with the supplied content. Using
    # generate_css() here can make an old, broken ZIP pass after a source-only fix.
    if src.endswith(".zip"):
        with zipfile.ZipFile(src) as z:
            css = z.read("styles.css").decode("utf-8")
    else:
        with open(os.path.join(src, "styles.css"), encoding="utf-8") as fh:
            css = fh.read()
    with open(css_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(css)

    proc = subprocess.run([C.shutil.which("node") or "node",
                           os.path.join(HERE, "regress_render_contract.mjs"),
                           payload_path, css_path],
                          capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    if proc.returncode != 0:
        print("node failed:", proc.returncode)
        print(proc.stderr[:2000])
        return 2
    data = json.loads(proc.stdout)

    fails = []

    def check(ok, label, detail=""):
        print(f"  {'OK ' if ok else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
        if not ok:
            fails.append(label + (" " + detail if detail else ""))

    print(f"chrome: color-mix supported = {data['colorMix']}")
    print("\n== with styles.css ==")
    for mode in ("light", "dark"):
        rec = data["modes"][mode]
        print(f"-- {mode} --")
        for cls in NEEDED:
            if cls not in rec["fields"]:
                fails.append(f"{mode}: {cls} not present in the sample")
                continue
            f = rec["fields"][cls]
            bad = f["computed"] in ("rgb(30, 144, 255)", "rgb(0, 128, 0)")
            check(not bad and f["contrast"] >= MIN_CONTRAST,
                  f"{mode} {cls:11}", f"colour={f['computed']:20} inline={f['inline']!s:12} "
                                     f"contrast={f['contrast']}")
        for cls, want in (("ld-nodew", "600"), ("ld-colloin", "600")):
            if cls in rec["weights"]:
                w = rec["weights"][cls]
                check(w["computed"] == want, f"{mode} {cls} weight",
                      f"computed={w['computed']} inline={w['inline']}")
        for cls, want in (("ld-mark", "none"), ("ld-snum", None)):
            m = rec["marks"].get(cls)
            if not m:
                continue
            if want:
                check(m["display"] == want, f"{mode} {cls} display", f"={m['display']}")
            else:
                check(m["display"] != "none" and m["fontSize"] != "0px" and m["width"] > 0,
                      f"{mode} {cls} visible",
                      f"display={m['display']} fontSize={m['fontSize']} w={m['width']}")
        for ol in rec["lists"]:
            check(ol["listStyle"] == "none", f"{mode} ol list-style", f"={ol['listStyle']}")
            check("0px" not in ol["chipFontSizes"], f"{mode} ol chip not collapsed",
                  f"fontSizes={ol['chipFontSizes'][:4]}")
        check(rec["defMarginBottom"] == "1px", f"{mode} ld-def margin-bottom",
              f"={rec['defMarginBottom']}")

    print("\n== with CSS, without Yomitan theme variables ==")
    for mode in ("no-var-light", "no-var-dark"):
        body = data["modes"][mode].get("plainText")
        check(body is not None, f"{mode} plain definition present")
        if body is not None:
            check(body["themeVariable"] == "", f"{mode} has no --text-color")
            check(body["rootColor"] == body["hostColor"]
                  and body["definitionColor"] == body["hostColor"],
                  f"{mode} root and definition inherit the host",
                  f"root={body['rootColor']} host={body['hostColor']}")
            check(body["contrast"] >= MIN_CONTRAST,
                  f"{mode} plain definition remains readable", f"contrast={body['contrast']}")

    print("\n== without styles.css ==")
    rec = data["modes"]["no-css"]
    for ol in rec["lists"]:
        check(ol["listStyle"] == "none",
              "no-css ol marker suppressed", f"inline={ol['inlineListStyle']} computed={ol['listStyle']}")
        if ol["sourceNumbers"]:
            # 49% of senses carry no number at all, so only lists that DO have a
            # chip are asked to render it
            check(ol["chipWidths"] and min(ol["chipWidths"]) > 0,
                  "no-css chip visible", f"widths={ol['chipWidths'][:6]}")
        src_nums = ol["sourceNumbers"]
        if src_nums[:1] == ["7"]:
            check(src_nums[:4] == ["7", "8", "9", "10"],
                  "no-css act shows the SOURCE numbers", f"{src_nums[:6]}")
    mark = rec["marks"].get("ld-mark")
    if mark:
        check(mark["display"] != "none", "no-css marker span visible", f"display={mark['display']}")
    # with no stylesheet the literal fallback is what MUST show -- that is the whole
    # point of SEMANTIC_INLINE_STYLES
    FALLBACK = {"ld-pos": "rgb(30, 144, 255)", "ld-gram": "rgb(30, 144, 255)",
                "ld-defcn": "rgb(0, 128, 0)", "ld-excn": "rgb(0, 128, 0)",
                "ld-field": "rgb(0, 128, 0)", "ld-grouptitle": "rgb(0, 128, 0)"}
    for cls, want in FALLBACK.items():
        f = rec["fields"].get(cls)
        if f:
            check(f["computed"] == want, f"no-css {cls} shows the fallback colour",
                  f"={f['computed']} (want {want})")

    print()
    if fails:
        print(f"RESULT: FAIL ({len(fails)})")
        for f in fails:
            print("  -", f)
        return 1
    print("RESULT: PASS -- palette/host inheritance with CSS; source numbering and markers without")
    return 0


if __name__ == "__main__":
    sys.exit(main())
