"""Build a Hoshi-Reader-compatible local-audio database from LDOCE5_V_2-15.mdd.

WHAT HOSHI EXPECTS (read from its Kotlin sources, not guessed)
-------------------------------------------------------------
app/src/main/java/moe/antimony/hoshi/features/audio/LocalAudioRepository.kt
    findAudio(term, reading):
        SELECT source, expression, reading, file FROM entries
        WHERE (expression = ? OR reading = ?)          -- if reading is non-blank
        WHERE expression = ?                            -- if reading IS blank
    audioSourcesFromDatabase():
        WHERE lower(file) LIKE '%.mp3' OR '%.opus' OR '%.ogg'
    loadAudio(file):
        SELECT data FROM android WHERE source = ? AND file = ?
LocalAudioResolver.kt
    ranking: expression+reading match > reading match > expression match,
             then by source order (derived from the db itself)
    supported extensions: mp3, opus, ogg
AudioSettings.kt
    LocalAudioPath = "Audio/android.db"   -> the file MUST be named android.db
ImportFileType.LocalAudioDatabase -> extension must be .db

DB SHAPE (same as yomidevs/local-audio-yomichan plugin/db_utils.py)
    entries(id, expression, reading, source, speaker, display, file)
    android(id, file, source, data)      -- data = raw audio bytes

WHAT THIS BUILDS
----------------
Headword pronunciation only (no example audio):
    <a class="speaker amefile|brefile">  and  <a class="PronCodes">
    href="sound://media/english/{ameProns,breProns}/<name>.mp3"
Sources are named `ldoce_ame` / `ldoce_bre` so Hoshi presents two selectable
sources; both are outside its BuiltInPriority list, so it orders them
alphabetically (ame before bre).

`reading` is left NULL: this dictionary has no kana readings, and Hoshi then
takes its `expression = ?` branch, which is exactly the match we want.

`.spx` files are skipped -- Hoshi cannot serve them, and transcoding would add a
dependency for <1% of entries.

Usage
-----
    python converter/build_audio_db.py --limit 300 --out build/audio_sample.db
    python converter/build_audio_db.py --out yomitan_audio/android.db
"""
import argparse
import io
import json
import os
import re
import sqlite3
import sys
import time
import zipfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldoce2yomitan as C  # noqa: E402

SEP = "</>"
# any tag whose attributes carry an audio href, with the class captured
TAG = re.compile(r"<(\w+)([^>]*)>", re.I | re.S)
AUDIO_ATTR = re.compile(
    r'(?:href|data-src-mp3)="(?:sound://)?media/english/(ameProns|breProns)/([^"]+\.mp3)"',
    re.I)
CLASS = re.compile(r'class="([^"]*)"', re.I)
HEAD_ANY = re.compile(r'class="([^"]*\bHead\b[^"]*)"', re.I)

SRC_AUDIO_SOURCE = {"ameProns": "ldoce_ame", "breProns": "ldoce_bre"}

SCHEMA = """
CREATE TABLE entries (
    id integer PRIMARY KEY NOT NULL,
    expression text NOT NULL,
    reading text,
    source text NOT NULL,
    speaker text,
    display text,
    file text NOT NULL
);
CREATE TABLE android (
    id integer PRIMARY KEY NOT NULL,
    file text NOT NULL,
    source text NOT NULL,
    data blob NOT NULL
);
CREATE INDEX idx_expression ON entries(expression, reading);
CREATE INDEX idx_expr_source ON entries(expression, reading, source);
CREATE INDEX idx_android ON android(file, source);
"""


def head_region(blob):
    """Head block only: from a class containing the token `Head` to the first
    definition container. `class="Head suppressedLEXVAR"` must match too -- an
    exact `class="Head"` test missed those and cost 16 points of coverage."""
    m = HEAD_ANY.search(blob)
    region = blob[m.start():] if m else blob
    for marker in ('class="Sense"', 'class="DEF"', 'class="lm5pp_popup"'):
        idx = region.find(marker)
        if idx > 0:
            return region[:idx]
    return region


def audio_in(region):
    """[(source_id, filename)] for headword audio in this region."""
    out = []
    for m in TAG.finditer(region):
        attrs = m.group(2)
        h = AUDIO_ATTR.search(attrs)
        if not h:
            continue
        d, name = h.group(1), h.group(2)
        out.append((SRC_AUDIO_SOURCE[d], name))
    return out


def scan_source(src, limit=None, progress_every=50000):
    """key -> {source_id: filename} for every source record with headword audio."""
    mapping = {}
    variants = {}
    seen_records = 0
    records = 0
    alias = 0
    with_audio = 0
    buf = []
    t0 = time.time()
    with io.open(src, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.rstrip("\n") != SEP:
                buf.append(line)
                continue
            # ---- end of record ----
            key = next((ln.strip() for ln in buf if ln.strip()), None)
            if key is not None:
                body = [ln for ln in buf if ln.strip() and ln.strip() != key]
                is_alias = bool(body) and all(ln.strip().startswith("@@@LINK=")
                                              for ln in body)
                if is_alias:
                    alias += 1
                elif "<" in "".join(buf):
                    records += 1
                    blob = "".join(buf)
                    hits = audio_in(head_region(blob))
                    if hits:
                        first = {}
                        for sid, name in hits:
                            first.setdefault(sid, name)
                        mapping[key] = first
                        # also index the HWD text and normalised key forms, since
                        # the dictionary's expression may differ from the raw key
                        for form in key_forms(key, blob):
                            variants.setdefault(form, first)
                        with_audio += 1
                    if limit and records >= limit:
                        break
            buf = []
            seen_records += 1
            if seen_records % progress_every == 0:
                print(f"    ... {seen_records:,} keys read, {records:,} entries, "
                      f"{with_audio:,} with audio, {time.time()-t0:.0f}s", flush=True)
    if buf:
        key = next((ln.strip() for ln in buf if ln.strip()), None)
        if key and "<" in "".join(buf):
            hits = audio_in(head_region("".join(buf)))
            if hits:
                first = {}
                for sid, name in hits:
                    first.setdefault(sid, name)
                mapping[key] = first
                for form in key_forms(key, "".join(buf)):
                    variants.setdefault(form, first)
    print(f"  source scan: records={records:,} alias={alias:,} "
          f"with_headword_audio={with_audio:,} ({time.time()-t0:.0f}s)")
    return variants


def key_forms(key, blob):
    """Candidate expressions a dictionary row might carry for this record."""
    forms = set()
    base = key.strip()
    forms.add(base)
    forms.add(C.strip_invisible(base).strip())
    forms.add(C.collapse_ws(base))
    forms.add(base.casefold())
    # the HWD text inside the head block is the authoritative headword
    m = re.search(r'class="[^"]*\bHWD\b[^"]*"[^>]*>(.*?)</span>', blob, re.S)
    if m:
        hwd = re.sub(r"<[^>]+>", "", m.group(1))
        hwd = C.strip_invisible(hwd).strip()
        if hwd:
            forms.add(hwd)
            forms.add(C.collapse_ws(hwd))
    return {f for f in forms if f}


def dictionary_expressions(zip_path, limit=None):
    """The expression set users can actually look up (score > 0 rows)."""
    out = []
    seen = set()
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if not re.fullmatch(r"term_bank_\d+\.json", n):
                continue
            for r in json.loads(z.read(n)):
                if r[4] <= 0:
                    continue
                if r[0] in seen:
                    continue
                seen.add(r[0])
                out.append(r[0])
                if limit and len(out) >= limit:
                    return out
    return out


def collect_needed_files(rows):
    need = {}
    for _expr, sid, name in rows:
        need.setdefault(sid, set()).add(name)
    return need


def build(mdd_path, out_path, zip_path, src, limit=None, progress_every=20000):
    print(f"[1/5] scanning source records for headword audio ...", flush=True)
    variants = scan_source(src, limit=None if not limit else None)

    print(f"[2/5] reading dictionary expressions ...", flush=True)
    exprs = dictionary_expressions(zip_path)
    print(f"  expressions in package: {len(exprs):,}")
    if limit:
        exprs = exprs[:limit]
        print(f"  limited to: {len(exprs):,}")

    print(f"[3/5] matching expressions to audio ...", flush=True)
    rows = []
    unmatched = []
    for e in exprs:
        hit = None
        for form in (e, C.strip_invisible(e).strip(), C.collapse_ws(e), e.casefold()):
            if form in variants:
                hit = variants[form]
                break
        if not hit:
            unmatched.append(e)
            continue
        for sid, name in hit.items():
            rows.append((e, sid, name))
    print(f"  rows: {len(rows):,} for {len(exprs)-len(unmatched):,} expressions "
          f"({(len(exprs)-len(unmatched))*100.0/max(len(exprs),1):.1f}% matched)")
    if unmatched:
        print(f"  unmatched sample: {unmatched[:10]}")

    need = collect_needed_files(rows)
    total_files = sum(len(v) for v in need.values())
    print(f"  distinct audio files needed: {total_files:,} "
          f"({ {k: len(v) for k, v in need.items()} })")

    print(f"[4/5] extracting audio from mdd ...", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".part"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=OFF")

    from mdict_utils.reader import MDD as _MDD
    m = _MDD(mdd_path)
    dir_of = {sid: d for d, sid in SRC_AUDIO_SOURCE.items()}
    want = set()
    for sid, names in need.items():
        for nm in names:
            want.add((sid, nm))

    # file -> bytes for the ones referenced
    blobs = {}
    scanned = 0
    t0 = time.time()
    for key, data in m.items():
        scanned += 1
        name = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
        name = name.replace("\\", "/").strip("/")
        parts = name.split("/")
        if len(parts) < 2:
            continue
        fname = parts[-1]
        d = parts[-2]
        sid = SRC_AUDIO_SOURCE.get(d)
        if sid is None:
            continue
        if (sid, fname) in want:
            blobs[(sid, fname)] = data
        if scanned % progress_every == 0:
            print(f"    mdd scanned {scanned:,} entries, matched {len(blobs):,} "
                  f"files ({time.time()-t0:.0f}s)", flush=True)
    print(f"  mdd scan done: {scanned:,} entries, {len(blobs):,} audio blobs "
          f"({time.time()-t0:.0f}s)")

    print(f"[5/5] writing database ...", flush=True)
    # Only write rows whose blob we ACTUALLY extracted. The source HTML references
    # a few files that are absent from the mdd (4 words x 2 accents, e.g.
    # ldoce6bulgur_wheat.mp3); keeping those rows would make Hoshi return a match
    # and then fail to load any audio, so they are dropped instead.
    kept = 0
    dropped = []
    for (expr, sid, name) in rows:
        if (sid, name) not in blobs:
            dropped.append((expr, sid, name))
            continue
        conn.execute(
            "INSERT INTO entries (expression, reading, source, speaker, display, file)"
            " VALUES (?,?,?,?,?,?)", (expr, None, sid, None, None, name))
        kept += 1
    inserted = 0
    for (sid, name), data in blobs.items():
        conn.execute("INSERT INTO android (file, source, data) VALUES (?,?,?)",
                     (name, sid, data))
        inserted += 1
    conn.commit()
    # sanity: no entry may lack a blob once written
    orphan = conn.execute("""
        SELECT COUNT(*) FROM entries e WHERE NOT EXISTS (
            SELECT 1 FROM android a WHERE a.source = e.source AND a.file = e.file)
    """).fetchone()[0]
    conn.close()
    os.replace(tmp, out_path)
    size = os.path.getsize(out_path)
    print(f"  db written: {out_path}  {size:,} B ({size/1048576:.1f} MiB)")
    print(f"  entries rows: {kept:,}   android blobs: {inserted:,}   orphans: {orphan}")
    if dropped:
        print(f"  dropped {len(dropped)} row(s) whose audio is missing from the mdd: "
              f"{sorted({d[0] for d in dropped})}")
    assert orphan == 0, "entries without a blob would break playback"
    return {"rows": kept, "blobs": inserted, "size": size,
            "matched_exprs": len(exprs) - len(unmatched),
            "exprs": len(exprs), "unmatched": unmatched[:20],
            "dropped_rows": len(dropped)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mdd", default=r"C:\workspace\ldoce\LDOCE5_V_2-15.mdd")
    ap.add_argument("--src", default=r"C:\workspace\ldoce\extract\LDOCE5++ V 2-15.mdx.txt")
    ap.add_argument("--zip", default=r"C:\workspace\ldoce\yomitan_full"
                                     r"\LDOCE5pp_Yomitan_2026.09.13.zip")
    ap.add_argument("--out", default=r"C:\workspace\ldoce\yomitan_audio\android.db")
    ap.add_argument("--limit", type=int, default=None,
                    help="only this many dictionary expressions (sampling)")
    args = ap.parse_args()
    stats = build(args.mdd, args.out, args.zip, args.src, limit=args.limit)
    print("\nRESULT:", json.dumps(stats, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
