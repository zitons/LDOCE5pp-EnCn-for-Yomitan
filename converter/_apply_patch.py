"""Safe patch helper: atomic writes only (temp file + os.replace) so a failure
can never truncate the target again, and every edit is asserted.

Usage: python _apply_patch.py <patch-name>
"""
import hashlib
import io
import io
import os
import subprocess
import sys
import tempfile

# Derived from this file's own location, not a literal. This module is the patch
# and restore framework for the converter, so a hardcoded absolute path is the
# worst possible place for one: run from another checkout it would patch, and
# restore_from_git() would read, that checkout's converter instead of this one --
# exactly the "auditing the wrong object" hazard the sweep of 2026-10-09 was
# meant to remove.
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "ldoce2yomitan.py")
REPO = os.path.dirname(HERE)


def read():
    with io.open(P, encoding="utf-8") as fh:
        return fh.read()


def write_atomic(text):
    d = os.path.dirname(P)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    os.close(fd)
    try:
        with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, P)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def restore_from_git(ref="HEAD:converter/ldoce2yomitan.py"):
    proc = subprocess.run(["git", "show", ref], cwd=REPO,
                          capture_output=True)
    # The return code used to be discarded here. A bad ref makes git print nothing
    # on stdout, so `raw` was b"" and the os.replace below wrote those 0 bytes over
    # the live converter -- the exact truncation this module's docstring says can
    # never happen. Verified: bad ref -> returncode 128, stdout 0 bytes.
    if proc.returncode != 0 or not proc.stdout:
        raise SystemExit(f"git show {ref} failed (exit {proc.returncode}): "
                         f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    raw = proc.stdout
    d = os.path.dirname(P)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    os.close(fd)
    try:
        with open(tmp, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, P)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return raw


def apply(name, pairs):
    s = read()
    before = hashlib.md5(s.encode("utf-8")).hexdigest()
    for i, (old, new, count) in enumerate(pairs, 1):
        n = s.count(old)
        assert n == count, f"[{name}] edit {i}: found {n}, expected {count}\n{old[:200]}"
        s = s.replace(old, new)
    write_atomic(s)
    after = hashlib.md5(s.encode("utf-8")).hexdigest()
    print(f"[{name}] {before[:10]} -> {after[:10]}  bytes={len(s.encode('utf-8'))}")
    return s


if __name__ == "__main__":
    if sys.argv[1] == "restore":
        raw = restore_from_git()
        print(f"restored {len(raw)} bytes from git HEAD")
