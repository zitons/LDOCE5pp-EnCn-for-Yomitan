#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LDOCE5++ (LM5pp HTML) -> Yomitan structured-content dictionary converter.
# Pipeline shape mirrors shoujocyber/OALD10-Yomitan-Converter:
#   MDX -> extracted text -> per-record parser -> structured content IR
#       -> packager (index.json/tag_bank/term_bank/styles.css/ZIP)
#       -> structural validator.
# Part 1 of 2 (core + renderer). Assembled by build script.

import gc
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
import glob
from collections import Counter
from datetime import date
from urllib.parse import quote, unquote

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(x, **kwargs):
        return x

VERSION = "1.1.0"
# ASCII only: this string is written into index.json, and a mono package declares
# targetLanguage "en" -- CJK metadata there breaks the "no CJK" contract.
AUTHOR = "LDOCE5++ Yomitan converter"
# The dictionary data comes from the freemdict forum; the OALD10 repo that
# inspired the pipeline is NOT this dictionary's homepage.
PROJECT_URL = "https://forum.freemdict.com/"
SOURCE_FORUM_URL = "https://forum.freemdict.com/"
TERM_BANK_BATCH = 10000
REDIRECT_SCORE = -10
ENTRY_SCORE = 10
COMPRESS_LEVEL = 6
# bs4 tree builder. "lxml" (C/libxml2) is byte-for-byte equivalent on this corpus
# and much faster than the pure-Python "html.parser" -- verified by
# converter/audit7_parser_equiv.py (1747 stratified rows, 0 differences).
HTML_PARSER = "lxml"

INVISIBLE_RE = re.compile("[\u00ad\u200b\u200c\u200d\u2060\ufeff\u2061\u2062\u2063\u2064]")
WS_RE = re.compile(r"\s+")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# Source classes holding the Chinese side of a bilingual label. render_inline_node
# drops these in mono mode; every *flattening* reader of a label must do the same
# (see LdoceRenderer._label_text, audit A5).
ZH_CLASSES = frozenset({"cn_txt", "cn_txt_ext"})
# Remove only recognized Chinese translations of NOT in mono usage examples.
# Leave other unmarked CJK for validation rather than silently deleting content.
MONO_USAGE_NOTE_RE = re.compile(r"\bNOT\s*" + CJK_RE.pattern + r"+\s*")
CONTRACTION_TAIL_RE = re.compile(r"^(?:[dstm]|ll|re|ve)(?:\b|$)", re.IGNORECASE)
NEGATIVE_CONTRACTION_TAIL_RE = re.compile(r"^n['\u2019]t(?:\b|$)", re.IGNORECASE)
E_STEM_RE = re.compile(r"[A-Za-z]+e$")


def strip_invisible(value):
    return INVISIBLE_RE.sub("", str(value or ""))


def collapse_ws(value):
    return WS_RE.sub(" ", value)


def sanitize_strings(value):
    if isinstance(value, str):
        return strip_invisible(value)
    if isinstance(value, list):
        return [sanitize_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_strings(item) for key, item in value.items()}
    return value


def sanitize_inplace(value):
    """Same semantics as sanitize_strings() but reuses the containers.

    Bank rows are written once and then discarded, so the deep copy that
    sanitize_strings() performs (millions of dict/list per bank) is pure
    overhead. Most strings contain no invisible characters at all, so this
    only allocates for the ones that do.
    """
    if isinstance(value, str):
        return strip_invisible(value)
    if isinstance(value, list):
        for i, item in enumerate(value):
            value[i] = sanitize_inplace(item)
        return value
    if isinstance(value, dict):
        for key in value:
            value[key] = sanitize_inplace(value[key])
        return value
    return value


def sc(tag, content=None, cls=None, data=None, lang=None, title=None, style=None, **extra):
    node = {"tag": tag}
    merged = dict(data) if data else {}
    if cls:
        existing = merged.get("class")
        merged["class"] = f"{existing} {cls}".strip() if existing else cls
    if merged:
        node["data"] = merged
    if lang:
        node["lang"] = lang
    if title:
        node["title"] = title
    if style:
        node["style"] = style
    node.update(extra)
    if content is not None:
        node["content"] = content
    return node


def sc_text(text):
    return strip_invisible(collapse_ws(str(text)))


def sc_has_text(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(sc_has_text(item) for item in value)
    if isinstance(value, dict):
        tag = value.get("tag")
        if tag in ("br", "img"):
            return True
        if "content" in value:
            return sc_has_text(value["content"])
        return True
    return False


def merge_adjacent_text(nodes):
    """Coalesce neighbouring strings, and KEEP the source's own separators.

    A whitespace-only run used to be dropped whenever a text run followed it, so
    the renderer had to reinvent the separator downstream with a character
    heuristic -- and that heuristic is what split words like `terrorist s` and
    `SUM 1` (audit R1). The source reads

        ...>coal</a> <span class="NonDV">mines</span> fell onto a school...

    so the space between the two tags is real typography and must survive. It is
    folded into the text run that follows (which is what makes it survive the
    coalescing below); a run next to an element is kept as a standalone " ", and a
    run between two block elements is harmless -- layout discards whitespace there.
    """
    out = []
    for i, node in enumerate(nodes):
        if not isinstance(node, str):
            out.append(node)
            continue
        if not node:
            continue
        if not node.strip():
            nxt = nodes[i + 1] if i + 1 < len(nodes) else None
            if isinstance(nxt, str):
                if not nxt.strip():
                    continue                    # collapse consecutive runs
                if not nxt[:1].isspace():
                    nodes[i + 1] = " " + nxt    # fold into the following text run
                    continue
        if out and isinstance(out[-1], str):
            prev = out[-1]
            if prev.strip():
                out[-1] = prev + node
            elif node.strip():
                out[-1] = prev + node           # a kept separator + the text
            continue
        out.append(node)
    return out


def strip_leading_bullet(nodes):
    if not nodes:
        return
    first = nodes[0]
    if isinstance(first, str):
        stripped = first.lstrip("\u2022\u00b7 \u00a0")
        if stripped:
            nodes[0] = stripped
        else:
            nodes.pop(0)


def starts_with_sense_number(nodes):
    """True when the first visible child of a sense is its number chip.

    Decides whether the hanging-indent gutter is worth reserving: 49% of the
    senses in this source carry no number, and an empty gutter just eats popup
    width (see generate_css / ld-sense-n)."""
    for item in nodes:
        if isinstance(item, str):
            if item.strip():
                return False
            continue
        if isinstance(item, dict):
            return (item.get("data") or {}).get("class") == "ld-snum"
        return False
    return False


# ---------------------------------------------------------------------------
# Class policy tables
# ---------------------------------------------------------------------------

DROP_TAGS = {"script", "style", "link", "input", "label", "meta", "head", "body", "html",
             "title", "textarea", "select", "option", "button", "form"}

DROP_CLASSES = {
    "lm5ppMenu", "lm5ppMenu_title", "lm5ppMenu_floatlogo", "lm5ppMenu_logo",
    "lm5pp_popup", "lm5pp_popupitem", "menu_quit", "logo_float",
    "icon_quit", "icon_senseFold", "icon_boxFold", "lm5pp_icon",
    "dictionary_intro", "en_title", "cn_title", "goldlogo", "halfgold",
    "corpusegg", "bussdictegg", "foldsign", "foldblank", "foldsignbar1",
    "foldsignbar2", "switch", "switch_title", "slider", "round", "suppressed",
    "hideOnAmp", "speaker", "brefile", "amefile", "exafile", "fa",
    "fa-volume-up", "LDOCEVERSIONLOGO_new", "LDOCEVERSIONLOGO_5",
    "LDOCE5pp-image-small", "imagerelated", "ldoce-show-image", "ldoce4img",
    "ldoce4page", "piccal", "PICCAL", "asset_intro",
}

UNWRAP_CLASSES = {
    "LDOCE_switch_lang", "switch_siblings", "switch_children", "neutral",
    "NonDV", "LDOCE5pp_sensefold", "LDOCE5pp_sensefold_other",
    "foldsign_fold", "LDOCEVERSION_new", "LDOCEVERSION_5", "upperBorder",
    "mini", "span", "div", "a", "lm5ppbody", "entry_content", "dictionary",
    "dictentry", "dictlink", "newline", "english", "merge_sense",
    "cross_sense", "landscape", "portrait", "refsensenum", "frequent",
    "comma", "SUFFIX",
}

INLINE_MAP = {
    "cn_txt":     ("ld-zh", {"zh": True}),
    "cn_txt_ext": ("ld-zh", {"zh": True}),
    "en_txt":     ("ld-en", {}),
    "GLOSS":      ("ld-gloss", {}),
    "COLLGLOSS":  ("ld-gloss", {}),
    "synopp":     ("ld-synmark", {}),
    "CROSSREFTYPE": ("ld-xrtype", {}),
    "sensenum":   ("ld-snum", {}),
    # HYP is handled explicitly in render_inline_node / hwd_collect: it carries
    # either a syllable dot (ld-hyp) or a stress mark (ld-stress).
    "HOMNUM":     ("ld-sup", {}),
    "REFHOMNUM":  ("ld-sup", {}),
    "REFSENSENUM": ("ld-sup", {}),
    "italic":     ("ld-it", {}),
    "DEFBOLD":    ("ld-b", {}),
    "HINTBOLD":   ("ld-b", {}),
    "GOODBOLD":   ("ld-b", {}),
    "STRONG":     ("ld-b", {}),
    "HINTITALIC": ("ld-it", {}),
    "CENTURY":    ("ld-century", {}),
    "TRAN":       ("ld-tran", {}),
    "LANG":       ("ld-lang", {}),
    "ORIGIN":     ("ld-origin", {}),
    "ABBR":       ("ld-abbr", {}),
    "OBJECT":     ("ld-obj", {}),
    "HINT":       ("ld-hint-inline", {}),
    "hint":       ("ld-hint-inline", {}),
    "LEVEL":      ("ld-level", {}),
    "FREQ":       ("ld-freq", {}),
    "GOODCOLLO":  ("ld-good-word", {}),
    "BADCOLLO":   ("ld-bad-word", {}),
    "COLLORANGE": ("ld-collo-range", {}),
    "THESPROPFORM": ("ld-propform", {}),
    "REFSENSE":   ("ld-sup", {}),
    "TITLE":      ("ld-grouptitle", {}),
}

CHIP_MAP = {
    "lm5pp_POS": "ld-pos",
    "pos": "ld-pos",
    "GRAM": "ld-gram",
    "GEO": "ld-geo",
    "REGISTERLAB": "ld-register",
    "FIELD": "ld-field",
    "FIELDXX": "ld-fieldxx",
    "ACTIV": "ld-act",
    "_ACTIV": "ld-act",
    "_ACTIV_": "ld-act",
    "cn_topic": "ld-actcn",
    "Signpost": "ld-signpost",
    "SIGNPOST": "ld-signpost",
    "SYN": "ld-syn",
    "OPP": "ld-syn",
    "HOMOPHONE": "ld-homophone",
    "DERIV": "ld-deriv",
    "LEXVAR": "ld-lexvar",
    "AmEVariant": "ld-lexvar",
    "BrEVariant": "ld-lexvar",
    "ORTHVAR": "ld-lexvar",
    "AMEVARPRON": "ld-pron-amevar",
    "PRESPARTX": "ld-infl-form",
    "PTandPPX": "ld-infl-form",
    "T3PERSSINGX": "ld-infl-form",
    "PLURALFORM": "ld-infl-form",
    "PASTTENSE": "ld-infl-form",
    "PASTPART": "ld-infl-form",
    "PRESPART": "ld-infl-form",
    "T3PERSSING": "ld-infl-form",
    "PTandPP": "ld-infl-form",
    "FULLFORM": "ld-infl-form",
    "COMP": "ld-infl-form",
    "SUPERL": "ld-infl-form",
    "EXP": "ld-exp",
    "COLLO": "ld-collo",
    "collo": "ld-collo",
    "COLLOINEXA": "ld-colloin",
    "LEXUNIT": "ld-collo",
    "LINKWORD": "ld-collo",
    "PROPFORM": "ld-propform",
    "EXPR": "ld-expr",
    "NodeW": "ld-nodew",
    "RELATEDWD": "ld-relatedwd",
    "CompareWord": "ld-relatedwd",
    "HWD": "ld-hwd",
    "REFHWD": "ld-refhwd",
    "PHRVBHWD": "ld-refhwd",
    "PRON": "ld-pron",
    "PronCodes": "ld-pronblk",
    "AMEQUIV": "ld-equiv",
    "BREQUIV": "ld-equiv",
    "title": "ld-grouptitle",
    "Num": "ld-num",
    "AC": "ld-gloss",
    "DATE": "ld-gloss",
    "BOOKFILM": "ld-gloss",
    "XREF": "ld-xref",
    "Crossref": "ld-crossref",
    "Xref": "ld-crossref",
    "Thesref": "ld-thesref",
    "PROPFORMPREP": "ld-propform",
    "REFLEX": "ld-it",
    "REFHOM": "ld-sup",
    "CROSS": "ld-crossref",
    "Variant": "ld-lexvar",
    "i": "ld-it",
}
CHIP_PRIORITY = list(CHIP_MAP.keys())

# A DROP class normally removes the element *and its entire subtree*. These tokens
# are allowed to win instead, because the element carries text the original
# stylesheet displays (`.Crossref.ldoce4img { color:#4058a4 }`). Without this the
# "See picture" pointer lines were silently dropped from 1548 records (REVIEW D8).
DROP_EXEMPT = {"Crossref", "crossRef"}


def is_dropped(cls):
    """True when the element should be removed wholesale.

    Deliberately *not* a bare `cls & DROP_CLASSES`: an element can carry a
    meaningful class alongside a discarded one (e.g. `Crossref imagerelated`),
    and dropping on the first hit loses real content.
    """
    return bool(cls & DROP_CLASSES) and not (cls & DROP_EXEMPT)


# LDOCE frequency band -> rank ceiling ("within the top N"), which is what
# Yomitan's frequency sorting expects: lower = more frequent.
FREQ_VALUE = {"S1": 1000, "W1": 1000, "S2": 2000, "W2": 2000, "S3": 3000, "W3": 3000}

# ---------------------------------------------------------------------------
# Semantic inlining (scheme B).
#
# 5 CSS ::before rules carry real information (example dash, correct/incorrect
# usage, corpus bullet). A host that cannot load the stylesheet at all -- Anki
# exports, plain-HTML previews, other readers -- loses that information entirely.
# So the marker is ALSO written into the content as
#     <span class="ld-mark">MARKER</span>
# and CSS hides it again ([data-sc-class="ld-mark"]{display:none}), keeping the
# ::before rule as the visible one. Verified on a real engine: with the
# stylesheet the marker span computes to display:none and ::before still draws
# the character (visual result unchanged); without it the span is an ordinary
# inline node, so the information survives.
#
# The marker is applied per container class so the character matches the rule it
# stands in for.
SCHEME_B_MARKERS = {
    "ld-ex":            "\u2013\u00a0",   # - (en dash, like the ::before content)
    "ld-gramexa":       "\u2013\u00a0",
    "ld-colloexa":      "\u2013\u00a0",
    "ld-ex-good":       "\u2713\u00a0",   # check
    "ld-ex-bad":        "\u2717\u00a0",   # cross
    "ld-corpexa":       "\u2022\u00a0",   # bullet
    "ld-corpexa-corpus": "\u2022\u00a0",
    "ld-corpexa-dics":  "\u2022\u00a0",
    "ld-corpexa-encyc": "\u2022\u00a0",
    "ld-corpexa-online": "\u2022\u00a0",
    "ld-corpexa-phrases": "\u2022\u00a0",
}


def scheme_b_prefix(cls):
    """Marker text for a container class, or "" when it needs none."""
    return SCHEME_B_MARKERS.get(cls, "")


# ---------------------------------------------------------------------------
# Portable separation between head atoms (see render_head + _chip_root_cause).
#
# ATOMS are self-contained pieces that must stay distinguishable when no
# stylesheet is applied. GLUE are parts of the headword itself -- separating them
# would turn the syllable dots into 'a . ban . don'.
# ---------------------------------------------------------------------------
HEAD_ATOM_CLASSES = frozenset({
    "ld-pron", "ld-pronblk", "ld-pron-amevar", "ld-level", "ld-freq", "ld-gloss",
    "ld-pos", "ld-gram", "ld-geo", "ld-register", "ld-field", "ld-fieldxx",
    "ld-act", "ld-actcn", "ld-synmark", "ld-sup", "ld-hwd-wrap", "ld-infl",
    # Alternative-form annotations: '(also an)', '(also 800 line...)', ', a'.
    # regress_head_separation.py found 8 heads where such a node sat between two
    # atoms and neither boundary got a space, e.g. 'a /…/ ●●● S1 W1
    # (also an)indefinite article'. It is self-contained, so it is an atom too.
    "ld-lexvar",
    # inflection-sequence members (render_inflections output, unwrapped into the
    # head): 'abetting[transitive]' was the observable failure.
    "ld-infl-form", "ld-infl-lab", "ld-infl-region", "ld-infl-ann", "ld-infl-pron",
})
HEAD_GLUE_CLASSES = frozenset({
    "ld-hyp", "ld-stress", "ld-hwd", "ld-en", "ld-zh",
    # a homograph number is superscript on the headword: 'abandon1', not 'abandon 1'
    "ld-sup",
})


def _sc_classes(node):
    if not isinstance(node, dict):
        return set()
    cls = (node.get("data") or {}).get("class")
    return set(cls.split()) if cls else set()


# ---------------------------------------------------------------------------
# Portable separation for every inline run.
#
# A host that drops the stylesheet has no margins or backgrounds, so adjacent
# inline siblings run together: '[uncountable]SHORT/NOT LONG',
# 'Corpus examples语料库例句', 'soft sell软推销'.
# 236,375 such seams exist corpus-wide. Block children already wrap in raw HTML
# and are left alone.
# ---------------------------------------------------------------------------
INLINE_TAGS = frozenset({"span", "a", "b", "i", "em", "strong", "sup", "sub",
               "ruby", "rt", "rp", "code", "small", "mark", "u"})


def _sc_tag(node):
    if isinstance(node, dict):
        return node.get("tag", "span")
    return None                      # bare string -> inline text


def _is_inline(node):
    t = _sc_tag(node)
    return t is None or t in INLINE_TAGS


def _plain_text(node):
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_plain_text(x) for x in node)
    if isinstance(node, dict):
        return _plain_text(node.get("content", ""))
    return ""


# characters that may END a left node and START a right node such that the two
# would visually merge. Kept deliberately narrow: only word characters, CJK and
# closing/opening brackets.
_LEFT_END = set(")]}、。）］’'")
# opening brackets and quotes, written as escapes so the literal stays simple
_RIGHT_START = set("([{\uff08\uff3b\u2018\u201c")
_WORDISH = set("abcdefghijklmnopqrstuvwxyz"
               "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


def _is_wordish(ch):
    return ch in _WORDISH or "\u4e00" <= ch <= "\u9fff"


# A phonetics block ('/.../', ' /-kli/') is a self-contained atom, and what
# follows it (a POS, another pronunciation, an inflection) is a different atom.
# Scoped to the ELEMENT -- a blanket "space after '/'" would corrupt ordinary
# prose such as 'and/or' or 'km/h'.
_PRON_BLOCK_CLASSES = frozenset({"ld-pronblk", "ld-pron", "ld-pron-amevar"})


def _is_pron_block(node):
    if not isinstance(node, dict):
        return False
    cls = (node.get("data") or {}).get("class")
    return bool(cls) and bool(set(cls.split()) & _PRON_BLOCK_CLASSES)


# Self-contained label/chip classes: they never continue into the text beside
# them, so a seam that touches one always needs a separator. Prose-inline classes
# are deliberately ABSENT -- ld-collo, ld-colloin, ld-hwd, ld-refhwd, ld-en,
# ld-bad-word, ld-good-word, ld-exp, ld-nodew, ld-wf-word, ld-wf-opp, ld-sup,
# ld-defref and friends: those can end mid-word and must keep the source seam.
BODY_ATOM_CLASSES = frozenset({
    "ld-pos", "ld-freq", "ld-gram", "ld-level", "ld-gloss", "ld-geo",
    "ld-register", "ld-field", "ld-fieldxx", "ld-act", "ld-actcn",
    "ld-synmark", "ld-homophone", "ld-signpost", "ld-propform", "ld-lexvar",
    # the Chinese side of a bilingual label is always its own unit
    "ld-zh",
    # headings, and the annotations inside an inflection sequence
    "ld-grouptitle", "ld-panel-title", "ld-panel-title-zh", "ld-exagroup-title",
    "ld-infl-form", "ld-infl-lab", "ld-infl-region", "ld-infl-ann",
    "ld-infl-pron",
})


def _is_body_atom(node):
    return _is_pron_block(node) or bool(_sc_classes(node) & BODY_ATOM_CLASSES)


def _is_sup_node(node):
    cls = (node.get("data") or {}).get("class") if isinstance(node, dict) else None
    return bool(cls) and "ld-sup" in cls.split()


def _seam_needs_space(left, right):
    lt, rt = _plain_text(left), _plain_text(right)
    if not lt or not rt:
        return False
    # the source already decided: whitespace on either side of the seam IS the
    # separator (merge_adjacent_text now preserves it) and nothing may be added
    if lt[-1].isspace() or rt[0].isspace():
        return False
    # never a space before/after a superscript homograph or inline number
    if _is_sup_node(left) or _is_sup_node(right):
        return False
    if _is_pron_block(left):
        return rt[0] not in "./,;:"
    # Word-internal apostrophes survive every source node shape: You’<a>re</a>,
    # <a>Don</a>’<a>t</a>, and <a>don’</a><a>t</a>. Do not disable every prose
    # seam: source NonDV links sometimes omit a real word space (model + kits),
    # and the word-family renderer also relies on separation between members.
    if not (_is_body_atom(left) or _is_body_atom(right)):
        if lt[-1] in "'’" and CONTRACTION_TAIL_RE.match(rt):
            return False
        # The apostrophe can be INSIDE the following node: did<span>n't</span>.
        # Explicit source whitespace was checked above; independent labels must
        # still be separated. Match a whole n't clitic, not an arbitrary n-word.
        if ("a" <= lt[-1].lower() <= "z"
                and NEGATIVE_CONTRACTION_TAIL_RE.match(rt)):
            return False
        # The source also links an inflection fragment separately: relieve + d,
        # fertilize + d. Both sides can be elements, so the text-tail guard below
        # is insufficient. Restrict this to lowercase d after an English e-stem;
        # do not glue arbitrary links (model + kits, games + console), numeric
        # labels, or standalone uppercase letters such as vitamin + D.
        if rt == "d" and E_STEM_RE.search(lt):
            return False
    # R1: another place this heuristic must not fire -- a bare text run on the
    # right of an element can CONTINUE that element's word. The source
    # reads
    #     <a href="entry://terrorist">terrorist</a></span>s carrying
    #     <span class="COLLOINEXA">bank robber</span>s in US history
    #     <a ...>download</a>ed        <a ...>SUM</a>1 (= someone)
    # so the trailing 's' / 'ed' / '1' must stay glued and `SUM1` must never become
    # `SUM 1`. A chip/label element on the left (`ld-pos`, `ld-freq`, a heading, an
    # inflection annotation) is a unit of its own, so those seams keep their
    # separator. Everything else behaves exactly as before the R1 fix.
    if isinstance(left, dict) and isinstance(right, str) and not _is_body_atom(left):
        return False
    a, b = lt[-1], rt[0]
    if _is_wordish(a) and (_is_wordish(b) or b in _RIGHT_START):
        return True
    if a in _LEFT_END and _is_wordish(b):
        return True
    return False


# Inline bottom margins for block nodes, mirroring the values generate_css()
# already declares for the same classes. Without a stylesheet every margin
# collapses and consecutive blocks (english def / chinese def / example /
# translation / next sense) read as one wall of text -- a space cannot fix that,
# because whitespace between block elements is discarded by layout.
#
# An inline declaration beats an author rule, so a fallback may only be attached
# where it is a NO-OP under CSS: either the value EQUALS the rule's bottom margin,
# or that rule marks the property !important. Two traps this file has already
# fallen into, both worth remembering:
#   * `margin:1px 0` is a TWO-value shorthand -- top/bottom then left/right -- so
#     its bottom margin is 1px, NOT 0. (Measured in Chrome; a misreading of it
#     once sent me looking for a phantom extra 1px on 133k ld-def nodes.)
#   * the 3-value form is top / left-right / bottom, so `margin:1px 0 3px` is 3px.
# regress_inline_vs_css.py expands the shorthand and enforces the invariant for
# every entry, in both directions.
BLOCK_BOTTOM_MARGIN = {
    "ld-def": "1px",
    "ld-defcn": "3px",
    "ld-ex": "3px",
    "ld-excn": "2px",
    "ld-sense": "7px",
    "ld-subsense": "3px",
}


# ---------------------------------------------------------------------------
# Native list semantics (reference package: LDOCE5.zip by lng).
#
# The reference carries its entire hierarchy in native HTML lists with NO
# stylesheet -- <ol><li> for senses, a nested <ul><li> for examples -- plus four
# inline styles. A browser then supplies the numbers, the bullets and the indents
# from its own default stylesheet, so the card is readable anywhere.
#
# Verified UA behaviour (real Chrome, no CSS):
#     ol -> display:block, list-style-type:decimal, padding-left:40px
#     li -> display:list-item
#     ul -> display:block, list-style-type:disc, padding-left:40px
#
# Dual-mode numbering: the SOURCE number stays authoritative in both
# environments. An earlier attempt hid our own number chip (inline font-size:0)
# and let the UA number the list; that is wrong whenever the source numbering is
# not a plain 1..n run -- LDOCE numbers senses continuously across an entry and
# skips cross-reference rows, so 'act' showed 1,2,3,4 for source 7,8,9,10 and 531
# entries were renumbered (audit R2). Instead the UA marker is switched off with
# the legal SC style `listStyleType` (SC_STYLE_ALLOWED), so:
#     with CSS    -> list-style:none from the stylesheet, our chip shows the number
#     without CSS -> inline listStyleType:none suppresses the UA marker, the
#                    browser still supplies ol's own `padding-left:40px` indent,
#                    and our chip shows the SOURCE number
# ---------------------------------------------------------------------------
UA_MARKER_OFF = {"listStyleType": "none"}
SEMANTIC_INLINE_STYLES = {
    "ld-gram":  {"color": "DodgerBlue"},
    "ld-pos":   {"color": "DodgerBlue"},
    "ld-defcn": {"color": "green"},
    "ld-excn":  {"color": "green"},
    "ld-field": {"color": "green", "fontWeight": "bold"},
    "ld-act":   {"fontWeight": "bold"},
    "ld-refhwd": {"fontWeight": "bold"},
    "ld-colloin": {"fontWeight": "bold"},
    "ld-collo": {"fontWeight": "bold"},
    "ld-nodew": {"fontWeight": "bold"},
    "ld-grouptitle": {"color": "green", "fontWeight": "bold"},
    "ld-exagroup-title": {"color": "green", "fontWeight": "bold"},
    # NOTE: every value below must either EQUAL its class rule in generate_css(),
    # or have that rule marked !important -- an inline declaration beats an author
    # rule, so a differing value silently overrides the theme palette. That is
    # exactly what happened to green/DodgerBlue: with the stylesheet loaded, dark
    # Chinese definitions fell from ~6.5:1 to 3.245:1 contrast (audit R3). Each
    # entry here is paired with an !important counterpart in generate_css().
    # ld-wf-root used to carry a bold fallback with no counterpart at all and was
    # removed for the same reason.
    "ld-wf-pos": {"fontStyle": "italic"},
}

# classes that are a list member at their level
SENSE_ITEM_CLASSES = frozenset({"ld-sense", "ld-sense-cross", "ld-sense-merge",
                                "ld-subsense"})
EXAMPLE_ITEM_CLASSES = frozenset({"ld-ex", "ld-ex-good", "ld-ex-bad",
                                  "ld-gramexa", "ld-colloexa"})


def add_inline_semantics(node):
    """Attach the no-CSS inline colour/weight styles (reference vocabulary)."""
    if isinstance(node, list):
        return [add_inline_semantics(x) for x in node]
    if isinstance(node, dict):
        d = dict(node)
        if "content" in d:
            d["content"] = add_inline_semantics(d["content"])
        cls = (d.get("data") or {}).get("class")
        if cls:
            style = dict(d.get("style") or {})
            for tok in cls.split():
                for k, v in SEMANTIC_INLINE_STYLES.get(tok, {}).items():
                    style.setdefault(k, v)
            if style:
                d["style"] = style
        return d
    return node


def group_into_list(nodes, member_classes, list_cls, list_tag="ol"):
    """Wrap consecutive members into one <ol>/<ul>, each becoming an <li>."""
    out = []
    run = []

    def flush():
        nonlocal run
        if not run:
            return
        items = []
        for nd in run:
            if isinstance(nd, dict) and nd.get("tag") == "li":
                items.append(nd)
            else:
                items.append(sc("li", nd if isinstance(nd, list) else [nd]))
        out.append(sc(list_tag, items, cls=list_cls, style=dict(UA_MARKER_OFF)))
        run = []

    for nd in nodes:
        cls = ""
        if isinstance(nd, dict):
            cls = (nd.get("data") or {}).get("class", "")
        if any(tok in member_classes for tok in cls.split()):
            run.append(nd)
        else:
            flush()
            out.append(nd)
    flush()
    return out


def _add_block_spacing(node):
    """Attach style.marginBottom to block nodes that need a no-CSS gap."""
    if isinstance(node, list):
        return [_add_block_spacing(x) for x in node]
    if isinstance(node, dict):
        d = dict(node)
        if "content" in d:
            d["content"] = _add_block_spacing(d["content"])
        cls = (d.get("data") or {}).get("class")
        if cls:
            margin = None
            for tok in cls.split():
                if tok in BLOCK_BOTTOM_MARGIN:
                    margin = BLOCK_BOTTOM_MARGIN[tok]
                    break
            if margin:
                style = dict(d.get("style") or {})
                style.setdefault("marginBottom", margin)
                d["style"] = style
        return d
    return node


def separate_inline_runs(node):
    """Insert one space between touching inline siblings, recursively."""
    if isinstance(node, list):
        out = []
        for i, item in enumerate(node):
            out.append(separate_inline_runs(item))
            if i + 1 >= len(node):
                continue
            nxt = node[i + 1]
            if _is_inline(item) and _is_inline(nxt) and _seam_needs_space(item, nxt):
                out.append(" ")
        return out
    if isinstance(node, dict):
        d = dict(node)
        if "content" in d:
            d["content"] = separate_inline_runs(d["content"])
        return d
    return node


def separate_head_atoms(nodes):
    """Insert a space between adjacent independent ATOM siblings.

    A space goes in only between two atoms, and never next to a GLUE element.
    A plain-text node followed by an atom is separated as well; text immediately
    followed by glue (the headword) is left alone.
    """
    def ends_with_space(n):
        return isinstance(n, str) and n.endswith((" ", "\u00a0"))

    def starts_with_space(n):
        return isinstance(n, str) and n.startswith((" ", "\u00a0"))

    out = []
    for idx, node in enumerate(nodes):
        out.append(node)
        if idx + 1 >= len(nodes):
            continue
        nxt = nodes[idx + 1]
        # an existing separator already provides the gap (' · ' between
        # inflection forms, or a whitespace-only text node)
        if ends_with_space(node) or starts_with_space(nxt):
            continue
        if isinstance(node, str):
            # non-empty text followed by an atom needs a separator
            if node.strip():
                b_cls = _sc_classes(nxt)
                if (b_cls & HEAD_ATOM_CLASSES) and not (b_cls & HEAD_GLUE_CLASSES):
                    out.append(" ")
            continue
        a_cls, b_cls = _sc_classes(node), _sc_classes(nxt)
        a_atom, b_atom = bool(a_cls & HEAD_ATOM_CLASSES), bool(b_cls & HEAD_ATOM_CLASSES)
        glue = bool(a_cls & HEAD_GLUE_CLASSES) or bool(b_cls & HEAD_GLUE_CLASSES)
        if a_atom and b_atom and not glue:
            out.append(" ")
    return out


# OBSERVATION THRESHOLD, not a cap. pos_tags_rules() emits every tag (see the
# comment there): real data peaks at 11 ('like' = 7 POS + 4 frequency codes), so
# any truncation loses metadata. validate_package() reports rows above this
# threshold so genuine data drift stays visible. Re-derive with _cap_choose.py.
TAG_LIMIT = 8

BLOCK_MAP = [
    ("Sense", "ld-sense"),
    ("Subsense", "ld-subsense"),
    ("Subentry", "ld-sense"),
    ("SubEntry", "ld-sense"),
    ("PhrVbEntry", "ld-phrventry"),
    ("EXAMPLE", "ld-ex"),
    ("GramExa", "ld-gramexa"),
    ("ColloExa", "ld-colloexa"),
    ("Collocate", "ld-collocate"),
    ("Exponent", "ld-exponent"),
    ("RunOn", "ld-runon"),
    ("EXPL", "ld-expl"),
    ("Section", "ld-section"),
    ("frequency", "ld-frequency"),
    ("SpokenSect", "ld-spokensect"),
    ("Hint", "ld-hint"),
    ("dont_say", "ld-dontsay"),
    ("warning", "ld-warn"),
    ("GOODEXA", "ld-ex-good"),
    ("BADEXA", "ld-ex-bad"),
    ("topics_container", "ld-topics"),
    ("related_topics", "ld-topics-body"),
    ("SECHEADING", "ld-psub"),
    ("HEADING", "ld-phead"),
    ("boxheader", "ld-phead"),
    ("spokensectheader", "ld-phead"),
]
BLOCK_TOKENS = {token for token, _ in BLOCK_MAP}
BLOCK_SCNAME = dict(BLOCK_MAP)

PANEL_CLASSES = {"F2NBox", "GramBox", "ThesBox", "ColloBox", "UsageBox", "ThesColloBox"}
PANEL_SKIP_CLASSES = {"FrequenceBox"}

PANEL_FALLBACK_TITLES = {
    "F2NBox": ("Register", "语体"),
    "GramBox": ("Grammar", "语法"),
    "ThesBox": ("Thesaurus", "词义辨析"),
    "ColloBox": ("Collocations", "搭配"),
    "UsageBox": ("Usage", "用法说明"),
    "ThesColloBox": ("Collocations", "搭配"),
}

PANEL_TITLES_ZH = {
    "thesaurus": ("Thesaurus", "词义辨析"),
    "collocations": ("Collocations", "搭配"),
    "grammar": ("Grammar", "语法"),
    "register": ("Register", "语体"),
    "usage": ("Usage", "用法说明"),
    "extra examples": ("Extra examples", "额外例句"),
    "word family": ("Word family", "词族"),
    "examples from the corpus": ("Corpus examples", "语料库例句"),
    "business dictionary": ("Business Dictionary", "商务英语"),
    "encyclopedia": ("Encyclopedia", "百科"),
    "hint": ("Hint", "提示"),
    "origin": ("Word origin", "词源"),
    "word origin": ("Word origin", "词源"),
    "frequency": ("Frequency", "使用频率"),
    "graphies": ("Graphics", "图表"),
    "picture": ("Picture", "图片"),
    "pictures": ("Pictures", "图片"),
    "more like this": ("More like this", "相关词"),
    "topics": ("Topics", "话题"),
    "which word": ("Which word", "词语对比"),
    "study note": ("Study note", "学习提示"),
    "grammar patterns": ("Grammar patterns", "语法搭配"),
    "spoken": ("Spoken", "口语"),
    "note": ("Note", "说明"),
}

POS_RULE_MAP = {
    "noun": "n", "n": "n", "verb": "v", "v": "v",
    "adjective": "adj", "adj": "adj", "adverb": "adv", "adv": "adv",
    "modal verb": "v", "auxiliary verb": "v", "phrasal verb": "v",
    "linking verb": "v",
}
POS_TAG_MAP = {
    "noun": "noun", "verb": "verb", "adjective": "adj", "adverb": "adv",
    "pronoun": "pron", "preposition": "prep", "conjunction": "conj",
    "exclamation": "excl", "determiner": "det", "number": "num",
    "modal verb": "modal", "auxiliary verb": "aux", "linking verb": "linking-v",
    "phrasal verb": "phrasal-v", "prefix": "prefix", "suffix": "suffix",
    "combining form": "combining-form", "abbreviation": "abbr",
    "symbol": "symb", "idiom": "idiom", "definite article": "def-article",
    "indefinite article": "indef-article", "ordinal number": "ordinal-num",
    "infinitive marker": "inf-marker", "infin marker": "inf-marker",
    "short form": "short-form",
}

# ---------------------------------------------------------------------------
# MDX extraction / record iteration
# ---------------------------------------------------------------------------


def prepare_input(input_file):
    source = os.path.abspath(os.path.expanduser(str(input_file)))
    if not os.path.isfile(source):
        raise FileNotFoundError(f"Input dictionary file not found: {source}")
    if not source.lower().endswith(".mdx"):
        return source
    sidecar = source + ".txt"
    if (
        os.path.isfile(sidecar)
        and os.path.getsize(sidecar) > 0
        and os.path.getmtime(sidecar) >= os.path.getmtime(source)
    ):
        print(f"[*] Reusing extracted MDX text: {sidecar}")
        return sidecar
    try:
        from mdict_utils import reader as mdict_reader
    except ImportError as exc:
        raise RuntimeError("Direct MDX input requires mdict-utils") from exc
    print(f"[*] Extracting MDX source: {source}")
    os.makedirs(os.path.dirname(sidecar) or ".", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ldoce-extract-", dir=os.path.dirname(source)) as tmp:
        mdict_reader.unpack(tmp, source)
        produced = os.path.join(tmp, os.path.basename(source) + ".txt")
        if not os.path.isfile(produced):
            candidates = [p for p in glob.glob(os.path.join(tmp, "*.txt")) if os.path.getsize(p) > 0]
            if not candidates:
                raise RuntimeError("mdict-utils produced no text file")
            produced = max(candidates, key=os.path.getsize)
        shutil.move(produced, sidecar)
    print(f"[OK] Extracted MDX text: {sidecar}")
    return sidecar


def iter_records(path):
    with io.open(path, "r", encoding="utf-8", newline="") as handle:
        buf_key = None
        buf_lines = []
        for line in handle:
            line = line.rstrip("\r\n")
            if line == "</>":
                if buf_key is not None:
                    yield buf_key, "\n".join(buf_lines)
                buf_key, buf_lines = None, []
            elif buf_key is None and not buf_lines:
                buf_key = line
            else:
                buf_lines.append(line)
        if buf_key is not None:
            yield buf_key, "\n".join(buf_lines)


def count_lines(path):
    with io.open(path, "rb") as handle:
        return sum(1 for _ in handle)


SKIP_KEY_RE = re.compile(r"^(ACTIV:|ldoce\d+jpg)", re.IGNORECASE)


def clean_target(t):
    """@@@LINK targets in this MDX sometimes embed markup:
    'add<span class="OBJECT"> something <-></span> on' -> plain key."""
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", " ", t)
    t = strip_invisible(collapse_ws(t)).strip()
    return t.strip(" \t;")


def norm_target(t):
    return re.sub(r"[\s\u2194\u2009\u00a0]+", "", t).casefold()


def classify_record(key, content):
    k = strip_invisible(key).strip()
    if not k:
        return "skip", None
    if SKIP_KEY_RE.match(k):
        return "skip", None
    head = content.lstrip()
    if head.startswith("@@@LINK="):
        target = head[len("@@@LINK="):].split("\n")[0].split("|")[0].strip()
        return "redirect", clean_target(target) or None
    probe = content[:8000]
    if "entry_content" in probe or "ldoceEntry" in probe:
        return "entry", None
    return "skip", None


# ---------------------------------------------------------------------------
# Term index
# ---------------------------------------------------------------------------


class TermIndex:
    def __init__(self):
        self.exact = set()
        self.by_fold = {}
        self.by_norm = {}
        self.linkable = set()   # alias words that exist as redirect rows
        self.link_norm = {}
        self.rendered = set()

    def add(self, key):
        self.exact.add(key)
        self.by_fold.setdefault(key.casefold(), key)
        self.by_norm.setdefault(norm_target(key), key)

    def add_alias_word(self, key):
        self.linkable.add(key)
        self.link_norm.setdefault(norm_target(key), key)
        self.link_norm.setdefault(norm_target(key.replace("-", " ")), key)

    def finalize_rendered(self, rendered_keys):
        self.rendered = set(rendered_keys)

    def resolve(self, target):
        if not target:
            return None
        t = strip_invisible(target).strip()
        if not t or t.upper().startswith("ACTIV:"):
            return None
        if t in self.exact:
            return t
        folded = self.by_fold.get(t.casefold())
        if folded:
            return folded
        hy = t.replace(" ", "-")
        if hy in self.exact:
            return hy
        sp = t.replace("-", " ")
        if sp in self.exact:
            return sp
        hy_fold = self.by_fold.get(hy.casefold())
        if hy_fold:
            return hy_fold
        sp_fold = self.by_fold.get(sp.casefold())
        if sp_fold:
            return sp_fold
        # normalized: ignores whitespace / hyphen / <-> object-marker differences
        for cand in (norm_target(t), norm_target(t.replace("-", " ")),
                     norm_target(t.replace("-", ""))):
            hit = self.by_norm.get(cand)
            if hit:
                return hit
        if t in self.linkable:
            return t
        for cand in (norm_target(t), norm_target(t.replace("-", " ")),
                     norm_target(t.replace("-", ""))):
            hit = self.link_norm.get(cand)
            if hit:
                return hit
        return None

    def __contains__(self, item):
        return item in self.exact or item in self.linkable


def entry_target_from_href(href, title):
    href = (href or "").strip()
    match = re.match(r"^entry://([^#?]*)", href)
    if match:
        raw = unquote(match.group(1)).strip()
        return raw or strip_invisible(title or "").strip()
    if href and not re.match(r"^(sound|https?|javascript|#|media|pic|rel:|/)", href, re.IGNORECASE):
        return unquote(href).strip()
    return strip_invisible(title or "").strip() or None


# ---------------------------------------------------------------------------
# DOM -> structured content
# ---------------------------------------------------------------------------

from bs4 import BeautifulSoup, NavigableString, Tag  # noqa: E402


def classes_of(el):
    if not isinstance(el, Tag):
        return frozenset()
    return frozenset(el.get("class") or [])


class LdoceRenderer:
    def __init__(self, term_index, mode="bilingual", open_panels=False):
        self.terms = term_index
        self.mode = mode
        self.open_panels = open_panels
        self.stats = Counter()
        self.unknown_classes = Counter()
        self.current_key = None

    # -- child walking ------------------------------------------------------

    def _drop_translation(self, el, cls):
        """Recognize translation nodes, not language-switch click handlers.

        switch_siblings also decorates ENGLISH source nodes (LM5Switch.js);
        treating it as a Chinese marker would delete English definitions. A few
        REGISTERLAB translations carry only Chinese text without a cn_txt class.
        """
        if self.mode != "mono":
            return False
        if cls & ZH_CLASSES:
            return True
        if "REGISTERLAB" in cls:
            text = el.get_text(" ", strip=True)
            return bool(CJK_RE.search(text)) and not re.search(r"[A-Za-z]", text)
        return False

    def _content_text(self, text):
        text = sc_text(text)
        return MONO_USAGE_NOTE_RE.sub("NOT ", text) if self.mode == "mono" else text

    def _children_blocks(self, el):
        nodes = []
        for child in el.children:
            if isinstance(child, NavigableString):
                if child.__class__.__name__ in ("Doctype", "Comment", "Declaration",
                                                "ProcessingInstruction", "CData"):
                    continue
                text = self._content_text(str(child))
                if text:
                    nodes.append(text)
                continue
            if not isinstance(child, Tag):
                continue
            nodes.extend(self.render_element(child))
        nodes = merge_adjacent_text(nodes)
        # Native list semantics: wrap runs of senses / examples into <ol>/<ul>.
        #
        # This is the ONE place that sees the direct children of every parent, so
        # grouping here covers senses inside div.ld-entry as well as at the top
        # level. Doing it at render_record() instead grouped nothing, because
        # ld-entry is already a finished subtree by then (verified: "tag":"ol"
        # count was 0 in the output).
        nodes = group_into_list(nodes, SENSE_ITEM_CLASSES, "ld-senselist", "ol")
        nodes = group_into_list(nodes, EXAMPLE_ITEM_CLASSES, "ld-exlist", "ul")
        # colour/weight that must survive when no stylesheet is loaded
        nodes = add_inline_semantics(nodes)
        return nodes

    def render_element(self, el):
        cls = classes_of(el)
        if self._drop_translation(el, cls):
            return []
        if is_dropped(cls) or el.name in DROP_TAGS:
            return []
        if "portrait" in cls:
            parent = el.parent
            has_landscape = parent is not None and any(
                isinstance(s, Tag) and "landscape" in classes_of(s) for s in parent.children
            )
            if has_landscape:
                return []  # keep the full-size landscape duplicate only
        if el.name in ("div", "aside", "section", "article", "main"):
            return self.render_div(el, cls)
        if el.name == "h1":
            return []
        if el.name in ("ul", "ol"):
            return self._render_list(el)
        if el.name == "table":
            return self._render_table(el)
        if el.name == "p":
            inner = self._children_blocks(el)
            return [sc("div", inner, cls="ld-para")] if inner else []
        if "Head" in cls:
            return [self.render_head(el)]
        if "Inflections" in cls:
            return [self.render_inflections(el)]
        forced = cls & BLOCK_TOKENS
        if forced:
            return [self.render_block_by_token(el, self._first_forced(forced))]
        if "wordfams" in cls or cls & PANEL_CLASSES or "etym" in cls or "assetlink" in cls \
                or "asset" in cls:
            return self.render_div(el, cls)
        if self._has_block_child(el):
            if "Head" in cls:
                return [self.render_head(el)]
            if "Inflections" in cls:
                return [self.render_inflections(el)]
            return self._children_blocks(el)
        return self.render_inline_node(el)

    def _render_list(self, el):
        items = []
        for li in el.find_all("li", recursive=False):
            inner = self._children_blocks(li)
            if inner:
                items.append(sc("li", inner))
        if not items:
            return []
        return [sc(el.name, items, cls="ld-list")]

    def _render_table(self, el):
        rows = []
        for tr in el.find_all("tr"):
            cells = []
            for cell in tr.find_all(["td", "th"], recursive=False):
                inner = self._children_blocks(cell)
                cells.append(sc(cell.name, inner, cls="ld-td" if cell.name == "td" else "ld-th"))
            if cells:
                rows.append(sc("tr", cells))
        if not rows:
            return []
        return [sc("table", [sc("tbody", rows)], cls="ld-table")]

    def _first_forced(self, forced):
        for token, _ in BLOCK_MAP:
            if token in forced:
                return token
        return sorted(forced)[0]

    def _has_block_child(self, el):
        for child in el.children:
            if isinstance(child, Tag):
                if child.name in ("div", "ul", "ol", "table", "details", "h1", "p",
                                  "section", "aside"):
                    return True
                ccls = classes_of(child)
                if ccls & (BLOCK_TOKENS | PANEL_CLASSES | {
                        "Sense", "Subentry", "ldoceEntry", "Entry", "asset",
                        "assetlink", "wordfams", "Head", "Inflections", "etym"}):
                    return True
        return False

    # -- div dispatch -------------------------------------------------------

    def render_div(self, el, cls):
        # A5 residual: the Chinese side of a bilingual note is usually a SPAN,
        # which render_inline_node() drops in mono mode -- but the ErrorBox note
        # uses a DIV:
        #   <div class="cn_txt"> 不要说<span class="en_txt"> </span>
        #   <span class="BADCOLLO">...<div class="cn_txt">
        # A div never reaches render_inline_node(), so it fell through to the
        # generic branch below and leaked Chinese into a package that declares
        # targetLanguage "en". Checked before every other branch and only in
        # mono, so bilingual output is bit-for-bit unchanged.
        if self._drop_translation(el, cls):
            return []
        if "asset" in cls:
            return self.render_asset(el, cls)
        if "assetlink" in cls:
            return self.render_assetlink(el, cls)
        panel_cls = cls & PANEL_CLASSES
        if panel_cls:
            if cls & PANEL_SKIP_CLASSES:
                return []
            box = self.render_box(el, sorted(panel_cls)[0])
            return [box] if box else []
        if "wordfams" in cls:
            wf = self.render_wordfams(el)
            return [wf] if wf else []
        if "etym" in cls:
            et = self.render_etym(el)
            return [et] if et else []
        if cls & {"ldoceEntry", "Entry"}:
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
        if "Head" in cls and "frequent" in cls:
            return [self.render_head(el)]
        if "Inflections" in cls:
            return [self.render_inflections(el)]
        if "BoxPanel" in cls:
            inner = self._children_blocks(el)
            return [sc("div", inner, cls="ld-panel-boxbody")] if inner else []
        if "Head" in cls:
            return [self.render_head(el)]
        forced = cls & BLOCK_TOKENS
        if forced:
            return [self.render_block_by_token(el, self._first_forced(forced))]
        inner = self._children_blocks(el)
        if not inner:
            return []
        return [sc("div", inner)]

    def render_block_by_token(self, el, token):
        if token == "EXAMPLE":
            return self.render_example(el, classes_of(el))
        scname = BLOCK_SCNAME.get(token) or "ld-block"
        if token in ("SECHEADING", "HEADING", "boxheader", "spokensectheader"):
            text = self._label_text(el)
            return sc("div", [text], cls=scname) if text else sc("div", [], cls="ld-empty")
        inner = self._children_blocks(el)
        if not inner:
            return sc("div", [], cls="ld-empty")
        cls = classes_of(el)
        node_cls = scname
        if "cross_sense" in cls:
            node_cls = "ld-sense-cross"
        elif "merge_sense" in cls:
            node_cls = "ld-sense-merge"
        is_sense = node_cls.startswith("ld-sense")
        marker = SCHEME_B_MARKERS.get(node_cls)
        if marker:
            inner = [sc("span", marker, cls="ld-mark")] + list(inner)
        if is_sense:
            # Native list semantics: a sense is an <li> inside the <ol> that
            # _children_blocks wraps around it, and the UA marker is switched off
            # on that <ol> (UA_MARKER_OFF). The number the reader sees is
            # therefore always the SOURCE number carried by our own chip -- see
            # the numbering note above SEMANTIC_INLINE_STYLES (audit R2).
            if node_cls.startswith("ld-sense") and starts_with_sense_number(inner):
                node_cls += " ld-sense-n"
            return sc("li", inner, cls=node_cls)
        return sc("div", inner, cls=node_cls)

    # -- semantic blocks ----------------------------------------------------

    def render_head(self, el):
        # Head children are emitted in SOURCE DOM order. The original stylesheet has
        # no `order:`/absolute positioning anywhere in the head rules, and the real
        # rendering (LM5style.css from the .mdd, measured in Chrome) confirms the
        # visual order equals the DOM order:
        #   HWD > HOMNUM > PronCodes > LEVEL > FREQ > AC > POS > GRAM > GEO >
        #   REGISTERLAB > Variant > HOMOPHONE > Inflections
        # Building the line from a fixed template (hwd, gram, pron, pos, chips)
        # silently moved GRAM in front of the pronunciation, e.g.
        # "18-wheeler [countable] /.../ noun" instead of "18-wheeler /.../ noun [countable]".
        out = []          # children of div.ld-head, in DOM order
        hwd_nodes = []    # the headword cluster (HWD + HYP + HOMNUM) -> one ld-hwd-wrap

        def hwd_collect(node, target):
            for ch in getattr(node, "children", []):
                if isinstance(ch, NavigableString):
                    text = sc_text(str(ch))
                    if text:
                        target.append(text)
                elif isinstance(ch, Tag):
                    ccls = classes_of(ch)
                    if is_dropped(ccls):
                        continue
                    if "HYP" in ccls:
                        # HYP is not always a syllable dot: 106672 are "·" but 21451 are
                        # primary stress "ˈ" and 17903 secondary stress "ˌ". Hardcoding "·"
                        # corrupted 27% of them (e.g. "second class" -> "·second ·class").
                        sep = sc_text(ch.get_text("", strip=True)) or "\u00b7"
                        # They also need different styling: a syllable dot is a grey
                        # separator, a stress mark is part of the headword and must
                        # inherit its colour with no padding (see generate_css).
                        target.append(sc("span", sep,
                                         cls="ld-hyp" if sep == "\u00b7" else "ld-stress"))
                    elif "HOMNUM" in ccls:
                        text = sc_text(ch.get_text("", strip=True))
                        if text:
                            target.append(sc("span", text, cls="ld-sup"))
                    else:
                        hwd_collect(ch, target)

        def flush_hwd():
            # Close the headword cluster so the next element lands after it, keeping
            # HWD+HOMNUM adjacent (source DOM is HWD -> HOMNUM in 12612/12612 heads).
            if not hwd_nodes:
                return
            if not any(isinstance(p, dict) or (isinstance(p, str) and p.strip())
                       for p in hwd_nodes):
                hwd_nodes.clear()
                return
            merged = []
            for part in hwd_nodes:
                if isinstance(part, dict):
                    merged.append(part)
                elif part.strip():
                    if merged and isinstance(merged[-1], str) and not merged[-1].endswith(" "):
                        merged[-1] = merged[-1] + " "
                    merged.append(part)
                elif merged and isinstance(merged[-1], str) and merged[-1].strip():
                    # whitespace-only run between two text runs -> single separator;
                    # leading whitespace and runs after an element are dropped, otherwise
                    # the headword line gets stray gaps (e.g. "improve   /\u026am\u02c8pru\u02d0v/").
                    if not merged[-1].endswith(" "):
                        merged[-1] = merged[-1] + " "
            if merged:
                out.append(sc("span", merged, cls="ld-hwd-wrap"))
            hwd_nodes.clear()

        for child in el.children:
            if isinstance(child, NavigableString):
                text = sc_text(str(child))
                if text:
                    hwd_nodes.append(text)
                continue
            if not isinstance(child, Tag):
                continue
            cls = classes_of(child)
            if self._drop_translation(child, cls):
                continue
            if is_dropped(cls):
                continue
            if "HWD" in cls:
                parts = []
                hwd_collect(child, parts)
                hwd_nodes.append(sc("span", parts or [sc_text(child.get_text("", strip=True))],
                                    cls="ld-hwd"))
            elif "HOMNUM" in cls:
                text = sc_text(child.get_text("", strip=True))
                if text:
                    # source DOM order is always HWD -> HOMNUM (12612/12612 heads),
                    # and .HOMNUM is `vertical-align:super`, so it renders in place:
                    # insert(0, ...) used to give "1abandon" instead of "abandon1".
                    hwd_nodes.append(sc("span", text, cls="ld-sup"))
            elif "Inflections" in cls:
                flush_hwd()
                inner = self.render_inflections(child).get("content") or []
                if inner:
                    out.append(sc("span", " \u00b7 ", cls="ld-sep"))
                    out.extend(inner)
            elif "PronCodes" in cls or "PRON" in cls or "AMEVARPRON" in cls:
                pron_text = sc_text(child.get_text("", strip=True))
                if pron_text:
                    flush_hwd()
                    pron_cls = "ld-pron-amevar" if "AMEVARPRON" in cls else "ld-pron"
                    out.append(sc("span", pron_text, cls=pron_cls))
            elif "lm5pp_POS" in cls:
                # One span per source span: entries such as "the" carry two POS spans
                # ("definite article" + ", determiner"); a single pos_text slot used to
                # keep only the last one.
                label = self._pick_landscape(child)
                if label:
                    flush_hwd()
                    out.append(sc("span", sc_text(label).lstrip(" ,;"), cls="ld-pos"))
            elif "GRAM" in cls:
                label = self._no_portrait_text(child)
                if label:
                    flush_hwd()
                    out.append(sc("span", sc_text(label), cls="ld-gram"))
            elif "LEVEL" in cls:
                stars = sc_text(child.get_text("", strip=True))
                title = strip_invisible(child.get("title") or "") or "Core vocabulary"
                if stars:
                    flush_hwd()
                    out.append(sc("span", stars, cls="ld-level", title=title))
            elif "FREQ" in cls:
                text = sc_text(child.get_text("", strip=True))
                title = strip_invisible(child.get("title") or "") or None
                if text:
                    flush_hwd()
                    out.append(sc("span", text, cls="ld-freq", title=title))
            elif "tooltip" in cls or "HYPHENATION" in cls:
                # tooltip: carries no visual payload of its own (the ●●● live in LEVEL,
                # which is matched above); HYPHENATION: syllable-split *display duplicate*
                # of the headword, `display:none` in the original stylesheet and toggled
                # by LM5Switch.js -- emitting it would read "abandona·ban·don".
                pass
            else:
                # Any other Head child is a label chip (register / geography / field /
                # variant / homophone / academic-word / ...). Most of them already have
                # an entry in CHIP_MAP / INLINE_MAP -- route them through it and render
                # as a real chip so nested entry:// links and title tooltips survive.
                # (Before: the text was glued straight into the headword, e.g. "seeing"
                # rendered as "see\u00b7ingspoken".)
                chip_cls = None
                for token in CHIP_PRIORITY:
                    if token in cls:
                        chip_cls = CHIP_MAP[token]
                        break
                if chip_cls is None:
                    for token, (map_cls, _flags) in INLINE_MAP.items():
                        if token in cls:
                            chip_cls = map_cls
                            break
                if chip_cls:
                    if any(isinstance(x, Tag) for x in child.children):
                        inner = merge_adjacent_text(self._children_blocks(child))
                    else:
                        # text-only label (REGISTERLAB / FIELD / AC ...): skip the
                        # full recursive render, which is what made this fix cost
                        # ~40% extra build time in the first version.
                        inner = [sc_text(child.get_text(" ", strip=True))]
                    if sc_has_text(inner):
                        flush_hwd()
                        out.append(sc("span", inner, cls=chip_cls,
                                      title=strip_invisible(child.get("title") or "") or None))
                    continue
                for c in cls:
                    self.unknown_classes[c] += 1
                text = sc_text(child.get_text(" ", strip=True))
                if text:
                    flush_hwd()
                    out.append(text)
        flush_hwd()
        # Portable separation between the head atoms.
        #
        # Everything that visually separates the chips of a head (pronunciation,
        # the OOO level, S2/W1 codes, AWL, part of speech, grammar box) comes from
        # CSS margins/backgrounds/borders, not from whitespace in the content. A
        # host that drops the stylesheet therefore renders
        #     'a·ban·don1/əˈbændən/●●○W3AWLverb[transitive]'
        # (28,252 of 76,554 heads have no whitespace at all). One literal space
        # per boundary costs a byte and is invisible while the stylesheet is
        # present. GLUE classes are excluded so 'a·ban·don' keeps its dots.
        out = separate_head_atoms(out)
        return sc("div", out, cls="ld-head")

    def _pick_landscape(self, el):
        """Label of a landscape/portrait pair, with the abbreviation excluded.

        When the pair exists this delegates to _no_portrait_text(), which keeps
        the loose qualifier beside it: entry '4-F' reads
        '<span class="lm5pp_POS"> noun, <span class="landscape">adjective</span>
        <span class="portrait">adj</span></span>' and used to render as the bare
        'adjective', losing the visible 'noun,'. This is the same defect D14
        fixed for GRAM (see REVIEW T9/D14); POS was simply left on the old
        helper. Spans without a landscape keep their previous text, so the
        behaviour change is confined to the spans that carry a pair.
        """
        if el.find("span", class_="landscape") is None:
            return el.get_text(" ", strip=True)
        return self._no_portrait_text(el)

    def _no_portrait_text(self, el):
        """Full grammatical label, e.g. '[singular, uncountable]'.

        A GRAM span is:  ' [' + qualifier text + <span class=landscape>full</span>
        + <span class=portrait><span class=cap>U</span></span> + ']'  -- the
        brackets and any loose qualifier ('singular,', 'only after noun') are
        siblings of the landscape span, so _pick_landscape() dropped them and we
        emitted a bare 'uncountable'. The portrait span is the abbreviation the
        original JS swaps in, so it is skipped exactly like _pick_landscape does.

        Also used for the GEO labels inside an Inflections sequence, where the same
        mistake dropped the loose qualifier ('busses especially American English'
        used to lose 'especially').
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

    def _label_text(self, el):
        """Text of a heading/label, dropping the Chinese side in mono mode.

        Section headings and sense-group labels were read with get_text(), which
        flattens span.cn_txt into a single string and so bypasses the mono filter
        in render_inline_node(). The mono package declares targetLanguage "en"
        but every one of the 243 candidate entries leaked Chinese into its
        headings ('age' -> '- Meaning 5: a particular period of history 时代，世代').
        Bilingual output is untouched, so the shipped package is unaffected.
        """
        if self.mode == "bilingual":
            return sc_text(el.get_text(" ", strip=True))
        parts = []
        for d in el.descendants:
            if not isinstance(d, NavigableString):
                continue
            anc = d.parent
            skip = False
            while anc is not None and anc is not el:
                if classes_of(anc) & ZH_CLASSES:
                    skip = True
                    break
                anc = anc.parent
            if not skip:
                parts.append(str(d))
        return sc_text(collapse_ws(" ".join(p.strip() for p in parts)).strip())

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
            cls="ld-panel-online",
        )
        if self.open_panels:
            details["open"] = True
        return details

    INFL_FORM_CLASSES = {
        "PLURALFORM", "PASTTENSE", "PASTPART", "PRESPART", "T3PERSSING",
        "PTandPP", "PTandPPX", "PRESPARTX", "T3PERSSINGX", "FULLFORM",
        "COMP", "SUPERL",
    }
    INFL_SEP = " · "

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
          * <span class="PronCodes"> the inflected form's own IPA, e.g.
            'worse /wɜːs $ wɜːrs/' (816 blocks)
        Emitting the forms alone silently merged two regional paradigms into one
        undifferentiated list, and stripped every inflected pronunciation.
        """
        nodes = []
        seen = set()

        def push_sep():
            if nodes and nodes[-1] != self.INFL_SEP:
                nodes.append(self.INFL_SEP)

        def push_form(raw):
            text = sc_text(raw).strip("() ")
            text = re.sub(r"\s+", " ", text)
            for part in re.split(r"[,;]", text):
                part = part.strip(" ,;.")
                if part and part not in seen:
                    seen.add(part)
                    push_sep()
                    nodes.append(sc("span", part, cls="ld-infl-form"))

        def push_annot(raw, cls_name):
            # ",;." as well as the brackets: a LINKWORD can carry the list
            # separator itself (', first person singular'), which duplicates our
            # own ' · ' separator.
            text = sc_text(raw).strip(" ,;.()")
            text = re.sub(r"\s+", " ", text)
            if text and text not in seen:
                seen.add(text)
                push_sep()
                nodes.append(sc("span", text, cls=cls_name))

        def text_no_portrait(node):
            """Text of `node` with every span.portrait subtree removed."""
            parts = []
            for d in node.descendants:
                if not isinstance(d, NavigableString):
                    continue
                anc = d.parent
                skip = False
                while anc is not None and anc is not node:
                    if "portrait" in classes_of(anc):
                        skip = True
                        break
                    anc = anc.parent
                if not skip:
                    parts.append(str(d))
            return collapse_ws("".join(parts)).strip()

        def label_and_form(span):
            """Split a form from the label(s) embedded inside it.

            The label is span.infllab ('past tense and past participle') or
            span.italic ('plural'); the original styles both italic. Its
            span.portrait sibling is the narrow-screen abbreviation and must not
            reach the output (see the module docstring). Returns (labels, form).
            """
            labs = [sub for sub in span.find_all("span")
                    if {"infllab", "italic"} & classes_of(sub)]
            if not labs:
                return [], span.get_text(" ", strip=True)
            parts = []
            for d in span.descendants:
                if not isinstance(d, NavigableString):
                    continue
                anc = d.parent
                skip = False
                while anc is not None and anc is not span:
                    if any(anc is l for l in labs):
                        skip = True
                        break
                    anc = anc.parent
                if not skip:
                    parts.append(str(d))
            labels = [t for t in (self._no_portrait_text(l) for l in labs) if t]
            return labels, collapse_ws("".join(parts)).strip()

        for child in el.children:
            if isinstance(child, NavigableString):
                continue
            cls = classes_of(child)
            if cls & self.INFL_FORM_CLASSES:
                labels, form = label_and_form(child)
                for lab in labels:
                    push_annot(lab, "ld-infl-lab")
                if form:
                    push_form(form)
                continue
            if "GEO" in cls:
                push_annot(self._no_portrait_text(child), "ld-infl-region")
                continue
            # A4: the inflected form's own pronunciation. The source pairs
            #   <span class="COMP">...worse</span><span class="PronCodes">
            #   <span class="PRON">wɜːs</span><span class="AMEVARPRON"> $ wɜːrs
            #   </span></span>
            # -- PronCodes matched no branch above and the fallback below only
            # collects form classes, so the IPA was silently dropped: 'bad' kept
            # 'comparative · worse · superlative · worst' and lost both blocks
            # (596 entries / 816 blocks corpus-wide). This is TEXT, not an audio
            # asset, so the "no audio in structured content" decision never
            # covered it. Deliberately not routed through seen{}: the block
            # belongs to the form that precedes it, and two forms may share one
            # pronunciation string.
            if "PronCodes" in cls or "PRON" in cls or "AMEVARPRON" in cls:
                pron = sc_text(child.get_text("", strip=True))
                if pron:
                    push_sep()
                    nodes.append(sc("span", pron, cls="ld-infl-pron"))
                continue
            if "LINKWORD" in cls or "italic" in cls:
                push_annot(child.get_text(" ", strip=True), "ld-infl-ann")
                continue
            if child.find("span", recursive=True) is not None:
                for sub in child.find_all("span", recursive=True):
                    scls = classes_of(sub)
                    if scls & self.INFL_FORM_CLASSES:
                        labels, form = label_and_form(sub)
                        for lab in labels:
                            push_annot(lab, "ld-infl-lab")
                        if form:
                            push_form(form)
        if not nodes:
            text = sc_text(text_no_portrait(el)).strip()
            if text:
                nodes = [sc("span", text, cls="ld-infl-form")]
        return sc("span", nodes, cls="ld-infl")

    def render_example(self, el, cls):
        english = el.find("span", class_="english", recursive=False)
        scope = english if english is not None else el
        cn_blocks = [c for c in scope.find_all("div", class_="cn_txt")]

        def is_in_cn(node):
            cur = node
            while cur is not None and cur is not scope:
                if any(cur is b for b in cn_blocks):
                    return True
                cur = cur.parent
            return False

        en_nodes = []
        for child in scope.children:
            if isinstance(child, NavigableString):
                if is_in_cn(child):
                    continue
                text = self._content_text(str(child))
                if text:
                    en_nodes.append(text)
                continue
            if not isinstance(child, Tag) or is_in_cn(child):
                continue
            ccls = classes_of(child)
            if is_dropped(ccls):
                continue
            if "EXAMPLE" in ccls:
                en_nodes.extend(self.render_div(child, ccls))
                continue
            if self._has_block_child(child):
                en_nodes.extend(self.render_element(child))
            else:
                en_nodes.extend(self.render_inline_node(child))
        cn_nodes = []
        if self.mode != "mono":
            for cn in cn_blocks:
                inner = merge_adjacent_text(self._children_blocks(cn))
                if sc_has_text(inner):
                    cn_nodes.append(sc("div", inner, cls="ld-excn", lang="zh"))
        if "GramExa" in cls:
            flavor = "ld-gramexa"
        elif "ColloExa" in cls:
            flavor = "ld-colloexa"
        elif "GOODEXA" in cls or "GOODCOLLO" in cls:
            flavor = "ld-ex-good"
        elif "BADEXA" in cls or "BADCOLLO" in cls or "dont_say" in cls:
            flavor = "ld-ex-bad"
        else:
            flavor = "ld-ex"
        out = list(en_nodes) + cn_nodes
        if not out:
            return sc("div", [], cls="ld-empty")
        # Scheme B: also write the leading marker into the content. With a
        # stylesheet present the ld-mark span is display:none and the ::before
        # rule draws the character, so the visual result is unchanged; a host with
        # no stylesheet (Anki export, plain HTML) still shows it.
        marker = SCHEME_B_MARKERS.get(flavor)
        if marker:
            out = [sc("span", marker, cls="ld-mark")] + out
        # examples are list members: _children_blocks groups consecutive ones into
        # a <ul>, so the browser supplies the bullet and the indent with no CSS
        tag = "li" if flavor in EXAMPLE_ITEM_CLASSES else "div"
        return sc(tag, out, cls=flavor)

    def render_box(self, el, panel_token):
        for junk in el.find_all(["script", "style", "input", "label", "img"]):
            junk.decompose()
        heading = el.find("span", class_="heading") or el.find("span", class_="lm5ppBoxHead")
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
            gtext = self._label_text(gloss).strip()
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
        if not sc_has_text(body):
            return None
        summary_children = [sc("span", title_en, cls="ld-panel-title")]
        if title_zh and self.mode == "bilingual":
            summary_children.append(sc("span", title_zh, cls="ld-panel-title-zh", lang="zh"))
        details = sc(
            "details",
            [sc("summary", summary_children, cls="ld-panel-sum"),
             sc("div", body, cls="ld-panel-body")],
            cls="ld-panel",
        )
        if self.open_panels:
            details["open"] = True
        return details

    def _panel_title(self, heading, panel_token):
        raw = ""
        if heading is not None:
            clone = BeautifulSoup(str(heading), "html.parser").find("span")
            for junk in clone.find_all("span", class_="foldsign"):
                junk.extract()
            cn_text = None
            if self.mode == "mono":
                # Skip ALL nested cn_txt/cn_txt_ext nodes, not just the first one.
                raw = self._label_text(clone).strip()
            else:
                # Preserve the established bilingual title layout.
                cn_part = clone.find("span", class_="cn_txt")
                if cn_part is not None:
                    cn_text = collapse_ws(cn_part.get_text(" ", strip=True))
                    cn_part.extract()
                raw = collapse_ws(clone.get_text(" ", strip=True))
            if cn_text:
                key = raw.casefold().strip(" :：.。")
                got = PANEL_TITLES_ZH.get(key)
                en = got[0] if got else (raw or "Note")
                return en, cn_text
        key = raw.casefold().strip(" :：.。")
        got = PANEL_TITLES_ZH.get(key)
        if got:
            return got if self.mode == "bilingual" else (got[0], None)
        if raw:
            return raw, None
        got = PANEL_FALLBACK_TITLES.get(panel_token)
        if got:
            return got if self.mode == "bilingual" else (got[0], None)
        return "Note", None

    def render_asset(self, el, cls):
        header_type = cls - {"asset", "div"}
        nxt = el.next_sibling
        bodies = []
        while nxt is not None:
            if isinstance(nxt, Tag):
                if "assetlink" in classes_of(nxt):
                    bodies.append(nxt)
                    nxt = nxt.next_sibling
                    continue
                if nxt.get_text(strip=True):
                    break
            nxt = nxt.next_sibling
        if bodies:
            result = self.render_assetlink(bodies, classes_of(bodies[0]), header_type, header=el)
            for b in bodies:
                b.extract()  # consumed: stop the parent walker re-rendering them
            return result
        return []

    def render_assetlink(self, els, cls, header_type=None, header=None):
        if not isinstance(els, list):
            els = [els]
        for el in els:
            for junk in el.find_all(["script", "style", "img", "input", "label"]):
                junk.decompose()
        intro = None
        if header is not None:
            span = header.find("span", class_="asset_intro")
            if span is not None:
                intro = collapse_ws(span.get_text(" ", strip=True))
        types = set(header_type or ()) | (cls - {"assetlink", "div"})
        joined = " ".join(sorted(t.casefold() for t in types))
        title_en = title_zh = None
        if intro:
            got = PANEL_TITLES_ZH.get(intro.casefold().rstrip(":：").strip())
            if got:
                title_en, title_zh = got
            else:
                title_en = intro
        if title_en is None:
            if "bussdict" in joined:
                title_en, title_zh = "Business Dictionary", "商务英语"
            elif "corpus" in joined:
                title_en, title_zh = "Corpus examples", "语料库例句"
            elif "encyc" in joined:
                title_en, title_zh = "Encyclopedia", "百科"
            elif "online" in joined:
                title_en, title_zh = "LDOCE Online", "在线增补"
            else:
                title_en, title_zh = "Extra content", "补充内容"
        if self.mode == "mono":
            title_zh = None
        groups = []
        orphan = False
        for el in els:
            sub = el.find_all("span", class_="exaGroup", recursive=False)
            if not sub:
                orphan = True
                continue
            for group in sub:
                node = self.render_exa_group(group)
                if node:
                    groups.append(node)
        if orphan:
            for el in els:
                inner = merge_adjacent_text(self._children_blocks(el))
                if sc_has_text(inner):
                    groups.append(sc("div", inner, cls="ld-exagroup"))
        if not groups:
            return []
        summary = [sc("span", title_en, cls="ld-panel-title")]
        if title_zh:
            summary.append(sc("span", title_zh, cls="ld-panel-title-zh", lang="zh"))
        details = sc(
            "details",
            [sc("summary", summary, cls="ld-panel-sum"),
             sc("div", groups, cls="ld-panel-body")],
            cls="ld-panel-corpus",
        )
        if self.open_panels:
            details["open"] = True
        return [details]

    def render_exa_group(self, group):
        nodes = []
        title = group.find("span", class_="title", recursive=False)
        if title is not None:
            text = sc_text(title.get_text(" ", strip=True))
            if text:
                nodes.append(sc("div", [text], cls="ld-exagroup-title"))
        items = []
        for exa in group.find_all("span", class_="exa", recursive=False):
            body = merge_adjacent_text(self._children_blocks(exa))
            if not sc_has_text(body):
                continue
            strip_leading_bullet(body)
            kind = (exa.get("type") or "").strip().lower()
            if kind not in ("corpus", "dics", "encyc", "online", "phrases"):
                kind = ""
            cls = "ld-corpexa-" + kind if kind else "ld-corpexa"
            # Scheme B (see render_example): re-add the bullet we just stripped,
            # this time inside the content and hidden by CSS when a stylesheet is
            # available.
            marker = SCHEME_B_MARKERS.get(cls)
            if marker:
                body = [sc("span", marker, cls="ld-mark")] + list(body)
            items.append(sc("li", body, cls=cls))
        if items:
            # UA_MARKER_OFF like every other list we emit: the bullet is carried by
            # the ld-mark span above, so a host with no stylesheet must not ALSO get
            # the UA's disc (it would read "• • example"). This producer was missed
            # when the marker suppression was introduced.
            nodes.append(sc("ul", items, cls="ld-corpulist", style=dict(UA_MARKER_OFF)))
        if not nodes:
            return None
        return sc("div", nodes, cls="ld-exagroup")

    def render_wordfams(self, el):
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
                #
                # The antonym word is an <a> when it has an entry to link to, but a
                # bare <span class="w"> / <span class="w rootword"> when it does not.
                # The bare form used to fall through to the generic inline branch,
                # losing the word-family styling (and showing up in the unknown-class
                # report as w/rootword/crossRef). Handle the children explicitly.
                parts = []
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
                if sc_has_text(parts):
                    node = sc("span", parts, cls="ld-wf-opp")
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
        body = [g for g in children if g.get("content")]
        if not body:
            return None
        summary = [sc("span", "Word family", cls="ld-panel-title")]
        if self.mode == "bilingual":
            summary.append(sc("span", "词族", cls="ld-panel-title-zh", lang="zh"))
        details = sc(
            "details",
            [sc("summary", summary, cls="ld-panel-sum"),
             sc("div", body, cls="ld-panel-body")],
            cls="ld-panel-wf",
        )
        if self.open_panels:
            details["open"] = True
        return details

    def render_etym(self, el):
        nodes = []
        for child in el.children:
            if isinstance(child, NavigableString):
                text = sc_text(str(child))
                if text:
                    nodes.append(text)
                continue
            if not isinstance(child, Tag):
                continue
            cls = classes_of(child)
            if is_dropped(cls) or "asset_intro" in cls or "Head" in cls:
                continue
            if "Sense" in cls:
                for inner_el in child.children:
                    if isinstance(inner_el, Tag):
                        nodes.extend(self.render_element(inner_el))
                    elif isinstance(inner_el, NavigableString):
                        text = sc_text(str(inner_el))
                        if text:
                            nodes.append(text)
                continue
            nodes.extend(self.render_element(child))
        nodes = merge_adjacent_text(nodes)
        if not sc_has_text(nodes):
            return None
        summary = [sc("span", "Word origin", cls="ld-panel-title")]
        if self.mode == "bilingual":
            summary.append(sc("span", "词源", cls="ld-panel-title-zh", lang="zh"))
        details = sc(
            "details",
            [sc("summary", summary, cls="ld-panel-sum"),
             sc("div", nodes, cls="ld-panel-body")],
            cls="ld-panel-etym",
        )
        if self.open_panels:
            details["open"] = True
        return details

    # -- inline -------------------------------------------------------------

    def render_inline_node(self, el):
        cls = classes_of(el)
        if self._drop_translation(el, cls):
            return []
        if is_dropped(cls) or el.name in DROP_TAGS:
            return []
        if "Head" in cls:
            return [self.render_head(el)]
        if "Inflections" in cls:
            return [self.render_inflections(el)]
        if "portrait" in cls:
            parent = el.parent
            has_landscape = parent is not None and any(
                isinstance(s, Tag) and "landscape" in classes_of(s) for s in parent.children
            )
            if has_landscape:
                return []
        if el.name == "br":
            return [sc("br")]
        if el.name == "img":
            return []
        if el.name in ("b", "strong"):
            inner = self._children_blocks(el)
            return [sc("span", inner, style={"fontWeight": "bold"})] if inner else []
        if el.name in ("i", "em"):
            inner = self._children_blocks(el)
            return [sc("span", inner, style={"fontStyle": "italic"})] if inner else []
        if el.name == "u":
            inner = self._children_blocks(el)
            return [sc("span", inner, style={"textDecorationLine": "underline"})] \
                if inner else []
        if el.name == "sup":
            inner = self._children_blocks(el)
            return [sc("span", inner, style={"verticalAlign": "super",
                                             "fontSize": "smaller"})] if inner else []
        if el.name == "sub":
            inner = self._children_blocks(el)
            return [sc("span", inner, style={"verticalAlign": "sub",
                                             "fontSize": "smaller"})] if inner else []
        if self._has_block_child(el):
            if "Head" in cls:
                return [self.render_head(el)]
            if "Inflections" in cls:
                return [self.render_inflections(el)]
            return self._children_blocks(el)
        if el.name == "a":
            return self.render_link(el, cls)
        if "DEF" in cls:
            return self.render_def(el)
        if "cn_txt" in cls or "cn_txt_ext" in cls:
            if self.mode == "mono":
                return []
            inner = self._children_blocks(el)
            return [sc("span", inner, cls="ld-zh", lang="zh")] if sc_has_text(inner) else []
        if "HYP" in cls:
            # Same split as render_head's hwd_collect: HYP may hold a syllable dot
            # or a stress mark, and they need different styling. (Was mapped
            # unconditionally to ld-hyp in INLINE_MAP.)
            sep = sc_text(el.get_text("", strip=True)) or "\u00b7"
            return [sc("span", sep, cls="ld-hyp" if sep == "\u00b7" else "ld-stress")]
        chip = None
        for token in CHIP_PRIORITY:
            if token in cls:
                chip = CHIP_MAP[token]
                break
        if chip:
            inner = self._children_blocks(el)
            if not sc_has_text(inner):
                return []
            lang = "zh" if chip == "ld-actcn" else None
            title = strip_invisible(el.get("title") or "") or None
            return [sc("span", inner, cls=chip, lang=lang, title=title)]
        for token, (map_cls, flags) in INLINE_MAP.items():
            if token in cls:
                inner = self._children_blocks(el)
                if not sc_has_text(inner):
                    return []
                lang = "zh" if flags.get("zh") else None
                title = strip_invisible(el.get("title") or "") or None
                return [sc("span", inner, cls=map_cls, lang=lang, title=title)]
        if cls & UNWRAP_CLASSES:
            return self._children_blocks(el)
        if el.name in ("span", "font"):
            for c in cls:
                self.unknown_classes[c] += 1
            inner = self._children_blocks(el)
            if not sc_has_text(inner):
                return []
            style = {}
            raw_style = (el.get("style") or "").lower()
            if "italic" in raw_style:
                style["fontStyle"] = "italic"
            if "bold" in raw_style:
                style["fontWeight"] = "bold"
            return [sc("span", inner, style=style or None)]
        for c in cls:
            self.unknown_classes[c] += 1
        return self._children_blocks(el)

    def render_link(self, el, cls):
        href = (el.get("href") or "").strip()
        if re.search(r"topic-full/?$", href, re.IGNORECASE):
            return []  # "Show entries from Topic: X" UI junk
        if not href or href.startswith("#") or re.match(
                r"^(sound|javascript|media|pic|rel:|/|https?:)", href, re.IGNORECASE):
            return self._children_blocks(el) if el.get_text(strip=True) else []
        target = clean_target(entry_target_from_href(href, el.get("title")))
        inner = merge_adjacent_text(self._children_blocks(el))
        if not sc_has_text(inner):
            return []
        if (target or "").upper().startswith("ACTIV:") or "ACTIV" in cls or "cn_topic" in cls:
            text = sc_text(el.get_text("", strip=True))
            chip = "ld-actcn" if "cn_topic" in cls else "ld-act"
            return [sc("span", text, cls=chip)] if text else []
        resolved = self.terms.resolve(target)
        if resolved:
            self.stats["links_live"] += 1
            return [sc("a", inner, href=f"?query={quote(resolved, safe='')}&wildcards=off")]
        self.stats["links_dead"] += 1
        if "defRef" in cls or "crossRef" in cls or "Thesref" in cls:
            return [sc("span", inner, cls="ld-xref-dead")]
        return inner

    def render_def(self, el):
        cn_nodes = {id(c) for c in el.find_all(["span", "div"], class_="cn_txt")}
        has_cn = bool(cn_nodes)

        def text_outside(node):
            if not isinstance(node, NavigableString):
                return False
            if not sc_text(str(node)).strip():
                return False
            cur = node.parent
            while cur is not None and cur is not el:
                if id(cur) in cn_nodes:
                    return False
                cur = cur.parent
            return True

        cn_only = False
        cn_el = None
        if has_cn and not any(text_outside(d) for d in el.descendants):
            cn_only = True
            cn_el = el.find(["span", "div"], class_="cn_txt")
        if cn_only and self.mode == "mono":
            return []
        if cn_only:
            inner = merge_adjacent_text(self._children_blocks(cn_el))
        else:
            inner = merge_adjacent_text(self._children_blocks(el))
        if not sc_has_text(inner):
            return []
        return [sc("div", inner, cls="ld-defcn" if cn_only else "ld-def",
                   lang="zh" if cn_only else None)]

    # -- record ------------------------------------------------------------

    def render_record(self, key, content):
        self.current_key = key
        soup = BeautifulSoup(content, HTML_PARSER)
        root = (soup.find("div", class_="entry_content")
                or soup.find("span", class_="lm5ppbody")
                or soup)
        nodes = self._children_blocks(root)
        # Portable separation for EVERY inline run, not just the head: without
        # the stylesheet there are no margins to keep chips apart, so
        # '[uncountable]SHORT/NOT LONG' and 'Corpus examples语料库例句'
        # read as one token.
        nodes = separate_inline_runs(merge_adjacent_text(nodes))
        # ...and a visible gap for block nodes, which whitespace cannot separate
        # (see BLOCK_BOTTOM_MARGIN: values mirror the class rules exactly).
        nodes = _add_block_spacing(nodes)
        return nodes

# ---------------------------------------------------------------------------
# CSS (all hooks via data-sc-class; every emitted class gets a rule)
# ---------------------------------------------------------------------------


def generate_css():
    return """/* LDOCE5++ Yomitan styles - generated by ldoce2yomitan v""" + VERSION + """ */
.gloss-sc { white-space: pre-wrap; }
.gloss-sc--structured-content { white-space: normal; }

/* ==========================================================================
   THEME CONTRACT
   Yomitan switches themes on <html> itself (css/display.css):
       :root                   --background-color:#ffffff  --text-color:#000000
       :root[data-theme=dark]  --background-color:#1e1e1e  --text-color:#d4d4d4
   Two traps, both verified in a real browser (see TYPOGRAPHY.md):

   1. The theme is NOT driven by the operating system. Keying the dark palette
      off `prefers-color-scheme` made two of the four combinations unreadable:
          Yomitan dark  + OS light -> #202124 text on #1e1e1e  (1.02:1)
          Yomitan light + OS dark  -> #dadce0 text on #ffffff  (1.39:1)

   2. You cannot select on the theme from here. Yomitan wraps this whole file
      with addScopeToCss() (display.js: `[data-dictionary="..."] { ... }`), so a
      nested `:root[data-theme=dark] ...` becomes `& :root[data-theme=dark] ...`
      -- a DESCENDANT selector that can never match, silently killing every
      dark override. (Measured: the headword stayed #1c1e21 on #1e1e1e.)

   So the palette does not branch on the theme at all. It is DERIVED from the
   inherited Yomitan text colour, which already switches with the theme:
     - neutrals  = the text colour at reduced alpha (composites over any bg)
     - accents   = a mid-tone hue mixed 68% with the text colour, which darkens
                   it on a light theme and lightens it on a dark one
   Measured contrast (light/dark), nested exactly as Yomitan does it:
     head 21/11 | zh 6.4/6.5 | pos 7.0/6.0 | snum 6.3/6.4 | register 6.5/6.3
     field 6.9/6.2 | geo 7.5/5.7 | warn 7.3/5.6 | level 6.2/6.6 | link 6.5/6.3
   If color-mix() is unsupported the declaration is dropped and the element
   falls back to the inherited text colour -- degraded, never unreadable.
   ========================================================================== */
[data-sc-class="ld"] {
  /* ---------------------------------------------------------------------
     PORTABLE DEFAULTS (scheme A).
     These static values are what any host that cannot parse color-mix()
     (Anki WebView, older readers, non-Yomitan consumers) will use. Each is the
     hue mixed toward mid grey and measured >= 3.0 contrast on BOTH a #ffffff
     and a #1e1e1e background (converter/_fallback_derive.py). Without them the
     variables stay DEFINED-but-invalid and every consumer falls back to the
     inherited text colour, which is why cards looked unstyled.
     The theme-adaptive color-mix() versions are applied further down inside an
     @supports block; a false @supports test means those are never parsed, so
     these defaults survive intact.
     --------------------------------------------------------------------- */
  --ld-link:  #458cd3;
  --ld-pos:   #4885ca;
  --ld-frame: #2f9c6e;
  --ld-zh:    #9d76d9;
  --ld-reg:   #c1743e;
  --ld-field: #7f8a3a;
  --ld-geo:   #8f67d8;
  --ld-warn:  #d35748;
  --ld-level: #b0851b;
  /* neutrals: the de-emphasised text tiers. With color-mix() available they are
     derived from --text-color further down, so they track the theme. Without it
     there is NO way to dim relative to the theme, and a fixed grey cannot stand
     in: measured against the two host backgrounds it has to clear 3:1 on BOTH,
     which pins the effective colour into the narrow mid band ~#696969..#949494 --
     and inside that band a *ramp* is impossible, because the tier ordering is
     monotone in alpha, so the faintest tier is exactly the one that drops below
     3:1 (the old rgba(120,120,120,.62) measured 2.29 / 2.26). So the fallback
     inherits the host's own text colour instead: readable by construction,
     hierarchy flat, and the information -- all a no-CSS host needs -- survives.
     Same expression as --ld-head, deliberately. */
  --ld-text2: var(--text-color, currentColor);
  --ld-dim:   var(--text-color, currentColor);
  --ld-faint: var(--text-color, currentColor);
  /* Without Yomitan theme variables (e.g. Anki), the root must inherit
     the host text colour too; a fixed dark fallback hides dark-card text. */
  /* headword is plain theme text -- never a fixed colour */
  --ld-head:  var(--text-color, currentColor);
  /* metrics */
  --ld-chip-gap:.3em; --ld-chip-size:.8em; --ld-gutter:1.9em; --ld-gutter-sub:1.6em;
  display:block; line-height:1.5; font-size:1em; color:var(--text-color,inherit);
}

/* Theme-adaptive palette: only parsed by engines that actually support
   color-mix(). Verified on a real engine (Chrome 152 via CDP) that a static
   default outside @supports survives when the test is false; a browser that
   does not understand color-mix() reports CSS.supports(...) === false and the
   block below is skipped entirely. */
@supports (color: color-mix(in srgb, red 50%, blue 50%)) {
  [data-sc-class="ld"] {
    --ld-link:  color-mix(in srgb, #3b8ee0 68%, var(--text-color, currentColor) 32%);
    --ld-pos:   color-mix(in srgb, #3f86d6 68%, var(--text-color, currentColor) 32%);
    --ld-frame: color-mix(in srgb, #22a06b 68%, var(--text-color, currentColor) 32%);
    --ld-zh:    color-mix(in srgb, #a274e8 68%, var(--text-color, currentColor) 32%);
    --ld-reg:   color-mix(in srgb, #cc7233 68%, var(--text-color, currentColor) 32%);
    --ld-field: color-mix(in srgb, #7f8c2f 68%, var(--text-color, currentColor) 32%);
    --ld-geo:   color-mix(in srgb, #9163e6 68%, var(--text-color, currentColor) 32%);
    --ld-warn:  color-mix(in srgb, #e0503f 68%, var(--text-color, currentColor) 32%);
    --ld-level: color-mix(in srgb, #b8860b 68%, var(--text-color, currentColor) 32%);
    --ld-text2: color-mix(in srgb, var(--text-color, currentColor) 88%, transparent);
    --ld-dim:   color-mix(in srgb, var(--text-color, currentColor) 70%, transparent);
    --ld-faint: color-mix(in srgb, var(--text-color, currentColor) 55%, transparent);
  }
}

[data-sc-class="ld-entry"] { display:block; }
[data-sc-class="ld-entry"] + [data-sc-class="ld-entry"] { border-top:1px solid rgba(128,128,128,.3); margin-top:8px; padding-top:8px; }
/* Scheme B: the inline copy of a semantic marker (example dash, tick/cross,
   corpus bullet). Hidden as long as ANY stylesheet is applied, so the ::before
   rules above stay the single visible prefix and the rendering is unchanged.
   A host that loads no CSS at all -- an Anki export, a plain-HTML preview --
   sees this as an ordinary inline span, so the information survives. */
[data-sc-class="ld-mark"] { display:none; }
[data-sc-class="ld-empty"] { display:none; }

/* ---- headword ---------------------------------------------------------- */
[data-sc-class="ld-head"] { display:block; margin:2px 0 6px; }
[data-sc-class="ld-hwd-wrap"] { font-size:1.28em; font-weight:700; color:var(--ld-head); }
[data-sc-class="ld-hwd"] { font:inherit; color:inherit; }
[data-sc-class="ld-hyp"] { color:var(--ld-faint); padding:0 1px; }
/* Stress marks (ˈ ˌ) share the HYP element with syllable dots. They used to be
   emitted with class ld-hyp, so 19,676 of them rendered grey and got 1px of
   padding on each side -- splitting the mark from the syllable it belongs to.
   They are part of the headword, so they must inherit its colour, unpadded. */
[data-sc-class="ld-stress"] { color:inherit; }
[data-sc-class="ld-sup"] { font-size:.68em; vertical-align:super; color:var(--ld-reg); font-weight:700; }
[data-sc-class="ld-pron"], [data-sc-class="ld-pronblk"], [data-sc-class="ld-pron-amevar"] { font-size:.92em; color:var(--ld-text2); margin-left:.45em; }
[data-sc-class="ld-pronblk"] { display:inline; }
[data-sc-class="ld-pron-amevar"] { color:var(--ld-dim); }
[data-sc-class="ld-pos"] { font-size:.88em; font-style:italic; color:var(--ld-pos) !important; margin-left:.45em; font-weight:600; }
[data-sc-class="ld-level"] { color:var(--ld-level); margin-left:.5em; font-size:.85em; letter-spacing:1px; }
[data-sc-class="ld-sep"] { color:var(--ld-faint); margin:0 .35em; }
[data-sc-class="ld-infl"] { font-size:.85em; color:var(--ld-text2); }
[data-sc-class="ld-infl-form"] { white-space:nowrap; }
[data-sc-class="ld-infl-lab"] { font-style:italic; opacity:.75; }
[data-sc-class="ld-infl-region"] { font-style:italic; color:var(--ld-geo, var(--ld-dim)); }
[data-sc-class="ld-infl-ann"] { color:var(--ld-dim); }
[data-sc-class="ld-infl-pron"] { color:var(--ld-text2); font-size:.92em; }

/* ---- chips -------------------------------------------------------------
   One shared frame; each chip only supplies its own colour. color-mix ties the
   tint and border to currentColor, so a chip adapts to both themes without a
   second set of background/border rules. */
[data-sc-class="ld-freq"], [data-sc-class="ld-gram"], [data-sc-class="ld-geo"],
[data-sc-class="ld-register"], [data-sc-class="ld-act"], [data-sc-class="ld-synmark"] {
  display:inline-block; font-size:var(--ld-chip-size); font-weight:600; line-height:1.35;
  text-indent:0;   /* text-indent is inherited: .ld-ex uses -1.6em for its hanging indent,
                      and an inline-block inherits it onto its own first line, which pulls
                      the chip's text out of its own box (see REVIEW T9). */
  border-radius:4px; padding:0 5px; margin:0 var(--ld-chip-gap) 0 0; vertical-align:baseline;
  border:1px solid rgba(128,128,128,.38); border:1px solid color-mix(in srgb, currentColor 38%, transparent); /* static fallback, scheme A */;
  background:rgba(128,128,128,.10); background:color-mix(in srgb, currentColor 10%, transparent); /* static fallback, scheme A */;
}
[data-sc-class="ld-freq"] { font-size:.72em; color:var(--ld-pos); font-variant-numeric:tabular-nums; }
[data-sc-class="ld-gram"] { color:var(--ld-pos) !important; }
[data-sc-class="ld-geo"] { color:var(--ld-geo); }
[data-sc-class="ld-register"] { color:var(--ld-reg); }
[data-sc-class="ld-act"] { color:var(--ld-frame); font-weight:700; text-transform:uppercase; letter-spacing:.3px; }
[data-sc-class="ld-synmark"] { font-size:.72em; color:var(--ld-reg); font-weight:700; }
[data-sc-class="ld-actcn"] { font-size:.8em; color:var(--ld-frame); margin-left:var(--ld-chip-gap); }
[data-sc-class="ld-field"], [data-sc-class="ld-fieldxx"] { display:inline-block; text-indent:0; font-size:.78em; font-weight:700; color:var(--ld-field) !important; letter-spacing:.4px; margin-right:var(--ld-chip-gap); }
[data-sc-class="ld-signpost"] { display:inline-block; text-indent:0; font-weight:700; color:var(--ld-text2); font-size:.94em; margin-right:var(--ld-chip-gap); }

/* ---- native list semantics (dual-mode) -----------------------------------
   The document uses <ol>/<li> for senses and <ul>/<li> for examples, so a host
   with NO stylesheet still gets real list structure (that is the whole point --
   see the reference package LDOCE5.zip).

   Note the UA marker is switched off with the legal SC style listStyleType
   (UA_MARKER_OFF) rather than by hiding anything of ours: an earlier version hid
   the sense-number chip and let the UA number the list, which renumbered 531
   entries whose source numbers are not a plain 1..n run (audit R2). With the
   marker off, every visible number is the source number, in both environments.

   Here we only reinstate the original design:
     * list-style:none removes the markers, padding-left:0 removes the UA indent
     * li is displayed as block so the previous div-based layout is reproduced
   Net effect: the rendered look with CSS is what it was before the switch to
   native lists. */
[data-sc-class="ld-senselist"], [data-sc-class="ld-exlist"],
[data-sc-class="ld-corpulist"] {
  list-style: none; padding-left: 0; margin: 0;
}
[data-sc-class="ld-senselist"] > li, [data-sc-class="ld-exlist"] > li,
[data-sc-class="ld-corpulist"] > li {
  display: block;
}
/* ---- senses ------------------------------------------------------------
   ld-sense-n is emitted TOGETHER with ld-sense when the sense actually carries
   a number, so the 1.9em gutter (into which ld-snum hangs) is reserved only
   when there is something to put in it -- 49% of senses have no number, and the
   empty gutter wasted ~5% of the popup width on every one of them.
   `~=` is required because that class value is then multi-token. */
[data-sc-class~="ld-sense"], [data-sc-class~="ld-sense-cross"], [data-sc-class~="ld-sense-merge"] { display:block; margin:0 0 7px; }
[data-sc-class~="ld-sense-n"] { padding-left:var(--ld-gutter); }
[data-sc-class="ld-subsense"] { display:block; margin:2px 0 3px; padding-left:1.6em; }
[data-sc-class="ld-runon"] { display:block; margin:2px 0 4px; padding-left:var(--ld-gutter); color:var(--ld-text2); }
[data-sc-class="ld-phrventry"] { display:block; border-left:3px solid rgba(47,156,110,.45); border-left:3px solid color-mix(in srgb, var(--ld-frame) 45%, transparent); /* static fallback, scheme A */; margin:6px 0; padding:2px 0 2px .7em; }
[data-sc-class="ld-snum"] { display:inline-block; text-indent:0; min-width:1.35em; margin-left:calc(-1 * var(--ld-gutter)); font-weight:700; color:var(--ld-frame); font-variant-numeric:tabular-nums; }
/* 5,742 subsenses DO carry a number. Their own indent (1.6em) is smaller than
   the sense gutter (1.9em), so an unscoped ld-snum would hang 0.3em past the
   subsense box and land on the parent definition text. Scope the hang. */
[data-sc-class="ld-subsense"] [data-sc-class="ld-snum"] { margin-left:calc(-1 * var(--ld-gutter-sub)); }

/* ---- definitions and translations -------------------------------------- */
[data-sc-class="ld-def"] { display:block; margin:1px 0 1px; font-size:1.02em; font-weight:500; }
[data-sc-class="ld-defcn"] { display:block; margin:1px 0 3px; font-weight:600; color:var(--ld-zh) !important; }
[data-sc-class="ld-zh"] { color:var(--ld-zh); }
[data-sc-class="ld-en"] { color:inherit; font-weight:600; }
[data-sc-class="ld-gloss"] { color:var(--ld-dim); font-size:.95em; }
[data-sc-class="ld-grouptitle"] { font-weight:700; color:var(--ld-frame) !important; }
/* Sense-group label inside a collocation/thesaurus box: "- Meaning 1: ...". It
   belongs to the box that follows it, so it sits at the top of the panel body. */
[data-sc-class="ld-panel-sub"] { display:block; margin:0 0 4px; padding-bottom:2px; border-bottom:1px solid rgba(128,128,128,.18); border-bottom:1px solid color-mix(in srgb, currentColor 18%, transparent); /* static fallback, scheme A */; }
[data-sc-class="ld-panel-sub"] [data-sc-class="ld-grouptitle"] { font-weight:700; }
/* LDOCE Online panel: sits at the same level as a normal entry, so give it a
   little separation from the preceding entry. */
[data-sc-class="ld-panel-online"] { display:block; margin:6px 0 6px; }
[data-sc-class="ld-panel-online"] > [data-sc-class="ld-panel-sum"]::before { border-left-color:var(--ld-dim); }

/* ---- examples ---------------------------------------------------------- */
[data-sc-class="ld-ex"], [data-sc-class="ld-ex-good"], [data-sc-class="ld-ex-bad"], [data-sc-class="ld-gramexa"], [data-sc-class="ld-colloexa"] { display:block; margin:1px 0 3px; padding-left:1.6em; text-indent:-1.6em; color:var(--ld-text2); font-size:.97em; }
[data-sc-class="ld-ex"]::before, [data-sc-class="ld-gramexa"]::before, [data-sc-class="ld-colloexa"]::before { content:"\\2013\\00a0 "; color:var(--ld-frame); font-weight:700; }
[data-sc-class="ld-ex-good"]::before { content:"\\2713\\00a0 "; color:var(--ld-frame); font-weight:700; }
[data-sc-class="ld-ex-bad"]::before { content:"\\2717\\00a0 "; color:var(--ld-warn); font-weight:700; }
[data-sc-class="ld-excn"] { display:block; padding-left:1.6em; text-indent:0; color:var(--ld-zh) !important; font-size:.95em; margin-bottom:2px; }
[data-sc-class="ld-propform"] { font-weight:700; color:var(--ld-pos); }
[data-sc-class="ld-hint"] { display:block; border-left:3px solid rgba(176,133,27,.60); border-left:3px solid color-mix(in srgb, var(--ld-level) 60%, transparent); /* static fallback, scheme A */; background:rgba(176,133,27,.08); background:color-mix(in srgb, var(--ld-level) 8%, transparent); /* static fallback, scheme A */; padding:3px 8px; margin:4px 0; }
[data-sc-class="ld-hint-inline"] { color:var(--ld-level); font-style:italic; }
[data-sc-class="ld-dontsay"] { display:block; border-left:3px solid rgba(211,87,72,.60); border-left:3px solid color-mix(in srgb, var(--ld-warn) 60%, transparent); /* static fallback, scheme A */; background:rgba(211,87,72,.07); background:color-mix(in srgb, var(--ld-warn) 7%, transparent); /* static fallback, scheme A */; padding:3px 8px; margin:4px 0; }
[data-sc-class="ld-warn"] { display:block; color:var(--ld-warn); }
[data-sc-class="ld-good-word"] { font-weight:700; color:var(--ld-frame); }
[data-sc-class="ld-bad-word"] { font-weight:700; color:var(--ld-warn); text-decoration:line-through; }
[data-sc-class="ld-collo-range"] { color:var(--ld-dim); font-style:italic; }

/* ---- cross references -------------------------------------------------- */
[data-sc-class="ld-xref"], [data-sc-class="ld-xref-dead"] { font-weight:600; }
[data-sc-class="ld-xref-dead"] { color:var(--ld-dim); text-decoration:underline dotted; }
[data-sc-class="ld-crossref"] { display:block; margin:2px 0 4px; color:var(--ld-text2); font-size:.96em; }
[data-sc-class="ld-syn"], [data-sc-class="ld-homophone"] { display:block; margin:2px 0; font-size:.96em; color:var(--ld-text2); }
[data-sc-class="ld-xrtype"] { font-style:italic; color:var(--ld-dim); font-size:.9em; margin-right:.25em; }
[data-sc-class="ld-refhwd"] { font-weight:700; color:var(--ld-head); }
[data-sc-class="ld-deriv"] { font-weight:700; }
[data-sc-class="ld-lexvar"] { font-style:italic; }
[data-sc-class="ld-equiv"] { font-weight:600; color:var(--ld-text2); }
[data-sc-class="ld-thesref"] { font-weight:700; color:var(--ld-frame); }
[data-sc-class="ld-relatedwd"] { font-weight:600; }
[data-sc-class="ld-abbr"] { font-weight:600; }
[data-sc-class="ld-num"] { display:inline-block; text-indent:0; min-width:1.2em; text-align:center; color:var(--ld-faint); }

/* ---- collocations / thesaurus / grammar -------------------------------- */
[data-sc-class="ld-collo"], [data-sc-class="ld-exp"] { font-weight:700; color:var(--ld-head); }
[data-sc-class="ld-colloin"] { font-weight:600 !important; }
[data-sc-class="ld-nodew"] { font-weight:600 !important; color:var(--ld-pos); }
[data-sc-class="ld-b"] { font-weight:700; }
[data-sc-class="ld-it"] { font-style:italic; }
[data-sc-class="ld-collocate"] { display:block; margin:3px 0; padding-left:.4em; }
[data-sc-class="ld-exponent"] { display:block; margin:4px 0; padding-left:.4em; }
[data-sc-class="ld-section"] { display:block; margin:4px 0 2px; }
[data-sc-class="ld-psub"], [data-sc-class="ld-phead"] { display:block; font-weight:800; color:var(--ld-frame); margin:4px 0 2px; }
[data-sc-class="ld-expl"] { display:block; margin:3px 0; }
[data-sc-class="ld-expr"] { font-weight:700; }
[data-sc-class="ld-spokensect"] { display:block; margin:6px 0; }
[data-sc-class="ld-obj"] { font-style:italic; }
[data-sc-class="ld-para"] { display:block; margin:2px 0; }
/* Reserved: no construct in LDOCE5++ emits these, but other LM5pp dictionaries
   (e.g. LDOCE6) may. Do not delete without checking a reskin target.
   ld-block, ld-frequency, ld-xref, ld-table, ld-td, ld-th, ld-panel-boxbody,
   ld-corpexa-encyc, ld-corpexa-online, ld-corpexa-phrases, ld-sense-merge,
   ld-actcn, ld-hint-inline */
[data-sc-class="ld-block"] { display:block; }
[data-sc-class="ld-frequency"] { display:block; padding:4px; }
[data-sc-class="ld-table"] { border-collapse:collapse; margin:4px 0; width:auto; }
[data-sc-class="ld-td"], [data-sc-class="ld-th"] { border:1px solid rgba(128,128,128,.45); border:1px solid color-mix(in srgb, var(--ld-dim) 45%, transparent); /* static fallback, scheme A */; padding:2px 6px; font-size:.95em; text-align:left; }
[data-sc-class="ld-th"] { background:rgba(47,156,110,.10); background:color-mix(in srgb, var(--ld-frame) 10%, transparent); /* static fallback, scheme A */; font-weight:700; }

/* ---- panels ------------------------------------------------------------ */
[data-sc-class="ld-panel"], [data-sc-class="ld-panel-corpus"], [data-sc-class="ld-panel-wf"], [data-sc-class="ld-panel-etym"], [data-sc-class="ld-panel-online"] { display:block; margin:5px 0 6px; }
[data-sc-class="ld-panel-sum"] { cursor:pointer; font-weight:700; color:var(--ld-head); list-style:none; padding:1px 0 1px 1.1em; position:relative; user-select:none; }
[data-sc-class="ld-panel-sum"]::-webkit-details-marker { display:none; }
[data-sc-class="ld-panel-sum"]::before { content:""; position:absolute; left:0; top:50%; border-top:.32em solid transparent; border-bottom:.32em solid transparent; border-left:.48em solid var(--ld-frame); transform:translateY(-50%); transition:transform .12s; }
[data-sc-class="ld-panel"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-corpus"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-wf"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-etym"][open] > [data-sc-class="ld-panel-sum"]::before, [data-sc-class="ld-panel-online"][open] > [data-sc-class="ld-panel-sum"]::before { transform:translateY(-50%) rotate(90deg); }
[data-sc-class="ld-panel-title"] { color:var(--ld-frame); }
[data-sc-class="ld-panel-title-zh"] { margin-left:.5em; font-size:.85em; color:var(--ld-zh); font-weight:600; }
[data-sc-class="ld-panel-body"] { border-left:3px solid rgba(47,156,110,.40); border-left:3px solid color-mix(in srgb, var(--ld-frame) 40%, transparent); /* static fallback, scheme A */; background:rgba(47,156,110,.06); background:color-mix(in srgb, var(--ld-frame) 6%, transparent); /* static fallback, scheme A */; border-radius:0 4px 4px 0; padding:4px 8px; margin-top:3px; }
[data-sc-class="ld-panel-boxbody"] { display:block; }
[data-sc-class="ld-panel-corpus"] > [data-sc-class="ld-panel-body"] { background:rgba(72,133,202,.06); background:color-mix(in srgb, var(--ld-pos) 6%, transparent); /* static fallback, scheme A */; border-left-color:rgba(72,133,202,.40); border-left-color:color-mix(in srgb, var(--ld-pos) 40%, transparent); /* static fallback, scheme A */; }
[data-sc-class="ld-panel-etym"] > [data-sc-class="ld-panel-sum"]::before { border-left-color:var(--ld-reg); }
[data-sc-class="ld-panel-wf"] > [data-sc-class="ld-panel-body"] { display:flex; flex-direction:column; gap:2px; }
[data-sc-class="ld-wf-group"] { display:block; }
[data-sc-class="ld-wf-pos"] { font-style:italic; font-weight:700; color:var(--ld-pos); margin-right:var(--ld-chip-gap); font-size:.9em; }
[data-sc-class="ld-wf-word"] { font-weight:600; }
[data-sc-class="ld-wf-root"] { color:var(--ld-dim); border-bottom:1px dotted rgba(128,128,128,.60); border-bottom:1px dotted color-mix(in srgb, currentColor 60%, transparent); /* static fallback, scheme A */; }
/* Antonym marker inside a word family: "!= disadvantage". The source wraps it in
   <span class="opp"> with a literal U+2260 plus a link. */
[data-sc-class="ld-wf-opp"] { color:var(--ld-dim); }
[data-sc-class="ld-wf-opp"] > a { color:inherit; font-weight:600; }

/* ---- corpus list ------------------------------------------------------- */
[data-sc-class="ld-exagroup"] { display:block; margin:3px 0; }
[data-sc-class="ld-exagroup-title"] { font-weight:700; color:var(--ld-frame) !important; margin-bottom:2px; }
[data-sc-class="ld-corpulist"] { list-style:none; margin:0 0 4px; padding:0; }
[data-sc-class="ld-corpexa"], [data-sc-class="ld-corpexa-corpus"], [data-sc-class="ld-corpexa-dics"], [data-sc-class="ld-corpexa-encyc"], [data-sc-class="ld-corpexa-online"], [data-sc-class="ld-corpexa-phrases"] { display:list-item; padding-left:1.2em; text-indent:-1.2em; margin:1px 0; font-size:.96em; color:var(--ld-text2); }
[data-sc-class="ld-corpexa"]::before, [data-sc-class="ld-corpexa-corpus"]::before, [data-sc-class="ld-corpexa-dics"]::before, [data-sc-class="ld-corpexa-encyc"]::before, [data-sc-class="ld-corpexa-online"]::before, [data-sc-class="ld-corpexa-phrases"]::before { content:"\\2022\\00a0 "; color:var(--ld-faint); }

/* ---- lists ------------------------------------------------------------- */
[data-sc-class="ld-list"] { margin:2px 0 4px 1.4em; padding:0; }

/* ---- etymology --------------------------------------------------------- */
[data-sc-class="ld-origin"] { font-style:italic; font-weight:600; }
[data-sc-class="ld-century"] { color:var(--ld-dim); font-size:.9em; }
[data-sc-class="ld-tran"] { font-style:italic; color:var(--ld-text2); }
[data-sc-class="ld-lang"] { font-style:italic; font-weight:600; color:var(--ld-pos); }

/* ---- links ------------------------------------------------------------- */
[data-sc-class="ld"] a { color:var(--ld-link); font-weight:600; text-decoration:none; }
[data-sc-class="ld"] a:hover { text-decoration:underline; }

/* ---- topics / misc ----------------------------------------------------- */
[data-sc-class="ld-topics"], [data-sc-class="ld-topics-body"] { display:block; margin:4px 0; }
"""


# ---------------------------------------------------------------------------
# Tag bank
# ---------------------------------------------------------------------------

TAG_NOTES_ZH = {
    "noun": "名词", "verb": "动词", "adj": "形容词", "adv": "副词", "pron": "代词",
    "prep": "介词", "conj": "连词", "excl": "感叹词", "det": "限定词", "num": "数词",
    "modal": "情态动词", "aux": "助动词", "linking-v": "连系动词", "phrasal-v": "短语动词",
    "prefix": "前缀", "suffix": "后缀", "combining-form": "组合形式", "abbr": "缩写",
    "symb": "符号", "idiom": "习语", "def-article": "定冠词", "indef-article": "不定冠词",
    "ordinal-num": "序数词", "inf-marker": "不定式标记", "short-form": "缩略形式",
    "redirect": "重定向条目", "non-lemma": "词形变化/别名",
    "S1": "口语最高频词", "S2": "口语高频词", "S3": "口语常用词",
    "W1": "书面最高频词", "W2": "书面高频词", "W3": "书面常用词",
}
TAG_NOTES_EN = {
    "noun": "Noun", "verb": "Verb", "adj": "Adjective", "adv": "Adverb",
    "pron": "Pronoun", "prep": "Preposition", "conj": "Conjunction",
    "excl": "Exclamation", "det": "Determiner", "num": "Number",
    "modal": "Modal Verb", "aux": "Auxiliary Verb", "linking-v": "Linking Verb",
    "phrasal-v": "Phrasal Verb", "prefix": "Prefix", "suffix": "Suffix",
    "combining-form": "Combining Form", "abbr": "Abbreviation", "symb": "Symbol",
    "idiom": "Idiom", "def-article": "Definite Article",
    "indef-article": "Indefinite Article", "ordinal-num": "Ordinal Number",
    "inf-marker": "Infinitive Marker", "short-form": "Short Form",
    "redirect": "Redirect entry", "non-lemma": "Non-lemma form",
    "S1": "Spoken frequency S1", "S2": "Spoken frequency S2", "S3": "Spoken frequency S3",
    "W1": "Written frequency W1", "W2": "Written frequency W2", "W3": "Written frequency W3",
}


def build_tag_bank(ui_zh):
    notes = TAG_NOTES_ZH if ui_zh else TAG_NOTES_EN
    tags = []
    seen = set()
    order = 1
    for name in POS_TAG_MAP.values():
        if name in seen:
            continue
        seen.add(name)
        tags.append([name, "partOfSpeech", order, notes.get(name, name), 0])
        order += 1
    order = 30
    for s in ("S1", "S2", "S3", "W1", "W2", "W3"):
        tags.append([s, "frequency", order, notes.get(s, s), 0])
        order += 1
    tags.append(["redirect", "search", -5, notes["redirect"], 0])
    tags.append(["non-lemma", "partOfSpeech", 100, notes["non-lemma"], 0])
    return tags


# ---------------------------------------------------------------------------
# Entry-level tag extraction (cheap regex scan, no full DOM)
# ---------------------------------------------------------------------------

# Attribute order is NOT fixed in the source: the real markup is
#   <span class="FREQ" title="Top 1000 spoken words">S1
# so requiring `">` immediately after the class value matched 0 of the 32195 FREQ
# spans -> S1-S3/W1-W3 never reached definitionTags and the six `frequency` tags
# declared in the tag bank were dead declarations (REVIEW.md D7).
#
# The POS span is matched as an OPENING TAG only; its body is read with a depth
# counter. Pairing it with a non-greedy `(.*?)</span>` stopped at the first INNER
# closing tag, so the real markup
#   <span class="lm5pp_POS"> <span class="landscape">adverb</span><span
#   class="portrait">adv</span></span><span class="lm5pp_POS"> <span
#   class="neutral span">, </span>preposition</span>
# captured ' <span class="landscape">adverb' for the first span and only ','
# for the second: 'above' lost its preposition, 'andante' its adverb, and 281
# entries shipped wrong definitionTags/rules (audit A3). It was never a parser
# problem -- audit7 proved bs4/lxml agree -- the regex was the defect.
POS_SCAN_RE = re.compile(
    r'<span[^>]*\bclass="[^"]*\blm5pp_POS\b[^"]*"[^>]*>', re.S)
FREQ_SCAN_RE = re.compile(r'<span[^>]*\bclass="[^"]*\bFREQ\b[^"]*"[^>]*>\s*([SW][123])(?![0-9])')
# The narrow-screen abbreviation the original JS swaps in. It must never reach
# the metadata, exactly as _pick_landscape()/_no_portrait_text() skip it on the
# display path.
PORTRAIT_SCAN_RE = re.compile(
    r'<span[^>]*\bclass="[^"]*\bportrait\b[^"]*"[^>]*>', re.S)
SPAN_TAG_RE = re.compile(r'<span\b[^>]*>|</span\s*>', re.S)


def _span_body(html, start, limit=1500):
    """Body of the <span> opened just before `start`, honouring nested spans.

    Returns (body, index just after its closing tag). A span left unclosed
    within `limit` characters is treated as malformed and cut at its first
    `</span>` -- the old non-greedy behaviour -- rather than swallowing the rest
    of the record.
    """
    depth = 1
    pos = start
    while True:
        m = SPAN_TAG_RE.search(html, pos)
        if m is None:
            break
        if m.group(0).startswith("</"):
            depth -= 1
            if depth == 0:
                return html[start:m.start()], m.end()
        else:
            depth += 1
        pos = m.end()
        if pos - start > limit:
            break
    close = html.find("</span", start)
    if close == -1:
        return html[start:], len(html)
    return html[start:close], close + len("</span")


def _drop_portrait_spans(html):
    """`html` minus every span.portrait subtree, nested spans respected."""
    out = []
    pos = 0
    for m in PORTRAIT_SCAN_RE.finditer(html):
        if m.start() < pos:
            continue                       # already inside a removed portrait
        out.append(html[pos:m.start()])
        _, pos = _span_body(html, m.end())
    out.append(html[pos:])
    return "".join(out)


def extract_tags(content):
    pos_tokens = []
    consumed = 0
    for m in POS_SCAN_RE.finditer(content):
        if m.start() < consumed:
            continue                       # nested occurrence inside a POS span
        body, end = _span_body(content, m.end())
        pos_tokens.append(_drop_portrait_spans(body))
        consumed = end
    freq_tokens = FREQ_SCAN_RE.findall(content)
    return pos_tokens, freq_tokens


def pos_tags_rules(pos_tokens, freq_tokens):
    tags = []
    rules = []
    for token in pos_tokens:
        text = re.sub(r"<[^>]+>", " ", token)
        text = strip_invisible(collapse_ws(text)).strip().lower()
        text = text.strip(" .;")
        for part in [text] + re.split(r"[,;]", text):
            part = part.strip(" .()")
            if not part:
                continue
            tag = POS_TAG_MAP.get(part)
            if tag and tag not in tags:
                tags.append(tag)
            rule = POS_RULE_MAP.get(part, "")
            if rule and rule not in rules:
                rules.append(rule)
    for f in dict.fromkeys(freq_tokens):
        if f not in tags:
            tags.append(f)
    # Nothing is truncated here -- on purpose.
    #
    # Three successive caps each silently dropped real metadata:
    #   * `if len(tags) >= 4: break` + `rules[:4]`  -> 53 entries lost their 5th+
    #     POS ('back' lost 'adj', 'cross' lost 'adv'+'prefix', 'after'/'arch'
    #     lost 'prefix'); those tokens also vanished from definitionTags, which
    #     is the same defect class as audit A2/A3 (parts-of-speech filtering of
    #     deinflection candidates).
    #   * a flat `tags[:6]` -> frequency codes were appended last and got cut
    #     (140 rows disagreed with term_meta_bank).
    #   * `TAG_LIMIT = 8`   -> still cut 'like' (7 POS + 4 freq = 11).
    #
    # definitionTags is a space-separated string with no declared maximum, so the
    # only correct behaviour is to emit everything. TAG_LIMIT now serves as an
    # observation threshold: validate_package() warns when a row exceeds it, so
    # genuine data drift stays visible without any silent loss. Re-derive it with
    # converter/_cap_choose.py if that warning ever fires.
    return " ".join(tags), " ".join(rules)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

SC_TAG_KEYS = {
    "br": {"tag", "data"},
    **{tag: {"tag", "content", "data", "lang"}
       for tag in ("ruby", "rt", "rp", "table", "thead", "tbody", "tfoot", "tr")},
    **{tag: {"tag", "content", "data", "colSpan", "rowSpan", "style", "lang"}
       for tag in ("td", "th")},
    **{tag: {"tag", "content", "data", "style", "title", "open", "lang"}
       for tag in ("span", "div", "ol", "ul", "li", "details", "summary")},
    "img": {"tag", "data", "path", "width", "height", "title", "alt",
            "description", "pixelated", "imageRendering", "appearance",
            "background", "collapsed", "collapsible", "verticalAlign",
            "border", "borderRadius", "sizeUnits"},
    "a": {"tag", "content", "href", "lang"},
}


def sc_shape_error(value, path="content"):
    if isinstance(value, str):
        return ""
    if isinstance(value, list):
        for i, item in enumerate(value):
            err = sc_shape_error(item, f"{path}[{i}]")
            if err:
                return err
        return ""
    if not isinstance(value, dict):
        return f"{path} must be string/array/object"
    tag = value.get("tag")
    if tag not in SC_TAG_KEYS:
        return f"{path}.tag unsupported: {tag!r}"
    extra = set(value) - SC_TAG_KEYS[tag]
    if extra:
        return f"{path}.{sorted(extra)[0]} not allowed on <{tag}>"
    data = value.get("data")
    if data is not None and (not isinstance(data, dict)
                             or any(not isinstance(v, str) for v in data.values())):
        return f"{path}.data must have string values"
    if tag == "a":
        href = value.get("href")
        if not isinstance(href, str) or not re.match(r"^(?:\?|https?:)", href):
            return f"{path}.href invalid"
    if "content" in value:
        return sc_shape_error(value["content"], f"{path}.content")
    return ""


def term_row_shape_error(row):
    if not isinstance(row, list) or len(row) != 8:
        return "row must have 8 fields"
    for i in (0, 1, 2, 3, 7):
        if not isinstance(row[i], str):
            return f"field {i} must be string"
    if not row[0].strip():
        return "empty expression"
    if isinstance(row[4], bool) or not isinstance(row[4], (int, float)):
        return "score must be number"
    if not isinstance(row[5], list) or not row[5]:
        return "glossary must be non-empty array"
    for j, item in enumerate(row[5]):
        if isinstance(item, list):
            if (len(item) != 2 or not isinstance(item[0], str)
                    or not isinstance(item[1], list)
                    or any(not isinstance(x, str) for x in item[1])):
                return f"glossary[{j}] invalid [term, rules] redirect"
            continue
        if not isinstance(item, dict):
            return f"glossary[{j}] must be object/array/string"
        if item.get("type") == "structured-content":
            if set(item) != {"type", "content"}:
                return f"glossary[{j}] invalid SC wrapper keys"
            err = sc_shape_error(item["content"], f"glossary[{j}].content")
            if err:
                return err
        elif item.get("type") == "text":
            if set(item) != {"type", "text"} or not isinstance(item["text"], str):
                return f"glossary[{j}] invalid text item"
        else:
            return f"glossary[{j}] unsupported glossary item"
    if isinstance(row[6], bool) or not isinstance(row[6], int):
        return "sequence must be int"
    return ""


def collect_sc_classes(value, found, compound=None):
    """Collect emitted class tokens, split by how they were emitted.

    `found`      -- tokens emitted as the entire class value (="X" or ~="X")
    `compound`   -- tokens emitted inside a multi-token value (only ~="X" matches)

    Yomitan sets data.class as a single attribute value, so a compound value can
    only be reached by an attribute-substring selector. Keeping the two sets
    apart is what makes the CSS check able to catch "ld-panel ld-panel-online".
    """
    if compound is None:
        compound = set()
    if isinstance(value, list):
        for item in value:
            collect_sc_classes(item, found, compound)
    elif isinstance(value, dict):
        cls = (value.get("data") or {}).get("class")
        if cls:
            parts = cls.split()
            if len(parts) > 1:
                compound.update(parts)
            else:
                found.update(parts)
        for key, item in value.items():
            if key != "data":
                collect_sc_classes(item, found, compound)


def iter_sc_links(value):
    if isinstance(value, list):
        for item in value:
            yield from iter_sc_links(item)
    elif isinstance(value, dict):
        if value.get("tag") == "a":
            yield value
        for key, item in value.items():
            if key != "data":
                yield from iter_sc_links(item)


# Style properties the Yomitan structured-content schema permits. Taken from
# definitions/structuredContentStyle in dictionary-term-bank-v3-schema.json, which
# sets additionalProperties:false -- any other key is silently DROPPED by the
# generator, so emitting one is always a bug.
SC_STYLE_ALLOWED = frozenset({
    "fontStyle", "fontWeight", "fontSize", "color", "background", "backgroundColor",
    "textDecorationLine", "textDecorationStyle", "textDecorationColor",
    "borderColor", "borderStyle", "borderRadius", "borderWidth", "clipPath",
    "verticalAlign", "textAlign", "textEmphasis", "textShadow",
    "margin", "marginTop", "marginLeft", "marginRight", "marginBottom",
    "padding", "paddingTop", "paddingLeft", "paddingRight", "paddingBottom",
    "wordBreak", "whiteSpace", "cursor", "listStyleType",
})


def collect_style_keys(node, bad, used):
    """Walk an SC subtree, recording style property names and any illegal ones."""
    if isinstance(node, list):
        for x in node:
            collect_style_keys(x, bad, used)
    elif isinstance(node, dict):
        st = node.get("style")
        if isinstance(st, dict):
            cls = (node.get("data") or {}).get("class")
            for k, v in st.items():
                used[k] += 1
                if k not in SC_STYLE_ALLOWED:
                    if len(bad) < 12:
                        bad.append((k, v, cls))
                elif v is None or (isinstance(v, str) and not v.strip()):
                    if len(bad) < 12:
                        bad.append((k + "=empty", v, cls))
        for k, v in node.items():
            if k != "style":
                collect_style_keys(v, bad, used)
    return bad, used


def validate_package(zip_path, term_index, revision, mode, full_rows=True,
                     known_exprs=None):
    """Structural validation of the finished package.

    Each bank is decompressed and parsed exactly once. The "target must be a
    real row" check needs the complete expression set up front, so when the
    caller knows it (build() does) it is passed in as `known_exprs`; a
    standalone call falls back to one extra read pass over the banks.
    """
    errors = []
    stats = Counter()
    used_classes = set()
    used_compound = set()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for required in ("index.json", "styles.css", "tag_bank_1.json"):
            if required not in names:
                errors.append(f"missing {required}")
        index = json.loads(zf.read("index.json").decode("utf-8"))
        if index.get("format") != 3:
            errors.append("index.format must be 3")
        if index.get("sequenced") is not True:
            errors.append("index.sequenced must be true")
        if index.get("sourceLanguage") != "en":
            errors.append("index.sourceLanguage must be en")
        expect_target = "zh" if mode == "bilingual" else "en"
        if index.get("targetLanguage") != expect_target:
            errors.append(f"index.targetLanguage must be {expect_target}")
        if str(index.get("revision")) != str(revision):
            errors.append("index.revision mismatch")
        banks = sorted(n for n in names if re.fullmatch(r"term_bank_\d+\.json", n))
        if not banks:
            errors.append("no term banks")
            return errors, stats
        stats["term_banks"] = len(banks)

        # ---- illegal structured-content style properties --------------------
        # additionalProperties:false means an unrecognised style key is silently
        # discarded. That already caused a real bug: the `display:none` meant to
        # suppress double numbering on the sense-number chip vanished, so with no
        # stylesheet BOTH the UA <ol> number and our own chip showed
        # ("1. 1 [countable]"). Nothing detected it, so assert it here. The
        # numbering mechanism has since been replaced (see UA_MARKER_OFF): the
        # legal listStyleType is used instead, and this gate keeps any future
        # illegal property from being dropped in silence.
        style_used = Counter()
        style_bad = []
        for bank in banks:
            for row in json.loads(zf.read(bank).decode("utf-8")):
                if isinstance(row, list) and len(row) > 5 and row[4] > 0:
                    collect_style_keys(row[5], style_bad, style_used)
        if style_bad:
            errors.append(
                f"illegal/empty structured-content style propert(ies): "
                + ", ".join(f"{k!r} on {c!r}" for k, _v, c in style_bad[:6]))
        stats["style_keys"] = len(style_used)
        stats["style_keys_used"] = ",".join(sorted(style_used))

        if known_exprs is None:
            all_terms = set()
            for bank in banks:
                raw = zf.read(bank)
                if mode == "mono" and CJK_RE.search(raw.decode("utf-8")):
                    errors.append(f"{bank}: mono build contains CJK text")
                for row in json.loads(raw.decode("utf-8")):
                    if isinstance(row, list) and row and isinstance(row[0], str):
                        all_terms.add(row[0])
        else:
            all_terms = known_exprs

        seqs = []
        for bank in banks:
            raw = zf.read(bank)
            text = raw.decode("utf-8")
            if known_exprs is not None and mode == "mono" and CJK_RE.search(text):
                errors.append(f"{bank}: mono build contains CJK text")
            rows = json.loads(text)
            stats["rows"] += len(rows)
            for row in rows:
                err = term_row_shape_error(row)
                if err:
                    errors.append(f"{bank} {row[0]!r}: {err}")
                    if len(errors) > 40:
                        return errors, stats
                    continue
                if isinstance(row[6], int) and not isinstance(row[6], bool):
                    seqs.append(row[6])
                # Observation only, never an error: nothing is truncated any more,
                # so a row above TAG_LIMIT just means the source grew richer than
                # when the threshold was derived. Collected into stats so the
                # caller can print it without failing an otherwise good build.
                if isinstance(row[2], str):
                    n_tags = len(row[2].split())
                    if n_tags > TAG_LIMIT:
                        stats["rows_over_tag_limit"] += 1
                        if stats["rows_over_tag_limit"] <= 5:
                            examples = stats.setdefault("tag_limit_examples", [])
                            if isinstance(examples, list):
                                examples.append(f"{row[0]!r}={n_tags}")
                for item in row[5]:
                    if isinstance(item, list):
                        stats["redirect_items"] += 1
                        if item[0] not in all_terms and not (
                                not full_rows and item[0] in term_index):
                            errors.append(
                                f"{bank} {row[0]!r}: dangling redirect -> {item[0]!r}")
                    elif isinstance(item, dict) and item.get("type") == "structured-content":
                        collect_sc_classes(item["content"], used_classes, used_compound)
                        for link in iter_sc_links(item["content"]):
                            href = link.get("href") or ""
                            if href.startswith("?query="):
                                stats["query_links"] += 1
                                target = unquote(href[len("?query="):].split("&")[0])
                                if target not in all_terms and not (
                                    not full_rows and target in term_index):
                                    stats["dangling_links"] += 1
                                    if stats["dangling_links"] <= 20:
                                        errors.append(
                                            f"{bank} {row[0]!r}: dangling query link -> {target!r}")
        # Sequence numbers must be unique and gapless from 0 (index.sequenced).
        # Comparing len(set) with max+1 alone was blind to duplicates that happen
        # to fill the range: a package with two rows at 0 and a row at 1 gave
        # {0,1}, len 2 == max+1, so validation passed (audit A6). Compare against
        # the row count instead.
        if seqs:
            unique = len(set(seqs))
            ok = (unique == len(seqs) and min(seqs) == 0
                  and max(seqs) == len(seqs) - 1)
            if not ok:
                errors.append(
                    f"sequence numbers must be unique and 0..{len(seqs) - 1}: "
                    f"{len(seqs)} rows, {unique} unique value(s), "
                    f"min={min(seqs)}, max={max(seqs)}")
            stats["sequence_ok"] = int(ok)
        meta_banks = sorted(n for n in names if re.fullmatch(r"term_meta_bank_\d+\.json", n))
        stats["term_meta_banks"] = len(meta_banks)
        for bank in meta_banks:
            rows = json.loads(zf.read(bank).decode("utf-8"))
            stats["freq_rows"] += len(rows)
            for row in rows:
                ok = (isinstance(row, list) and len(row) == 3
                      and isinstance(row[0], str) and row[1] == "freq"
                      and isinstance(row[2], dict)
                      and isinstance(row[2].get("value"), (int, float))
                      and isinstance(row[2].get("displayValue"), str))
                if not ok:
                    errors.append(f"{bank}: malformed freq row {row!r}")
                    if len(errors) > 40:
                        return errors, stats
                    continue
                if row[0] not in all_terms:
                    errors.append(f"{bank}: freq row for unknown term {row[0]!r}")
        css = zf.read("styles.css").decode("utf-8") if "styles.css" in names else ""
        defined_exact = set()
        for m in re.findall(r'\[data-sc-class="([^"]+)"\]', css):
            defined_exact.update(m.split())
        defined_substr = set()
        for m in re.findall(r'\[data-sc-class~="([^"]+)"\]', css):
            defined_substr.update(m.split())
        defined = defined_exact | defined_substr
        missing = used_classes - defined
        if missing:
            errors.append("CSS missing selectors for: " + ", ".join(sorted(missing)))
        # A compound class value is only reachable via an attribute-substring
        # selector. Exact-match rules look correct in the stylesheet yet can never
        # apply to those elements, so require ~= for every compound token.
        loose = used_compound - defined_substr
        if loose:
            errors.append(
                "CSS: compound class values need [data-sc-class~=\"...\"] selectors for: "
                + ", ".join(sorted(loose)))
    return errors, stats


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------


class BuildValidationError(RuntimeError):
    """Rendering or package validation failed; the ZIP was NOT published.

    Raised instead of printing a success line: before this existed a failing
    build still renamed its "*.part" over the real package, printed
    "[OK] Dictionary package" and exited 0, silently replacing the last good
    archive with an invalid one (audit A1).
    """

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(
            f"package validation failed ({len(self.errors)} error(s)); "
            "the existing package was left untouched")


def build(input_path, output_dir, mode="bilingual", revision=None, test_words=None,
          open_panels=False, keep_json=False, validate=True, show_progress=True,
          limit=None):
    start = time.time()
    os.makedirs(output_dir, exist_ok=True)
    revision = revision or date.today().strftime("%Y.%m.%d")
    source_revision = infer_source_revision(input_path)

    debug = bool(test_words)
    # A build restricted with --limit is a PARTIAL dictionary too: without the
    # marker it is written under the OFFICIAL file name and can silently replace a
    # complete package (measured: `--limit 1` over a 2-row output shrank it to one
    # row and still exited 0). The `_DEBUG` suffix also keeps audit2/audit3 from
    # ever picking a partial build up as the package under test.
    partial = debug or limit is not None
    test_set = None
    if debug:
        test_set = {w.strip().casefold() for w in re.split(r"[,;，、]", test_words) if w.strip()}
    if partial:
        print(f"[!] PARTIAL build ({'test-words' if debug else '--limit'}): the package "
              f"is named _DEBUG and is not a deliverable.")

    # Bank rows are numerous and short-lived, so a higher GC threshold avoids
    # constant generation-0 scanning. NOTE: gc.disable() is NOT safe here --
    # BeautifulSoup trees hold parent references (cycles), so they are only
    # reclaimed by the cyclic collector.
    gc_threshold = gc.get_threshold()
    gc.set_threshold(50000, 100, 100)

    ui_zh = mode == "bilingual"
    zip_name = (f"LDOCE5pp_Yomitan_{date.today().strftime('%Y.%m.%d')}"
                + ("" if ui_zh else "_EN") + ("_DEBUG" if partial else "") + ".zip")
    zip_path = os.path.join(output_dir, zip_name)
    zip_tmp = zip_path + ".part"

    print("[*] Pass A: collecting headword index ...")
    term_index = TermIndex()
    alias_rows = []
    seen_kinds = Counter()
    n_records = 0
    # No count_lines() pre-scan: Pass A visits every record anyway, so its tally
    # is exact and the 877 MB file is no longer read a third time.
    for key, content in tqdm(iter_records(input_path), total=None,
                             desc="index", disable=not show_progress):
        n_records += 1
        k = strip_invisible(key).strip()
        if not k:
            continue
        kind, target = classify_record(k, content)
        seen_kinds[kind] += 1
        if kind == "entry":
            term_index.add(k)
        elif kind == "redirect":
            alias_rows.append((k, target))
    print(f"[OK] Pass A: entries={seen_kinds['entry']} unique={len(term_index.exact)} "
          f"redirects={seen_kinds['redirect']} skipped={seen_kinds['skip']} "
          f"records={n_records}")

    # alias graph
    target_map = {}
    for word, target in alias_rows:
        if target and target != word:
            target_map.setdefault(word, []).append(target)

    def resolve_with(word, reachable, fold, normm):
        out = []
        seen = set()
        stack = list(target_map.get(word, []))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            hit = current
            if hit not in reachable:
                alt = fold.get(hit.casefold()) or normm.get(norm_target(hit))
                if alt:
                    hit = alt
            if hit in reachable:
                out.append(hit)
            elif current in target_map:
                stack.extend(target_map[current])
        return list(dict.fromkeys(out))

    # Provisional alias resolution against Pass-A entry keys: decides which
    # alias words will get rows, so query links only target real rows.
    # (Rendering drop-outs are ~0; the strict validator catches any mismatch.)
    prov_fold = {k.casefold(): k for k in term_index.exact}
    prov_norm = {norm_target(k): k for k in term_index.exact}
    planned_alias = set()
    if not debug:  # in debug builds rows only cover test words: keep links strict
        for word in target_map:
            if word in term_index.exact:
                continue
            if resolve_with(word, term_index.exact, prov_fold, prov_norm):
                planned_alias.add(word)
                term_index.add_alias_word(word)
    print(f"[*] Alias plan: rows planned={len(planned_alias)} "
          f"unresolvable={len(target_map) - len(planned_alias) if not debug else 0}")

    print("[*] Pass B: rendering structured content ...")
    renderer = LdoceRenderer(term_index, mode=mode, open_panels=open_panels)
    term_bank = []
    file_index = 1
    sequence = 0
    generated = []
    rendered_keys = set()
    key_rules = {}
    freq_meta = {}
    written_exprs = set()
    stats = Counter()
    render_failures = []
    empty_failures = []

    # Banks are streamed straight into the archive: previously each 65 MB bank
    # was written to a temp file and then read back by zf.write(), i.e. 475 MB
    # written and re-read for nothing. Written to "*.part" and renamed at the
    # end so a crashed build never leaves a half-valid zip under the real name.
    zf = zipfile.ZipFile(zip_tmp, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=COMPRESS_LEVEL)

    def reject_package(errors):
        # A rendering failure can leave flushed banks in an OPEN archive.
        # Close before removing; close() is also safe after schema validation.
        zf.close()
        try:
            os.remove(zip_tmp)
        except OSError:
            pass
        gc.set_threshold(*gc_threshold)
        print(f"[FAIL] Nothing published; any previous {zip_name} is untouched.")
        raise BuildValidationError(errors)

    def save_bank(rows, idx):
        name = f"term_bank_{idx}.json"
        data = sanitize_inplace(rows)
        payload = json.dumps(data, ensure_ascii=False,
                             indent=1 if debug else None,
                             separators=None if debug else (",", ":"))
        if keep_json:
            path = os.path.join(output_dir, name)
            with io.open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
            generated.append(path)
        zf.writestr(name, payload)

    def flush_if_full():
        nonlocal term_bank, file_index
        if len(term_bank) >= TERM_BANK_BATCH:
            save_bank(term_bank, file_index)
            print(f"    -> wrote term_bank_{file_index}.json ({len(term_bank)} rows)")
            term_bank = []
            file_index += 1

    processed = 0
    for key, content in tqdm(iter_records(input_path), total=n_records,
                             desc="render", disable=not show_progress):
        processed += 1
        k = strip_invisible(key).strip()
        if not k:
            continue
        kind, _target = classify_record(k, content)
        if kind != "entry":
            continue
        if debug and k.casefold() not in test_set:
            continue
        try:
            nodes = renderer.render_record(k, content)
        except Exception as exc:  # noqa: BLE001
            stats["render_errors"] += 1
            if stats["render_errors"] <= 8:
                render_failures.append(f"render error {k!r}: {exc!r}")
                print(f"[WARN] {render_failures[-1]}")
            continue
        if not nodes or not sc_has_text(nodes):
            stats["empty_records"] += 1
            if stats["empty_records"] <= 8:
                empty_failures.append(f"empty render {k!r}: no visible content")
                print(f"[WARN] {empty_failures[-1]}")
            continue
        pos_tokens, freq_tokens = extract_tags(content)
        tags, rules = pos_tags_rules(pos_tokens, freq_tokens)
        rendered_keys.add(k)
        # A2: several records can share one expression (269 in this corpus) --
        # 'bail out' has a noun-phrasal-v row and a phrasal-v row. The alias
        # rows inherit this map, so it has to be the union over EVERY row with
        # that key; assigning per record left only the last one's rules and made
        # 940 aliases under-report theirs (partsOfSpeechFilter then cut the
        # deinflected candidates: bailout's -> bailout found nothing). Union
        # keeps first-seen order so the banks stay byte-reproducible.
        key_rules[k] = " ".join(dict.fromkeys(
            (key_rules.get(k) or "").split() + rules.split()))
        if freq_tokens:
            freq_meta[k] = list(dict.fromkeys(freq_tokens))
        gloss = [{"type": "structured-content",
                  "content": sc("div", nodes, cls="ld")}]
        term_bank.append([k, "", tags, rules, ENTRY_SCORE, gloss, sequence, ""])
        written_exprs.add(k)
        sequence += 1
        flush_if_full()
        if limit and len(rendered_keys) >= limit:
            break

    # The schema only sees written rows, never a record skipped by the renderer.
    # Abort before aliases/sidecars, even with --skip-validation: that option is
    # not permission for best-effort rendering or publishing an incomplete ZIP.
    rendering_errors = []
    if stats["render_errors"]:
        rendering_errors.append(
            f"{stats['render_errors']} source record(s) failed rendering; "
            "refusing to publish an incomplete dictionary")
    if stats["empty_records"]:
        rendering_errors.append(
            f"{stats['empty_records']} source record(s) rendered empty content; "
            "refusing to publish an incomplete dictionary")
    if rendering_errors:
        for error in rendering_errors:
            print(f"[FAIL] {error}")
        reject_package(rendering_errors + render_failures + empty_failures)

    term_index.finalize_rendered(rendered_keys)

    # ---- redirect rows ------------------------------------------------------
    rendered_fold = {k.casefold(): k for k in rendered_keys}
    rendered_norm = {norm_target(k): k for k in rendered_keys}
    alias_rendered = 0
    dropped_alias = 0
    for word in sorted(target_map):
        if word in rendered_keys:
            continue
        targets = resolve_with(word, rendered_keys, rendered_fold, rendered_norm)
        if not targets:
            dropped_alias += 1
            continue
        rules = " ".join(dict.fromkeys(
            tok for t in targets for tok in (key_rules.get(t) or "").split()))
        content_gloss = [[t, ["redirect"]] for t in targets]
        term_bank.append([word, "", "non-lemma", rules, REDIRECT_SCORE,
                          content_gloss, sequence, ""])
        written_exprs.add(word)
        sequence += 1
        alias_rendered += 1
        flush_if_full()
    print(f"[*] Redirect rows: {alias_rendered} (dropped unresolvable: {dropped_alias})")
    if term_bank:
        save_bank(term_bank, file_index)
        print(f"    -> wrote term_bank_{file_index}.json ({len(term_bank)} rows)")

    # ---- term_meta_bank: real frequency metadata ----------------------------
    # Yomitan reads frequency from its own bank (the importer matches
    # /^term_meta_bank_(\d+)\.json$/). Without it the package carried no frequency
    # data at all: the S/W grades existed only as decorative chips, so results
    # could not be sorted by frequency.
    freq_rows = 0
    if freq_meta:
        meta_rows = []
        for word, codes in freq_meta.items():
            for code in codes:
                value = FREQ_VALUE.get(code)
                if value is not None:
                    meta_rows.append([word, "freq",
                                      {"value": value, "displayValue": code}])
        # NOTE: the zip is already open at this point (banks are streamed straight
        # into it), so the meta bank must go through zf.writestr() too -- writing a
        # plain file on disk would leave it out of the package entirely.
        # Also: do NOT name the loop variable `start` -- that shadows the build
        # start time and turns the elapsed-time report into a nonsense number.
        for offset in range(0, len(meta_rows), TERM_BANK_BATCH):
            idx = offset // TERM_BANK_BATCH + 1
            name = f"term_meta_bank_{idx}.json"
            chunk = meta_rows[offset:offset + TERM_BANK_BATCH]
            payload = json.dumps(chunk, ensure_ascii=False,
                                 indent=1 if debug else None,
                                 separators=None if debug else (",", ":"))
            if keep_json:                 # same policy as save_bank(): the zip is
                path = os.path.join(output_dir, name)   # the artefact, the loose
                with io.open(path, "w", encoding="utf-8") as handle:   # file is only
                    handle.write(payload)                              # for debugging
                generated.append(path)
            zf.writestr(name, payload)
            freq_rows += len(chunk)
            print(f"    -> wrote {name} ({len(chunk)} rows)")

    # ---- metadata ----------------------------------------------------------
    desc_bits = ["Longman Dictionary of Contemporary English 5++ V2.15",
                 f"converter v{VERSION}"]
    if ui_zh:
        desc_bits.insert(1, "朗文当代高级英语辞典 · 双语增强版")
    if source_revision:
        desc_bits.append(f"source {source_revision}")
    index_data = {
        "title": "LDOCE5++ (LM5pp)",
        "format": 3,
        "revision": revision,
        "sequenced": True,
        # AUTHOR / URL are ASCII on purpose: a mono package declares
        # targetLanguage "en" and must not carry CJK metadata.
        "author": AUTHOR,
        "url": PROJECT_URL,
        "description": "；".join(desc_bits) if ui_zh else "; ".join(desc_bits),
        "attribution": ("Longman Dictionary of Contemporary English (Pearson); "
                        "LM5pp HTML edition; data: " + SOURCE_FORUM_URL),
        "sourceLanguage": "en",
        "targetLanguage": "zh" if ui_zh else "en",
    }
    dumps = lambda obj: json.dumps(  # noqa: E731
        obj, ensure_ascii=False,
        indent=1 if debug else None,
        separators=None if debug else (",", ":"))

    for name, payload in (("index.json", dumps(index_data)),
                          ("tag_bank_1.json", dumps(build_tag_bank(ui_zh))),
                          ("styles.css", generate_css())):
        path = os.path.join(output_dir, name)
        with io.open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
        generated.append(path)
        zf.writestr(name, payload)

    zf.close()

    if renderer.unknown_classes:
        print("[*] Top unknown classes kept generically:")
        for name, cnt in renderer.unknown_classes.most_common(25):
            print(f"      {cnt:>9}  {name}")

    print("\n=== Stats ===")
    print(f"[*] Records scanned: {processed}")
    print(f"[*] Rendered entries: {len(rendered_keys)}")
    print(f"[*] Redirect rows: {alias_rendered} (alias keys: {len(target_map)})")
    print(f"[*] Frequency rows: {freq_rows}")
    print(f"[*] Empty after render: {stats['empty_records']}")
    print(f"[*] Render errors: {stats['render_errors']}")
    print(f"[*] Query links: live={renderer.stats['links_live']} "
          f"demoted={renderer.stats['links_dead']}")
    print(f"[*] Elapsed: {time.time() - start:.1f}s")

    # ---- publish gate -----------------------------------------------------
    # Validation reads the still-unpublished "*.part" archive; the rename only
    # happens when it passes. The rename used to come FIRST, so a failing build
    # replaced the good package and still reported success (audit A1).
    if validate:
        print("[*] Validating package ...")
        errors, vstats = validate_package(
            zip_tmp, term_index, revision, mode,
            full_rows=debug is False and limit is None,
            known_exprs=written_exprs)
        print(f"[*] Validator: rows={vstats['rows']} banks={vstats['term_banks']} "
              f"query_links={vstats['query_links']} dangling={vstats['dangling_links']} "
              f"redirect_items={vstats['redirect_items']} "
              f"seq_ok={vstats['sequence_ok']} "
              f"freq_rows={vstats['freq_rows']}")
        if vstats.get("rows_over_tag_limit"):
            print(f"[!] {vstats['rows_over_tag_limit']} row(s) carry more than "
                  f"TAG_LIMIT={TAG_LIMIT} definitionTags "
                  f"(e.g. {', '.join(vstats.get('tag_limit_examples') or [])}); "
                  f"nothing was truncated -- re-derive TAG_LIMIT with _cap_choose.py.")
        if errors:
            print(f"[FAIL] Validation failed with {len(errors)} error(s):")
            for err in errors[:60]:
                print("   - " + err)
            reject_package(errors)
        print("[OK] Validation passed.")
    else:
        print("[*] Validation skipped on request (--skip-validation).")

    os.replace(zip_tmp, zip_path)          # atomic: *.part -> real name
    print(f"[*] Compressed {zip_name}")

    if not keep_json:
        for path in list(generated):
            if os.path.basename(path).startswith(("term_bank_", "term_meta_bank_")):
                try:
                    os.remove(path)
                except OSError:
                    pass
    gc.set_threshold(*gc_threshold)
    print(f"[OK] Dictionary package: {zip_path}")
    return zip_path


def infer_source_revision(path):
    m = re.search(r"(20\d{6})(\d{4,6})?", os.path.basename(str(path)))
    return m.group(0) if m else ""


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="LDOCE5++ (LM5pp) -> Yomitan dictionary")
    parser.add_argument("-i", "--input", required=True, help="MDX file or extracted .mdx.txt")
    parser.add_argument("-o", "--output", default="./yomitan_ldoce", help="Output directory")
    parser.add_argument("-m", "--mode", choices=("bilingual", "mono"), default="bilingual")
    parser.add_argument("--revision", default=None)
    parser.add_argument("--test-words", default=None,
                        help="Debug build restricted to these comma-separated headwords")
    parser.add_argument("--open-panels", action="store_true")
    parser.add_argument("--keep-json", action="store_true")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Skip package checks; rendering failures still abort publication")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--limit", type=int, default=None,
                        help="Render at most N entries (smoke testing)")
    args = parser.parse_args(argv)
    input_path = prepare_input(args.input)
    try:
        build(
            input_path,
            args.output,
            mode=args.mode,
            revision=args.revision,
            test_words=args.test_words,
            open_panels=args.open_panels,
            keep_json=args.keep_json,
            validate=not args.skip_validation,
            show_progress=not args.no_progress,
            limit=args.limit,
        )
    except BuildValidationError as exc:
        # A1: a failing build must be visible to whoever ran it. Previously the
        # process still exited 0 and packaging scripts shipped the failure.
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
