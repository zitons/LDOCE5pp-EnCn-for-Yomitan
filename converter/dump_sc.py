"""Dump the structured-content tree of one term row as an indented outline."""
import json
import sys
import zipfile


def walk(node, depth, out, limit):
    pad = "  " * depth
    if isinstance(node, str):
        text = node.strip()
        if text:
            out.append(f"{pad}TXT {text[:110]}")
        return
    if isinstance(node, list):
        for item in node:
            walk(item, depth, out, limit)
        return
    tag = node.get("tag", "?")
    cls = (node.get("data") or {}).get("class", "")
    extra = ""
    if cls:
        extra += f".{cls}"
    if node.get("lang"):
        extra += f"[{node['lang']}]"
    if node.get("title"):
        extra += f"(t:{node['title'][:30]})"
    if node.get("href"):
        extra += f" -> {node['href'][:70]}"
    if node.get("style"):
        extra += f" {{{';'.join(node['style'])}}}"
    out.append(f"{pad}<{tag}{extra}>")
    if len(out) > limit:
        return
    walk(node.get("content", ""), depth + 1, out, limit)


def main():
    zip_path, word, limit = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 400
    zf = zipfile.ZipFile(zip_path)
    for name in zf.namelist():
        if not name.startswith("term_bank_"):
            continue
        for row in json.loads(zf.read(name).decode("utf-8")):
            if row[0] != word:
                continue
            print(f"=== ROW {row[0]!r} tags={row[2]!r} rules={row[3]!r} score={row[4]} seq={row[6]}")
            for item in row[5]:
                if isinstance(item, list):
                    print(f"REDIRECT -> {item}")
                elif item.get("type") == "structured-content":
                    out = []
                    walk(item["content"], 0, out, limit)
                    print("\n".join(out[:limit]))


if __name__ == "__main__":
    main()
