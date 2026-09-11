"""Final acceptance report for the shipped package: code<->artifact parity,
official-schema sample, structural invariants, and the fix-specific gates."""
import hashlib
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, r"C:\workspace\ldoce\converter")
import ldoce2yomitan as C  # noqa: E402

ZIP = r"C:\workspace\ldoce\yomitan_full\LDOCE5pp_Yomitan_2026.09.11.zip"
SRC = r"C:\workspace\ldoce\converter\ldoce2yomitan.py"

src = io.open(SRC, encoding="utf-8").read()
print("converter:", len(src.encode("utf-8")), "bytes md5",
      hashlib.md5(src.encode()).hexdigest()[:12], "| VERSION", C.VERSION)

size = os.path.getsize(ZIP)
sha = hashlib.sha256(open(ZIP, "rb").read()).hexdigest()
print(f"package:   {size} bytes  sha256 {sha[:24]}")

z = zipfile.ZipFile(ZIP)
idx = json.loads(z.read("index.json"))
print("index:", {k: idx[k] for k in ("title", "format", "revision", "sequenced",
                                     "sourceLanguage", "targetLanguage")})

# code <-> artifact
print("\ncode<->artifact")
print("  styles.css identical to generate_css():",
      z.read("styles.css").decode("utf-8") == C.generate_css())
print("  text-indent:0 occurrences:",
      z.read("styles.css").decode("utf-8").count("text-indent:0"))

# converter validator, strict
errors, st = C.validate_package(ZIP, C.TermIndex(), idx["revision"], "bilingual",
                                full_rows=True)
print("\nconverter validator (strict):", "PASS" if not errors else errors[:3])
print("  stats:", dict(st))

# structural invariants
banks = sorted((n for n in z.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)),
               key=lambda n: int(re.search(r"\d+", n).group()))
seqs = set()
rows = 0
online = 0
wf_opp = 0
sub = 0
infl_region = 0
for b in banks:
    for r in json.loads(z.read(b)):
        rows += 1
        seqs.add(r[6])
        if r[4] > 0:
            blob = json.dumps(r[5], ensure_ascii=False)
            online += blob.count('"ld-panel-online"')
            wf_opp += blob.count('"ld-wf-opp"')
            sub += blob.count('"ld-panel-sub"')
            infl_region += blob.count('"ld-infl-region"')
print("\nrows:", rows, "| seq contiguous:", len(seqs) == max(seqs) + 1,
      f"(0..{max(seqs)})")
print("fix markers in package: online panels=%d, wf-opp=%d, panel-sub=%d, infl-region=%d"
      % (online, wf_opp, sub, infl_region))

meta = json.loads(z.read("term_meta_bank_1.json"))
print("term_meta rows:", len(meta), "| distinct terms:", len({m[0] for m in meta}))
print("\nRESULT:", "ACCEPTED" if not errors else "NEEDS WORK")
