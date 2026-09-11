"""Close the last 6 unknown-class leaks.

Inside span.opp, a word can be `<span class="crossRef rootword w" href="/dictionary/X#X__n">`
-- an ANCHOR-form span that carries w/rootword. The opp loop tested crossRef first and
handed it to render_inline_node, whose generic span fallback logs w/rootword/crossRef as
unknown classes.

Rule: inside a word family, a w/rootword word is a word-family word regardless of which
other classes it carries or whether it happens to be a span with an href. Only real
entry:// links (plain <a>) become links; the fragment-href spans inside opp are
self-references, so render them as plain word text.
"""
import sys

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from _apply_patch import apply  # noqa: E402

OLD = '''                    scls = classes_of(sub)
                    if "crossRef" in scls or sub.name == "a":
                        rendered = self.render_inline_node(sub)
                        if rendered:
                            parts.extend(rendered)
                    elif scls & {"w", "rootword"}:
                        text = sc_text(sub.get("title") or sub.get_text(" ", strip=True))
                        if text:
                            parts.append(sc("span", text, cls="ld-wf-word"))
                    elif scls & {"neutral", "span"} or not scls:
                        inner = merge_adjacent_text(self._children_blocks(sub))
                        parts.extend(inner)
                    else:
                        inner = merge_adjacent_text(self._children_blocks(sub))
                        parts.extend(inner)
'''

NEW = '''                    scls = classes_of(sub)
                    # Order matters: a word-family word can ALSO carry crossRef and
                    # an href (e.g. <span class="crossRef rootword w"
                    # href="/dictionary/dislike#dislike__3">, a self-reference). Test
                    # the word classes first -- handing those to the generic link
                    # path was what logged w/rootword/crossRef as unknown classes.
                    if scls & {"w", "rootword"}:
                        href = (sub.get("href") or "").strip()
                        text = sc_text(sub.get("title") or sub.get_text(" ", strip=True))
                        if not text:
                            continue
                        inner = [text]
                        target = clean_target(entry_target_from_href(href, sub.get("title")))
                        resolved = self.terms.resolve(target) if target else None
                        if resolved:
                            self.stats["links_live"] += 1
                            parts.append(sc("a", inner,
                                            href=f"?query={quote(resolved, safe='')}&wildcards=off"))
                        else:
                            parts.append(sc("span", inner, cls="ld-wf-word"))
                    elif sub.name == "a" or (sub.get("href") or "").startswith("entry://"):
                        rendered = self.render_inline_node(sub)
                        if rendered:
                            parts.extend(rendered)
                    else:
                        inner = merge_adjacent_text(self._children_blocks(sub))
                        parts.extend(inner)
'''

if __name__ == "__main__":
    apply("opp word-class precedence", [(OLD, NEW, 1)])
    print("OPP PRECEDENCE FIXED")
