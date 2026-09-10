"""Quick preview: render Yomitan structured-content rows from a term bank
into a standalone HTML page (mirroring Yomitan's generator semantics) so the
build can be eyeballed in a browser."""
import json
import sys
import html as html_mod
from urllib.parse import unquote

ATTR_ESCAPE = html_mod.escape


def sc_to_html(node):
    if isinstance(node, str):
        return ATTR_ESCAPE(node)
    if isinstance(node, list):
        return "".join(sc_to_html(x) for x in node)
    tag = node.get("tag")
    if tag == "br":
        return "<br>"
    attrs = []
    data = node.get("data") or {}
    for k, v in data.items():
        attrs.append(f'data-sc-{k.lower()}="{ATTR_ESCAPE(str(v))}"')
    if node.get("lang"):
        attrs.append(f'lang="{ATTR_ESCAPE(node["lang"])}"')
    if node.get("title"):
        attrs.append(f'title="{ATTR_ESCAPE(node["title"])}"')
    if node.get("href"):
        href = node["href"]
        if href.startswith("?query="):
            target = unquote(href[len("?query="):].split("&")[0])
            href = f"#{ATTR_ESCAPE(target)}"
        attrs.append(f'href="{ATTR_ESCAPE(href)}"')
    if node.get("style"):
        css = ";".join(f"{k}:{v}" for k, v in node["style"].items())
        attrs.append(f'style="{ATTR_ESCAPE(css)}"')
    if node.get("open"):
        attrs.append("open")
    inner = sc_to_html(node.get("content", "")) if "content" in node else ""
    return f"<{tag} {' '.join(attrs)}>{inner}</{tag}>"


def main():
    zip_path = sys.argv[1]
    words = set(w.lower() for w in sys.argv[2:])
    import zipfile
    zf = zipfile.ZipFile(zip_path)
    css = zf.read("styles.css").decode("utf-8")
    parts = []
    for name in zf.namelist():
        if not name.startswith("term_bank_"):
            continue
        for row in json.loads(zf.read(name).decode("utf-8")):
            word = row[0]
            if words and word.lower() not in words:
                continue
            if row[4] < 0:
                continue
            body = []
            for item in row[5]:
                if isinstance(item, list):
                    body.append(f'<div class="ld-redirect-row">→ {ATTR_ESCAPE(item[0])}</div>')
                elif item.get("type") == "structured-content":
                    body.append(sc_to_html(item["content"]))
                elif item.get("type") == "text":
                    body.append(ATTR_ESCAPE(item["text"]))
            parts.append(
                f'<section class="card"><h2 class="hw">{ATTR_ESCAPE(word)}'
                + (f' <small>{ATTR_ESCAPE(row[2])}</small>' if row[2] else "")
                + "</h2>" + "".join(body) + "</section>")
    page = f"""<!doctype html><html><head><meta charset="utf-8"><style>
/* The preview always renders light-on-white. Pin the colour scheme so the page
   does not change shape depending on the host OS preference -- a stale
   dictionary CSS plus a dark host preference is exactly how the headword once
   rendered #e8eaed on white (contrast 1.13:1) during a regression check. */
:root {{ color-scheme: light; }}
body {{ font-family: Georgia, 'Times New Roman', 'Segoe UI', sans-serif; background:#fff; color:#202124; margin:0; padding:16px; max-width:860px; margin:auto; }}
.card {{ border:1px solid #ddd; border-radius:8px; padding:12px 16px; margin-bottom:18px; }}
.hw {{ margin:0 0 8px; font-size:1em; color:#888; border-bottom:2px solid #eee; padding-bottom:4px; }}
a {{ color:#0a66c2; }}
{css}
</style></head><body>{''.join(parts)}</body></html>"""
    out = "C:\\workspace\\ldoce\\preview.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("written", out)


if __name__ == "__main__":
    main()
