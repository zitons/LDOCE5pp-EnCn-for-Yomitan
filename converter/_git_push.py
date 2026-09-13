"""Push to GitHub without the credential-manager hang.

Problem (reproduced): `git push` never completes on this machine.
`git credential fill` hangs forever, so git stalls before sending anything. The
credential DOES exist -- Windows Credential Manager holds
`LegacyGeneric:target=git:https://github.com` with user `x-access-token` and a
40-char `ghp_` PAT -- but GitHub Credential Manager waits on an invisible prompt
instead of reading it.

Fix: read the PAT straight out of the credential store with CredRead (no GCM),
write a one-line askpass shim, and run git with `credential.helper=` cleared plus
`GIT_ASKPASS` pointing at the shim. The shim is deleted in a finally block and the
token is scrubbed from any output.

Usage:
    python converter/_git_push.py                 # push current branch to origin
    python converter/_git_push.py --tags          # also push tags
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys

REPO = r"C:\workspace\ldoce"
PROXY = "http://127.0.0.1:7890"
CRED_TARGET = "git:https://github.com"
SHIM = os.path.join(REPO, "converter", "_askpass_tmp.bat")


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
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                   ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    advapi32.CredReadW.restype = wt.BOOL
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    ptr = ctypes.POINTER(CREDENTIAL)()
    if not advapi32.CredReadW(CRED_TARGET, 1, 0, ctypes.byref(ptr)):
        raise SystemExit(f"credential {CRED_TARGET!r} not found "
                         f"(err={ctypes.get_last_error()})")
    c = ptr.contents
    blob = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
    advapi32.CredFree(ptr)
    return blob.decode("utf-16-le")


def main():
    args = sys.argv[1:]
    token = read_pat()
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            cwd=REPO, capture_output=True, text=True).stdout.strip()
    try:
        with open(SHIM, "w", encoding="ascii") as f:
            f.write("@echo " + token + "\r\n")
        env = dict(os.environ)
        env["GIT_ASKPASS"] = SHIM
        env["GIT_TERMINAL_PROMPT"] = "0"
        cmd = ["git", "-c", "credential.helper=", "-c", f"http.proxy={PROXY}",
               "push", "--progress", "origin", branch]
        if "--tags" in args:
            cmd.append("--tags")
        r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True,
                           text=True, timeout=1800)
        out = ((r.stdout or "") + (r.stderr or "")).replace(token, "***")
        print(out[-3000:])
        print("EXIT", r.returncode)
        return r.returncode
    finally:
        try:
            os.remove(SHIM)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
