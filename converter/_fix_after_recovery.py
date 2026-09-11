"""Fix two real defects found while verifying the recovery:

1. The online panel was emitted with a COMPOUND class ("ld-panel ld-panel-online"),
   which never matches an exact [data-sc-class="..."] selector -- the project's
   number-one trap (HANDOVER S5.1). Switch to the single token ld-panel-online and
   add it to every comma list that styles a panel.
2. GEO labels inside an Inflections sequence used _pick_landscape(), dropping the
   loose qualifier ("especially" in 'busses especially American English'). The
   generic no-portrait reader is now shared by GRAM and inflections.
"""
import sys

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from _apply_patch import apply  # noqa: E402

EDITS = [
    ("online panel single-token class", [
        ('            cls="ld-panel ld-panel-online",\n',
         '            cls="ld-panel-online",\n', 1),
        ('[data-sc-class="ld-panel"], [data-sc-class="ld-panel-corpus"], [data-sc-class="ld-panel-wf"], [data-sc-class="ld-panel-etym"] { display:block; margin:5px 0 6px; }\n',
         '[data-sc-class="ld-panel"], [data-sc-class="ld-panel-corpus"], [data-sc-class="ld-panel-wf"], [data-sc-class="ld-panel-etym"], [data-sc-class="ld-panel-online"] { display:block; margin:5px 0 6px; }\n', 1),
        ('[data-sc-class="ld-panel"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-corpus"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-wf"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-etym"][open] > [data-sc-class="ld-panel-sum"]::before {',
         '[data-sc-class="ld-panel"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-corpus"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-wf"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-etym"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-online"][open] > [data-sc-class="ld-panel-sum"]::before {', 1),
    ]),
    ("share the no-portrait reader", [
        ('    def _gram_text(self, el):\n', '    def _no_portrait_text(self, el):\n', 1),
        ('                label = self._gram_text(child)\n',
         '                label = self._no_portrait_text(child)\n', 1),
        ('''        siblings of the landscape span, so _pick_landscape() dropped them and we
        emitted a bare 'uncountable'. The portrait span is the abbreviation the
        original JS swaps in, so it is skipped exactly like _pick_landscape does.
        """''',
         '''        siblings of the landscape span, so _pick_landscape() dropped them and we
        emitted a bare 'uncountable'. The portrait span is the abbreviation the
        original JS swaps in, so it is skipped exactly like _pick_landscape does.

        Also used for the GEO labels inside an Inflections sequence, where the same
        mistake dropped the loose qualifier ('busses especially American English'
        used to lose 'especially').
        """''', 1),
        ('                push_annot(self._pick_landscape(child) or "", "ld-infl-region")\n',
         '                push_annot(self._no_portrait_text(child), "ld-infl-region")\n', 1),
    ]),
]

if __name__ == "__main__":
    for name, pairs in EDITS:
        apply(name, pairs)
    print("FIXES APPLIED")
