"""Create the v2026.09.13 tag and GitHub Release, then upload both assets.

Auth: the same CredRead path as _git_push.py (GCM hangs on this machine).
Upload endpoint: uploads.github.com (the normal API asset upload), NOT the repo
push path -- the repo path resets after ~19 s on a 60 MB body, the release asset
endpoint completes.

Usage:
    python converter/_make_release.py --dry-run     # show what would happen
    python converter/_make_release.py               # create tag/release + upload
"""
import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = r"C:\workspace\ldoce"
OWNER_REPO = "zitons/LDOCE5pp-EnCn-for-Yomitan"
TAG = os.environ.get("REL_TAG", "v2026.09.13")
NAME = os.environ.get("REL_NAME", "LDOCE5pp En-Cn for Yomitan — 2026.09.13")
PROXY = "http://127.0.0.1:7890"
NOTES = os.environ.get("REL_NOTES", os.path.join(REPO, "_release_notes.md"))
_assets_env = os.environ.get("REL_ASSETS")
ASSETS = ([p for p in _assets_env.split(";") if p] if _assets_env else [
    os.path.join(REPO, r"yomitan_fixed\verified\bilingual\LDOCE5pp_Yomitan_2026.09.13.zip"),
    os.path.join(REPO, r"yomitan_fixed\verified\mono\LDOCE5pp_Yomitan_2026.09.13_EN.zip"),
])


class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR),
        ("Comment", wt.LPWSTR), ("LastWritten", wt.FILETIME),
        ("CredentialBlobSize", wt.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wt.DWORD), ("AttributeCount", wt.DWORD),
        ("Attributes", ctypes.c_void_p), ("TargetAlias", wt.LPWSTR),
        ("UserName", wt.LPWSTR),
    ]


def read_pat():
    a = ctypes.WinDLL("advapi32", use_last_error=True)
    a.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                            ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    a.CredReadW.restype = wt.BOOL
    a.CredFree.argtypes = [ctypes.c_void_p]
    p = ctypes.POINTER(CREDENTIAL)()
    if not a.CredReadW("git:https://github.com", 1, 0, ctypes.byref(p)):
        raise SystemExit("credential not found")
    c = p.contents
    blob = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
    a.CredFree(p)
    return blob.decode("utf-16-le")


def opener():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": PROXY, "http": PROXY}))


def api(token, method, url, payload=None, raw=None, content_type=None):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        content_type = content_type or "application/json"
    elif raw is not None:
        data = raw
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("User-Agent", "ldoce-release")
    req.add_header("Accept", "application/vnd.github+json")
    if content_type:
        req.add_header("Content-Type", content_type)
    return opener().open(req, timeout=1800)


def main():
    dry = "--dry-run" in sys.argv
    for p in ASSETS:
        if not os.path.exists(p):
            raise SystemExit(f"missing asset: {p}")
    print(f"tag    : {TAG}")
    print(f"name   : {NAME}")
    print(f"notes  : {NOTES} ({os.path.getsize(NOTES)} B)")
    for p in ASSETS:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        print(f"asset  : {os.path.basename(p)}  {os.path.getsize(p):,} B  "
              f"sha256 {h.hexdigest()[:20]}…")
    if dry:
        print("\n--dry-run: nothing created")
        return 0

    token = read_pat()
    base = f"https://api.github.com/repos/{OWNER_REPO}"

    # 1. create the tag ref (points at the pushed main head)
    sha = os.popen(f'git -C "{REPO}" rev-parse main').read().strip()
    try:
        api(token, "POST", f"{base}/git/refs",
            {"ref": f"refs/tags/{TAG}", "sha": sha})
        print(f"[ok] tag {TAG} -> {sha[:12]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 422:
            print(f"[skip] tag {TAG} already exists")
        else:
            raise SystemExit(f"tag failed: {e.code} {body[:300]}")

    # 2. create the release (or reuse an existing one for this tag)
    notes = open(NOTES, encoding="utf-8").read()
    try:
        rel = json.load(api(token, "POST", f"{base}/releases",
                            {"tag_name": TAG, "name": NAME, "body": notes,
                             "draft": False, "prerelease": False}))
        print(f"[ok] release id={rel['id']}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 422:                      # already exists
            rel = json.load(api(token, "GET", f"{base}/releases/tags/{TAG}"))
            print(f"[skip] release exists id={rel['id']}")
        else:
            raise SystemExit(f"release failed: {e.code} {body[:300]}")

    upload_base = rel["upload_url"].split("{")[0]
    existing = {a["name"]: a["id"] for a in rel.get("assets", [])}

    # 3. upload each asset; replace an existing one of the same name
    for p in ASSETS:
        name = os.path.basename(p)
        if name in existing:
            api(token, "DELETE", f"{base}/releases/assets/{existing[name]}")
            print(f"[ok] removed previous {name}")
        raw = open(p, "rb").read()
        url = f"{upload_base}?name={urllib.parse.quote(name)}"
        r = json.load(api(token, "POST", url, raw=raw,
                          content_type="application/zip"))
        print(f"[ok] uploaded {name}  {r['size']:,} B  state={r['state']}")

    # 4. verify the published release
    rel = json.load(api(token, "GET", f"{base}/releases/tags/{TAG}"))
    print(f"\npublished: {rel['html_url']}")
    for a in rel["assets"]:
        print(f"   {a['name']}  {a['size']:,} B")
        print(f"      {a['browser_download_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
