"""Re-apply every change made after HEAD: T9, T10, D10, D11, box label,
D14 (GRAM), D13 (LDOCE Online panel), render_inflections rewrite.

All writes go through _apply_patch.write_atomic (temp + os.replace), and every
edit is asserted, so a mismatch aborts without touching the target file.
"""
import sys

sys.path.insert(0, r"C:\workspace\ldoce\converter")
from _apply_patch import apply  # noqa: E402

DOT = "\u00b7"

# ---------------------------------------------------------------- T9
T9 = [
    (
        '  display:inline-block; font-size:var(--ld-chip-size); font-weight:600; line-height:1.35;\n'
        '  border-radius:4px; padding:0 5px; margin:0 var(--ld-chip-gap) 0 0; vertical-align:baseline;\n',
        '  display:inline-block; font-size:var(--ld-chip-size); font-weight:600; line-height:1.35;\n'
        '  text-indent:0;   /* text-indent is inherited: .ld-ex uses -1.6em for its hanging indent,\n'
        '                      and an inline-block inherits it onto its own first line, which pulls\n'
        '                      the chip\'s text out of its own box (see REVIEW T9). */\n'
        '  border-radius:4px; padding:0 5px; margin:0 var(--ld-chip-gap) 0 0; vertical-align:baseline;\n',
        1,
    ),
    (
        '[data-sc-class="ld-field"], [data-sc-class="ld-fieldxx"] { display:inline-block; font-size:.78em;',
        '[data-sc-class="ld-field"], [data-sc-class="ld-fieldxx"] { display:inline-block; text-indent:0; font-size:.78em;',
        1,
    ),
    (
        '[data-sc-class="ld-signpost"] { display:inline-block; font-weight:700;',
        '[data-sc-class="ld-signpost"] { display:inline-block; text-indent:0; font-weight:700;',
        1,
    ),
    (
        '[data-sc-class="ld-snum"] { display:inline-block; min-width:1.35em;',
        '[data-sc-class="ld-snum"] { display:inline-block; text-indent:0; min-width:1.35em;',
        1,
    ),
    (
        '[data-sc-class="ld-num"] { display:inline-block; min-width:1.2em;',
        '[data-sc-class="ld-num"] { display:inline-block; text-indent:0; min-width:1.2em;',
        1,
    ),
]

# ------------------------------------------------- T10 + D11: word family
WF_OLD = '''def render_wordfams(self, el):
        fam = el.find("span", class_="LDOCE_word_family")
        if fam is None:
            return None
        children = []
        current_group = None
        for child in fam.children:
            if not isinstance(child, Tag):
                continue
            cls = classes_of(child)
            if "pos" in cls:
                label = sc_text(child.get_text(" ", strip=True))
                current_group = sc("div", [sc("span", label, cls="ld-wf-pos")], cls="ld-wf-group")
                children.append(current_group)
                continue
            node = None
            if "rootword" in cls:
                text = sc_text(child.get("title") or child.get_text(" ", strip=True))
                if text:
                    node = sc("span", text, cls="ld-wf-root")
            elif "crossRef" in cls:
                rendered = self.render_inline_node(child)
                if rendered:
                    node = rendered[0] if len(rendered) == 1 else sc("span", rendered,
                                                                     cls="ld-wf-word")
            elif "w" in cls:
                text = sc_text(child.get("title") or child.get_text(" ", strip=True))
                if text:
                    node = sc("span", text, cls="ld-wf-word")
            if node is None:
                continue
            if current_group is None:
                current_group = sc("div", [], cls="ld-wf-group")
                children.append(current_group)
            group_content = current_group.setdefault("content", [])
            if group_content:
                group_content.append(" ")
            group_content.append(node)
'''

WF_NEW = '''def render_wordfams(self, el):
        # T10: div.wordfams comes in two shapes. The normal one starts with a
        # <span class="LDOCE5pp_sensefold"> header (the fold toggle) and then the
        # <span class="LDOCE_word_family"> data. 38 entries (close, cooperate,
        # definite, ...) carry a SECOND block whose only child is the data span:
        # no header, and that data span has an inline display:none which the
        # original CSS never overrides and LM5Switch.js never toggles (its
        # selector requires the sensefold to be a direct child of .wordfams).
        # The original dictionary therefore never shows those blocks. Emitting
        # them gave those 38 entries two identical "Word family" panels.
        if el.find("span", class_="LDOCE5pp_sensefold", recursive=False) is None:
            return None
        fam = el.find("span", class_="LDOCE_word_family")
        if fam is None:
            return None
        children = []
        current_group = None

        def append_word(node):
            nonlocal current_group
            if current_group is None:
                current_group = sc("div", [], cls="ld-wf-group")
                children.append(current_group)
            group_content = current_group.setdefault("content", [])
            if group_content:
                group_content.append(" ")
            group_content.append(node)

        for child in fam.children:
            if not isinstance(child, Tag):
                # Loose text directly inside LDOCE_word_family carries real
                # word-family members ('additonal', 'the accused', 'customs',
                # 'administrate') -- 2.0% of blocks. The old `continue` dropped
                # them silently. NB sc_text() collapses but does NOT strip, so an
                # explicit .strip() is required or every inter-tag whitespace gap
                # becomes a bogus <span class="ld-wf-word"> </span>.
                text = sc_text(str(child)).strip()
                if text:
                    append_word(sc("span", text, cls="ld-wf-word"))
                continue
            cls = classes_of(child)
            if "pos" in cls:
                label = sc_text(child.get_text(" ", strip=True))
                current_group = sc("div", [sc("span", label, cls="ld-wf-pos")], cls="ld-wf-group")
                children.append(current_group)
                continue
            node = None
            if "opp" in cls:
                # Antonym marker: <span class="opp"> != <a class="crossRef w">...</a></span>
                # Matched no branch before, so the whole subtree (12.6% of
                # word-family blocks, 3,528 in the corpus) was dropped.
                inner = merge_adjacent_text(self._children_blocks(child))
                if sc_has_text(inner):
                    node = sc("span", inner, cls="ld-wf-opp")
            elif "rootword" in cls:
                text = sc_text(child.get("title") or child.get_text(" ", strip=True))
                if text:
                    node = sc("span", text, cls="ld-wf-root")
            elif "crossRef" in cls:
                rendered = self.render_inline_node(child)
                if rendered:
                    node = rendered[0] if len(rendered) == 1 else sc("span", rendered,
                                                                     cls="ld-wf-word")
            elif "w" in cls:
                text = sc_text(child.get("title") or child.get_text(" ", strip=True))
                if text:
                    node = sc("span", text, cls="ld-wf-word")
            if node is None:
                continue
            append_word(node)
'''

WF_CSS = (
    '[data-sc-class="ld-wf-root"] { color:var(--ld-dim); border-bottom:1px dotted color-mix(in srgb, currentColor 60%, transparent); }\n',
    '[data-sc-class="ld-wf-root"] { color:var(--ld-dim); border-bottom:1px dotted color-mix(in srgb, currentColor 60%, transparent); }\n'
    '/* Antonym marker inside a word family: "!= disadvantage". The source wraps it in\n'
    '   <span class="opp"> with a literal U+2260 plus a link. */\n'
    '[data-sc-class="ld-wf-opp"] { color:var(--ld-dim); }\n'
    '[data-sc-class="ld-wf-opp"] > a { color:inherit; font-weight:600; }\n',
    1,
)

# ------------------------------------------------------------- D10: tag cap
TAGLIMIT_ANCHOR = (
    'FREQ_VALUE = {"S1": 1000, "W1": 1000, "S2": 2000, "W2": 2000, "S3": 3000, "W3": 3000}',
    'FREQ_VALUE = {"S1": 1000, "W1": 1000, "S2": 2000, "W2": 2000, "S3": 3000, "W3": 3000}\n'
    '# Cap on the space-separated definitionTags string. POS tags fill first, then\n'
    '# frequency levels, which are never dropped (see pos_tags_rules()).\n'
    'TAG_LIMIT = 8',
    1,
)

TAGS_OLD = '''    for f in dict.fromkeys(freq_tokens):
        if f not in tags:
            tags.append(f)
    return " ".join(tags[:6]), " ".join(rules[:4])
'''
TAGS_NEW = '''    for f in dict.fromkeys(freq_tokens):
        if f not in tags:
            tags.append(f)
    # Frequency levels are appended after the POS tags, so the old flat
    # tags[:6] cap silently dropped them on multi-POS entries: 'about' lost W2
    # from definitionTags while its term_meta_bank row still carried it (140
    # rows disagreed). Reserve room for every S/W level; POS tags yield first.
    freq_part = [t for t in tags if t in FREQ_VALUE]
    pos_part = [t for t in tags if t not in FREQ_VALUE]
    room = max(0, TAG_LIMIT - len(freq_part))
    return " ".join(pos_part[:room] + freq_part), " ".join(rules[:4])
'''

# --------------------------------------------- box sense-group label (span.HEADING)
BOX_OLD = '''        heading = el.find("span", class_="heading") or el.find("span", class_="lm5ppBoxHead")
        title_en, title_zh = self._panel_title(heading, panel_token)
        panel = el.find("div", class_="BoxPanel")
        body = []
        if panel is not None:
            body = self._children_blocks(panel)
        else:
            for child in el.children:
                if child is heading:
                    continue
                if isinstance(child, Tag):
                    ccls = classes_of(child)
                    if "heading" in ccls or "lm5ppBoxHead" in ccls:
                        continue
                    body.extend(self.render_element(child))
        body = merge_adjacent_text(body)
'''
BOX_NEW = '''        heading = el.find("span", class_="heading") or el.find("span", class_="lm5ppBoxHead")
        title_en, title_zh = self._panel_title(heading, panel_token)
        # A box may carry TWO headings: the fold header (class "heading", e.g.
        # COLLOCATIONS) and a sense-group label (class "HEADING" -- uppercase --
        # e.g. "- Meaning 1: one thing that you do"). The latter sits between the
        # header and BoxPanel, so rendering only BoxPanel dropped it. 17 boxes
        # per 1,500 entries carry both; the label tells which sense the
        # collocations belong to. When there is no fold header the uppercase one
        # IS the panel title (that is what the lm5ppBoxHead fallback picks up),
        # hence the identity check.
        gloss = el.find("span", class_="HEADING")
        gloss_node = None
        if gloss is not None and gloss is not heading:
            gtext = sc_text(gloss.get_text(" ", strip=True)).strip()
            if gtext:
                gloss_node = sc("div", [sc("span", gtext, cls="ld-grouptitle")],
                                cls="ld-panel-sub")
        panel = el.find("div", class_="BoxPanel")
        body = []
        if panel is not None:
            body = self._children_blocks(panel)
        else:
            for child in el.children:
                if child is heading:
                    continue
                if isinstance(child, Tag):
                    ccls = classes_of(child)
                    if "heading" in ccls or "lm5ppBoxHead" in ccls:
                        continue
                    body.extend(self.render_element(child))
        if gloss_node is not None:
            body = [gloss_node] + body
        body = merge_adjacent_text(body)
'''

BOX_CSS = (
    '[data-sc-class="ld-grouptitle"] { font-weight:700; color:var(--ld-frame); }\n',
    '[data-sc-class="ld-grouptitle"] { font-weight:700; color:var(--ld-frame); }\n'
    '/* Sense-group label inside a collocation/thesaurus box: "- Meaning 1: ...". It\n'
    '   belongs to the box that follows it, so it sits at the top of the panel body. */\n'
    '[data-sc-class="ld-panel-sub"] { display:block; margin:0 0 4px; padding-bottom:2px; border-bottom:1px solid color-mix(in srgb, currentColor 18%, transparent); }\n'
    '[data-sc-class="ld-panel-sub"] [data-sc-class="ld-grouptitle"] { font-weight:700; }\n',
    1,
)

# ------------------------------------------------------------ D14: head GRAM
GRAM_DISPATCH = (
    '            elif "GRAM" in cls:\n'
    '                label = self._pick_landscape(child)\n',
    '            elif "GRAM" in cls:\n'
    '                label = self._gram_text(child)\n',
    1,
)

GRAM_HELPER_ANCHOR = '''    def _pick_landscape(self, el):
        land = el.find("span", class_="landscape")
        if land is not None:
            return land.get_text(" ", strip=True)
        return el.get_text(" ", strip=True)
'''

GRAM_HELPER_NEW = GRAM_HELPER_ANCHOR + '''
    def _gram_text(self, el):
        """Full grammatical label, e.g. '[singular, uncountable]'.

        A GRAM span is:  ' [' + qualifier text + <span class=landscape>full</span>
        + <span class=portrait><span class=cap>U</span></span> + ']'  -- the
        brackets and any loose qualifier ('singular,', 'only after noun') are
        siblings of the landscape span, so _pick_landscape() dropped them and we
        emitted a bare 'uncountable'. The portrait span is the abbreviation the
        original JS swaps in, so it is skipped exactly like _pick_landscape does.
        """
        parts = []
        for child in el.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
                continue
            cls = classes_of(child)
            if "portrait" in cls:
                continue
            if child.find("span", class_="portrait") is not None:
                for sub in child.children:
                    if isinstance(sub, Tag) and "portrait" in classes_of(sub):
                        continue
                    if isinstance(sub, NavigableString):
                        parts.append(str(sub))
                continue
            parts.append(child.get_text(" ", strip=True))
        return collapse_ws("".join(parts)).strip()

    def _is_online_entry(self, el):
        """True for the OUTERMOST LDOCE Online wrapper only.

        The marker sits on both div.dictentry.LDOCEVERSION_new and the
        div.ldoceEntry.Entry.LDOCEVERSION_new inside it; wrapping each produced
        two nested panels. An ancestor check (rather than a render-time flag) is
        used because _children_blocks() renders the inner entry before the outer
        wrap happens.
        """
        if "LDOCEVERSION_new" not in classes_of(el):
            return False
        return el.find_parent(class_="LDOCEVERSION_new") is None

    def _online_panel(self, body):
        """Collapsed 'LDOCE Online' panel for the LDOCEVERSION_new content.

        The source marks LDOCE Online (LDOCE4-derived, often type="encyc") entries
        with LDOCEVERSION_new, hides them via `.dictentry.LDOCEVERSION_new
        {display:none}` and reveals them with the popup's "LDOCE Online" checkbox
        (#switch_online, default off -- LM5Switch.js filters `.LDOCEVERSION_new`
        on that checkbox). We keep the content but collapsed, so the default view
        matches the original and nothing is silently dropped.
        """
        summary = [sc("span", "LDOCE Online", cls="ld-panel-title")]
        if self.mode == "bilingual":
            summary.append(sc("span", "在线增补", cls="ld-panel-title-zh", lang="zh"))
        details = sc(
            "details",
            [sc("summary", summary, cls="ld-panel-sum"),
             sc("div", body, cls="ld-panel-body")],
            cls="ld-panel ld-panel-online",
        )
        if self.open_panels:
            details["open"] = True
        return details
'''

# ------------------------------------------------------------ D13: dispatch
DISPATCH_OLD = '''        if cls & {"ldoceEntry", "Entry"}:
            inner = self._children_blocks(el)
            return [sc("div", inner, cls="ld-entry")] if inner else []
        if "dictionary" in cls or "dictentry" in cls:
            return self._children_blocks(el)
'''
DISPATCH_NEW = '''        if cls & {"ldoceEntry", "Entry"}:
            inner = self._children_blocks(el)
            if not inner:
                return []
            # LDOCE Online extra entry (LDOCE4-derived, type="encyc"): the source
            # hides it with `.dictentry.LDOCEVERSION_new{display:none}` and the
            # popup's "LDOCE Online" checkbox (#switch_online) reveals it. Emitted
            # bare it reads as a duplicated second entry for the same headword
            # (e.g. 'absurd'), so keep the content but collapse it under a
            # labelled panel -- the same treatment as the original's default state.
            if self._is_online_entry(el):
                return [self._online_panel([sc("div", inner, cls="ld-entry")])]
            return [sc("div", inner, cls="ld-entry")]
        if "dictionary" in cls or "dictentry" in cls:
            inner = self._children_blocks(el)
            if self._is_online_entry(el) and sc_has_text(inner):
                return [self._online_panel(inner)]
            return inner
'''

ONLINE_CSS = (
    '[data-sc-class="ld-panel-sub"] [data-sc-class="ld-grouptitle"] { font-weight:700; }\n',
    '[data-sc-class="ld-panel-sub"] [data-sc-class="ld-grouptitle"] { font-weight:700; }\n'
    '/* LDOCE Online panel: sits at the same level as a normal entry, so give it a\n'
    '   little separation from the preceding entry. */\n'
    '[data-sc-class="ld-panel-online"] { display:block; margin:6px 0 6px; }\n'
    '[data-sc-class="ld-panel-online"] > [data-sc-class="ld-panel-sum"]::before { border-left-color:var(--ld-dim); }\n',
    1,
)

# ------------------------------------------------- render_inflections rewrite
INFL_OLD = '''    def render_inflections(self, el):
        items = []
        for child in el.find_all("span", recursive=True):
            cls = classes_of(child)
            if cls & {"PLURALFORM", "PASTTENSE", "PASTPART", "PRESPART", "T3PERSSING",
                      "PTandPP", "PTandPPX", "PRESPARTX", "T3PERSSINGX", "FULLFORM",
                      "COMP", "SUPERL"}:
                text = sc_text(child.get_text(" ", strip=True)).strip("() ")
                text = re.sub(r"\\s+", " ", text)
                for part in re.split(r"[,;]", text):
                    part = part.strip(" ,;.")
                    if part and part not in items:
                        items.append(part)
        if not items:
            text = sc_text(el.get_text(" ", strip=True)).strip()
            items = [text] if text else []
        children = []
        for idx, item in enumerate(items):
            if idx:
                children.append(" \\u00b7 ")
            children.append(sc("span", item, cls="ld-infl-form"))
        return sc("span", children, cls="ld-infl")
'''

INFL_NEW = '''    INFL_FORM_CLASSES = {
        "PLURALFORM", "PASTTENSE", "PASTPART", "PRESPART", "T3PERSSING",
        "PTandPP", "PTandPPX", "PRESPARTX", "T3PERSSINGX", "FULLFORM",
        "COMP", "SUPERL",
    }
    INFL_SEP = " @DOT@ "

    def render_inflections(self, el):
        """Inflection list, keeping source order AND the annotations.

        The span is a SEQUENCE: surface forms plus annotations that qualify the
        adjacent forms. Two annotation kinds occur inside it and used to be
        dropped because only the form classes were collected:
          * <span class="GEO"> British English / especially American English
            (43 spans corpus-wide; it distinguishes BrE forms from AmE ones,
            e.g. backpedal -> 'backpedalled, backpedalling British English,
            backpedaled, backpedaling American English')
          * <span class="LINKWORD"> 'or' / '(same pronunciation)' (15 spans)
        Emitting the forms alone silently merged two regional paradigms into one
        undifferentiated list.
        """
        nodes = []
        seen = set()

        def push_sep():
            if nodes and nodes[-1] != self.INFL_SEP:
                nodes.append(self.INFL_SEP)

        def push_form(raw):
            text = sc_text(raw).strip("() ")
            text = re.sub(r"\\s+", " ", text)
            for part in re.split(r"[,;]", text):
                part = part.strip(" ,;.")
                if part and part not in seen:
                    seen.add(part)
                    push_sep()
                    nodes.append(sc("span", part, cls="ld-infl-form"))

        def push_annot(raw, cls_name):
            text = sc_text(raw).strip("() ")
            text = re.sub(r"\\s+", " ", text)
            if text and text not in seen:
                seen.add(text)
                push_sep()
                nodes.append(sc("span", text, cls=cls_name))

        for child in el.children:
            if isinstance(child, NavigableString):
                continue
            cls = classes_of(child)
            if cls & self.INFL_FORM_CLASSES:
                push_form(child.get_text(" ", strip=True))
                continue
            if "GEO" in cls:
                push_annot(self._pick_landscape(child) or "", "ld-infl-region")
                continue
            if "LINKWORD" in cls or "italic" in cls:
                push_annot(child.get_text(" ", strip=True), "ld-infl-ann")
                continue
            if child.find("span", recursive=True) is not None:
                for sub in child.find_all("span", recursive=True):
                    scls = classes_of(sub)
                    if scls & self.INFL_FORM_CLASSES:
                        push_form(sub.get_text(" ", strip=True))
        if not nodes:
            text = sc_text(el.get_text(" ", strip=True)).strip()
            if text:
                nodes = [sc("span", text, cls="ld-infl-form")]
        return sc("span", nodes, cls="ld-infl")
'''.replace("@DOT@", DOT)

INFL_CSS = (
    '[data-sc-class="ld-infl-lab"] { font-style:italic; opacity:.75; }\n',
    '[data-sc-class="ld-infl-lab"] { font-style:italic; opacity:.75; }\n'
    '[data-sc-class="ld-infl-region"] { font-style:italic; color:var(--ld-geo, var(--ld-dim)); }\n'
    '[data-sc-class="ld-infl-ann"] { color:var(--ld-dim); }\n',
    1,
)

EDITS = [
    ("T9 text-indent", T9),
    ("T10+D11 wordfams", [(WF_OLD, WF_NEW, 1), WF_CSS]),
    ("D10 tag cap", [TAGLIMIT_ANCHOR, (TAGS_OLD, TAGS_NEW, 1)]),
    ("box sense-group label", [(BOX_OLD, BOX_NEW, 1), BOX_CSS]),
    ("D14 gram_text", [GRAM_DISPATCH, (GRAM_HELPER_ANCHOR, GRAM_HELPER_NEW, 1)]),
    ("D13 online panel", [(DISPATCH_OLD, DISPATCH_NEW, 1), ONLINE_CSS]),
    ("inflections rewrite", [(INFL_OLD, INFL_NEW, 1), INFL_CSS]),
]

if __name__ == "__main__":
    for name, pairs in EDITS:
        apply(name, pairs)
    print("ALL PATCHES APPLIED")
