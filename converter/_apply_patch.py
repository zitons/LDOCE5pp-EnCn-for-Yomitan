"""Safe patch helper: atomic writes only (temp file + os.replace) so a failure
can never truncate the target again, and every edit is asserted.

Usage: python _apply_patch.py <patch-name>
"""
import hashlib
import io
import os
import subprocess
import sys
import tempfile

P = r"C:\workspace\ldoce\converter\ldoce2yomitan.py"


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
    raw = subprocess.run(["git", "show", ref], cwd=r"C:\workspace\ldoce",
                         capture_output=True).stdout
    d = os.path.dirname(P)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    os.close(fd)
    with open(tmp, "wb") as fh:
        fh.write(raw)
    os.replace(tmp, P)
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
