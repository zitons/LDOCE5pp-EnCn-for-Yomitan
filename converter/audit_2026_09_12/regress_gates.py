"""Post-fix regression gates for audit A1 (publish gate) and A6 (sequence check).

Deterministic and self-contained: A1 is exercised by injecting a validator
failure into build() (the real CLI path then runs through main()), A6 by four
hand-built sequence fixtures. Run from the repo root:

    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -u converter/audit_2026_09_12/regress_gates.py

Non-zero exit only if a gate fails.
"""
import contextlib
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(r"C:\workspace\ldoce")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "converter"))
import ldoce2yomitan as M  # noqa: E402

FAILURES = []


def check(label, ok, detail=""):
    print(f"[{'OK' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- A1 gate ---
# A fresh directory per run: deleting an old one trips the sandbox's
# recycle-bin fail-closed policy, and nothing here needs a clean slate.
GATE_DIR = OUT / f"regress_publish_gate/{time.strftime('%Y%m%d-%H%M%S')}"
GATE_DIR.mkdir(parents=True, exist_ok=True)

fixture = OUT / "be_fixture.mdx.txt"
build_dir = GATE_DIR / "out"
good = M.build(str(fixture), str(build_dir), mode="mono", revision="gate-ok",
               show_progress=False)
good_sha = sha(good)
check("A1 base build published a package", Path(good).exists(), Path(good).name)

# Second build into the same directory, with validation forced to fail.
real_validate = M.validate_package
injected = []


def failing_validate(*a, **kw):
    injected.append(1)
    return (["injected: term_bank_1.json: mono build contains CJK text"],
            {"rows": 1, "term_banks": 1, "query_links": 0, "dangling_links": 0,
             "redirect_items": 0, "sequence_ok": 1, "freq_rows": 2})


buf = io.StringIO()
M.validate_package = failing_validate
try:
    with contextlib.redirect_stdout(buf):
        M.build(str(fixture), str(build_dir), mode="mono", revision="gate-fail",
                show_progress=False)
    raised = False
except M.BuildValidationError as exc:
    raised = True
    message = str(exc)
finally:
    M.validate_package = real_validate
log = buf.getvalue()

check("A1 failing build raises BuildValidationError", raised)
check("A1 failing build logged [FAIL]", "[FAIL]" in log)
check("A1 failing build never printed [OK] Dictionary package",
      "[OK] Dictionary package" not in log)
# The cleanup itself is os.remove() on a file this process just created. Some
# sandboxes intercept deletes (fail-closed recycle-bin policy) and the removal
# silently degrades -- probe the capability so the gate reports an environment
# limit instead of a false code failure.
probe = build_dir / "_delete_probe.tmp"
probe.write_bytes(b"x")
try:
    os.remove(probe)
    deletes_work = True
except OSError as exc:
    deletes_work = False
    del exc
leftovers = [p.name for p in build_dir.glob("*.part")]
if deletes_work:
    check("A1 nothing left under a *.part name", not leftovers, str(leftovers))
else:
    print("[SKIP] A1 *.part cleanup: this sandbox blocks file deletion "
          f"(left: {leftovers})")
check("A1 previous good package survived, byte-identical",
      Path(good).exists() and sha(good) == good_sha, good_sha[:16])
check("A1 error message names the failure", bool(message), message)

# The CLI must translate that into a non-zero exit code.
M.validate_package = failing_validate
try:
    rc = M.main(["-i", str(fixture), "-o", str(build_dir), "-m", "mono",
                 "--no-progress", "--revision", "gate-cli"])
finally:
    M.validate_package = real_validate
check("A1 CLI exits non-zero on validation failure", rc not in (0, None), f"rc={rc}")
check("A1 CLI left the good package untouched",
      Path(good).exists() and sha(good) == good_sha)
check("A1 good build still passes the real validator after the gate ran",
      not real_validate(good, M.TermIndex(), "gate-ok", "mono",
                        full_rows=False)[0])

# ----------------------------------------------------------- A6 sequences ---
IDX = {"title": "audit fixture", "format": 3, "revision": "audit",
       "sequenced": True, "sourceLanguage": "en", "targetLanguage": "zh"}


def seq_fixture(name, sequences):
    path = GATE_DIR / name
    rows = [[f"w{i}", "", "", "", 10,
             [{"type": "structured-content",
               "content": {"tag": "div", "content": f"w{i}"}}], s, ""]
            for i, s in enumerate(sequences)]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps(IDX))
        z.writestr("tag_bank_1.json", "[]")
        z.writestr("styles.css", "")
        z.writestr("term_bank_1.json", json.dumps(rows))
    return path


for name, seqs, should_fail in (
        ("seq_ok.zip", [0, 1, 2], False),
        ("seq_duplicate.zip", [0, 0, 1], True),
        ("seq_duplicate_only.zip", [0, 0], True),
        ("seq_no_zero.zip", [1, 2], True),
        ("seq_gap.zip", [0, 2], True),
):
    errors, stats = M.validate_package(str(seq_fixture(name, seqs)),
                                       M.TermIndex(), "audit", "bilingual")
    got = bool(errors)
    check(f"A6 {name}: sequences {seqs} -> "
          f"{'rejected' if should_fail else 'accepted'}", got == should_fail,
          (errors[:1] or [f"seq_ok={stats['sequence_ok']}"])[0])

# A6 must still accept a well-formed evenly-filled range.
errors, stats = M.validate_package(str(seq_fixture("seq_large.zip", range(40))),
                                   M.TermIndex(), "audit", "bilingual")
check("A6 40 gapless rows accepted", not errors and stats["sequence_ok"] == 1)

print()
if FAILURES:
    print(f"{len(FAILURES)} gate(s) FAILED: {FAILURES}")
    sys.exit(1)
print("all gates passed")
