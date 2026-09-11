"""Give word-family words nested inside span.opp their proper class.

span.opp wraps the antonym marker and its word: either
  <a class="crossRef w" href=...>  (a real link -- already handled)
or
  <span class="w"> / <span class="w rootword">  (plain text, NO href)
The second form reached the generic inline fallback, so those words lost the
ld-wf-word styling and got logged as unknown classes ("w" 529 / "rootword" 237 /
"crossRef" 6 in the last build's report). Text was never lost and no link was
lost (linked antonyms are anchors), so this is a styling/report fix.
"""
import sys

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from _apply_patch import apply  # noqa: E402

OLD = '''            if "opp" in cls:
                # Antonym marker: <span class="opp"> != <a class="crossRef w">...</a></span>
                # Matched no branch before, so the whole subtree (12.6% of
                # word-family blocks, 3,528 in the corpus) was dropped.
                inner = merge_adjacent_text(self._children_blocks(child))
                if sc_has_text(inner):
                    node = sc("span", inner, cls="ld-wf-opp")
'''

NEW = '''            if "opp" in cls:
                # Antonym marker: <span class="opp"> != <a class="crossRef w">...</a></span>
                # Matched no branch before, so the whole subtree (12.6% of
                # word-family blocks, 3,528 in the corpus) was dropped.
                #
                # The antonym word is an <a> when it has an entry to link to, but a
                # bare <span class="w"> / <span class="w rootword"> when it does not.
                # The bare form used to fall through to the generic inline branch,
                # losing the word-family styling (and showing up in the unknown-class
                # report as w/rootword/crossRef). Handle the children explicitly.
                parts = []
                for sub in child.children:
                    if isinstance(sub, NavigableString):
                        continue
                    scls = classes_of(sub)
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
                if sc_has_text(parts):
                    node = sc("span", parts, cls="ld-wf-opp")
'''

if __name__ == "__main__":
    apply("word family: opp child handling", [(OLD, NEW, 1)])
    print("OPP CHILD HANDLING APPLIED")
