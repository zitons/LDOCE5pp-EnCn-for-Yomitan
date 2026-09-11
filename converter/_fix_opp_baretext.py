"""Fix a regression from the opp-child patch: the antonym word may be a LOOSE
TEXT NODE directly inside span.opp (academe: '<span class="opp"><span
class="neutral span"> != </span>unacademic</span>'), and the new loop skipped
NavigableString children, so the word disappeared.
"""
import sys

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from _apply_patch import apply  # noqa: E402

OLD = '''                parts = []
                for sub in child.children:
                    if isinstance(sub, NavigableString):
                        continue
                    scls = classes_of(sub)
'''

NEW = '''                parts = []
                for sub in child.children:
                    if isinstance(sub, NavigableString):
                        # The antonym word itself may be bare text inside the span
                        # (academe: '<span class="opp"> != unacademic</span>'), so
                        # text nodes must be kept -- skipping them dropped the word.
                        text = sc_text(str(sub)).strip()
                        if text:
                            parts.append(sc("span", text, cls="ld-wf-word"))
                        continue
                    scls = classes_of(sub)
'''

if __name__ == "__main__":
    apply("opp bare-text antonym", [(OLD, NEW, 1)])
    print("OPP BARE TEXT FIXED")
