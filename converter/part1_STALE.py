#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LDOCE5++ (LM5pp HTML) -> Yomitan structured-content dictionary converter.
# Pipeline shape mirrors shoujocyber/OALD10-Yomitan-Converter:
#   MDX -> extracted text -> per-record parser -> structured content IR
#       -> packager (index.json/tag_bank/term_bank/styles.css/ZIP)
#       -> structural validator.
# Part 1 of 2 (core + renderer). Assembled by build script.

import io
import json
import os
import re
import shutil
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

VERSION = "1.0.0"
AUTHOR = "海鸥 LDOCE5++ converter"
PROJECT_URL = "https://github.com/shoujocyber/OALD10-Yomitan-Converter"
SOURCE_FORUM_URL = "https://forum.freemdict.com/"
TERM_BANK_BATCH = 10000
REDIRECT_SCORE = -10
ENTRY_SCORE = 10

INVISIBLE_RE = re.compile("[\u00ad\u200b\u200c\u200d\u2060\ufeff\u2061\u2062\u2063\u2064]")
WS_RE = re.compile(r"\s+")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


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


def add_class(node, cls):
    data = node.setdefault("data", {})
    existing = data.get("class")
    data["class"] = f"{existing} {cls}".strip() if existing else cls
    return node


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
    out = []
    for node in nodes:
        if isinstance(node, str) and out and isinstance(out[-1], str):
            prev = out[-1]
            if prev.endswith(" ") or not node.startswith(" "):
                out[-1] = prev + node if prev.strip() else node
            else:
                out[-1] = prev + node
        else:
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
    "HYP":        ("ld-hyp", {}),
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
    "AMEVARPRON": "ld-amevar",
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
    ("GOODEXA", "ld-good"),
    ("BADEXA", "ld-bad"),
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


def classify_record(key, content):
    k = strip_invisible(key).strip()
    if not k:
        return "skip", None
    if SKIP_KEY_RE.match(k):
        return "skip", None
    head = content.lstrip()
    if head.startswith("@@@LINK="):
        target = head[len("@@@LINK="):].split("\n")[0].split("|")[0].strip()
        return "redirect", target
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
        self.rendered = set()

    def add(self, key):
        self.exact.add(key)
        self.by_fold.setdefault(key.casefold(), key)

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
        return None

    def __contains__(self, item):
        return item in self.exact


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

    def _children_blocks(self, el):
        nodes = []
        for child in el.children:
            if isinstance(child, NavigableString):
                if child.__class__.__name__ in ("Doctype", "Comment", "Declaration",
                                                "ProcessingInstruction", "CData"):
                    continue
                text = sc_text(str(child))
                if text:
                    nodes.append(text)
                continue
            if not isinstance(child, Tag):
                continue
            nodes.extend(self.render_element(child))
        return merge_adjacent_text(nodes)

    def render_element(self, el):
        cls = classes_of(el)
        if cls & DROP_CLASSES or el.name in DROP_TAGS:
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
            return [sc("div", inner, cls="ld-entry")] if inner else []
        if "dictionary" in cls or "dictentry" in cls:
            return self._children_blocks(el)
        if "Head" in cls and "frequent" in cls:
            return [self.render_head(el)]
        if "Inflections" in cls:
            return [self.render_inflections(el)]
        if "BoxPanel" in cls:
            inner = self._children_blocks(el)
            return [sc("div", inner, cls="ld-panel-boxbody")] if inner else []
        forced = cls & BLOCK_TOKENS
        if forced:
            return [self.render_block_by_token(el, self._first_forced(forced))]
        if "Head" in cls:
            return [self.render_head(el)]
        inner = self._children_blocks(el)
        if not inner:
            return []
        return [sc("div", inner)]

    def render_block_by_token(self, el, token):
        if token == "EXAMPLE":
            return self.render_example(el, classes_of(el))
        scname = BLOCK_SCNAME.get(token) or "ld-block"
        if token in ("SECHEADING", "HEADING", "boxheader", "spokensectheader"):
            text = sc_text(el.get_text(" ", strip=True))
            return sc("div", [text], cls=scname) if text else sc("div", [], cls="ld-empty")
        inner = self._children_blocks(el)
        if not inner:
            return sc("div", [], cls="ld-empty")
        cls = classes_of(el)
        node = sc("div", inner, cls=scname)
        if "cross_sense" in cls:
            node = sc("div", inner, cls="ld-sense-cross")
        elif "merge_sense" in cls:
            node = sc("div", inner, cls="ld-sense-merge")
        return node

    # -- semantic blocks ----------------------------------------------------

    def render_head(self, el):
        hwd_nodes = []
        pron_nodes = []
        pos_text = None
        chips = []
        infl_nodes = []

        def hwd_collect(node, out):
            for ch in getattr(node, "children", []):
                if isinstance(ch, NavigableString):
                    text = sc_text(str(ch))
                    if text:
                        out.append(text)
                elif isinstance(ch, Tag):
                    ccls = classes_of(ch)
                    if ccls & DROP_CLASSES:
                        continue
                    if "HYP" in ccls:
                        out.append(sc("span", "\u00b7", cls="ld-hyp"))
                    elif "HOMNUM" in ccls:
                        text = sc_text(ch.get_text("", strip=True))
                        if text:
                            out.append(sc("span", text, cls="ld-sup"))
                    else:
                        hwd_collect(ch, out)

        for child in el.children:
            if isinstance(child, NavigableString):
                text = sc_text(str(child))
                if text:
                    hwd_nodes.append(text)
                continue
            if not isinstance(child, Tag):
                continue
            cls = classes_of(child)
            if cls & DROP_CLASSES:
                continue
            if "HWD" in cls:
                parts = []
                hwd_collect(child, parts)
                hwd_nodes.append(sc("span", parts or [sc_text(child.get_text("", strip=True))],
                                    cls="ld-hwd"))
            elif "HOMNUM" in cls:
                text = sc_text(child.get_text("", strip=True))
                if text:
                    hwd_nodes.insert(0, sc("span", text, cls="ld-sup"))
            elif "PronCodes" in cls or "PRON" in cls or "AMEVARPRON" in cls:
                pron_text = sc_text(child.get_text("", strip=True))
                if pron_text:
                    extra = "amevar" if "AMEVARPRON" in cls else ""
                    pron_nodes.append(sc("span", pron_text, cls=("ld-pron-" + extra.strip())))
            elif "lm5pp_POS" in cls:
                label = self._pick_landscape(child)
                if label:
                    pos_text = sc_text(label)
            elif "LEVEL" in cls:
                stars = sc_text(child.get_text("", strip=True))
                title = strip_invisible(child.get("title") or "") or "Core vocabulary"
                if stars:
                    chips.append(sc("span", stars, cls="ld-level", title=title))
            elif "FREQ" in cls:
                text = sc_text(child.get_text("", strip=True))
                title = strip_invisible(child.get("title") or "") or None
                if text:
                    chips.append(sc("span", text, cls="ld-freq", title=title))
            elif "tooltip" in cls:
                pass
            elif "Inflections" in cls:
                node = self.render_inflections(child)
                infl_nodes = node.get("content") or []
            else:
                text = sc_text(child.get_text(" ", strip=True))
                if text:
                    hwd_nodes.append(text)
        head_children = []
        merged = []
        for part in hwd_nodes:
            if isinstance(part, dict):
                merged.append(part)
            else:
                if merged and isinstance(merged[-1], str) and not merged[-1].endswith(" "):
                    merged[-1] = merged[-1] + " "
                merged.append(part)
        if merged:
            head_children.append(sc("span", merged, cls="ld-hwd-wrap"))
        head_children.extend(pron_nodes)
        if pos_text:
            head_children.append(sc("span", pos_text, cls="ld-pos"))
        head_children.extend(chips)
        if infl_nodes:
            head_children.append(sc("span", " \u00b7 ", cls="ld-sep"))
            head_children.extend(infl_nodes)
        return sc("div", head_children, cls="ld-head")

    def _pick_landscape(self, el):
        land = el.find("span", class_="landscape")
        if land is not None:
            return land.get_text(" ", strip=True)
        return el.get_text(" ", strip=True)

    def render_inflections(self, el):
        items = []
        for child in el.find_all("span", recursive=True):
            cls = classes_of(child)
            if cls & {"PLURALFORM", "PASTTENSE", "PASTPART", "PRESPART", "T3PERSSING",
                      "PTandPP", "PTandPPX", "PRESPARTX", "T3PERSSINGX", "FULLFORM",
                      "COMP", "SUPERL"}:
                text = sc_text(child.get_text(" ", strip=True)).strip("() ")
                text = re.sub(r"\s+", " ", text)
                if text and text not in items:
                    items.append(text)
        if not items:
            text = sc_text(el.get_text(" ", strip=True)).strip()
            items = [text] if text else []
        children = []
        for idx, item in enumerate(items):
            if idx:
                children.append(" \u00b7 ")
            children.append(sc("span", item, cls="ld-infl-form"))
        return sc("span", children, cls="ld-infl")

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
                text = sc_text(str(child))
                if text:
                    en_nodes.append(text)
                continue
            if not isinstance(child, Tag) or is_in_cn(child):
                continue
            ccls = classes_of(child)
            if ccls & DROP_CLASSES:
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
        return sc("div", out, cls=flavor)

    def render_box(self, el, panel_token):
        for junk in el.find_all(["script", "style", "input", "label", "img"]):
            junk.decompose()
        heading = el.find("span", class_="heading") or el.find("span", class_="lm5ppBoxHead")
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
            cn_part = clone.find("span", class_="cn_txt")
            cn_text = None
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
        body = None
        while nxt is not None:
            if isinstance(nxt, Tag):
                if "assetlink" in classes_of(nxt):
                    body = nxt
                    break
                if nxt.get_text(strip=True):
                    break
            nxt = nxt.next_sibling
        if body is not None:
            body.extract()
            return self.render_assetlink(body, classes_of(body), header_type, header=el)
        return []

    def render_assetlink(self, el, cls, header_type=None, header=None):
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
        for group in el.find_all("span", class_="exaGroup", recursive=False):
            node = self.render_exa_group(group)
            if node:
                groups.append(node)
        if not groups:
            inner = self._children_blocks(el)
            if not sc_has_text(inner):
                return []
            groups = [sc("div", inner, cls="ld-exagroup")]
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
            items.append(sc("li", body, cls=cls))
        if items:
            nodes.append(sc("ul", items, cls="ld-corpulist"))
        if not nodes:
            return None
        return sc("div", nodes, cls="ld-exagroup")

    def render_wordfams(self, el):
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
            if cls & DROP_CLASSES or "asset_intro" in cls or "Head" in cls:
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
        if cls & DROP_CLASSES or el.name in DROP_TAGS:
            return []
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
        if not href or href.startswith("#") or re.match(
                r"^(sound|javascript|media|pic|rel:|/|https?:)", href, re.IGNORECASE):
            return self._children_blocks(el) if el.get_text(strip=True) else []
        target = entry_target_from_href(href, el.get("title"))
        inner = merge_adjacent_text(self._children_blocks(el))
        if not sc_has_text(inner):
            return []
        if (target or "").upper().startswith("ACTIV:") or "ACTIV" in cls or "cn_topic" in cls:
            return [sc("span", inner, cls="ld-act")]
        resolved = self.terms.resolve(target)
        if resolved:
            self.stats["links_live"] += 1
            return [sc("a", inner, href=f"?query={quote(resolved, safe='')}&wildcards=off")]
        self.stats["links_dead"] += 1
        if "defRef" in cls or "crossRef" in cls or "Thesref" in cls:
            return [sc("span", inner, cls="ld-xref-dead")]
        return inner

    def render_def(self, el):
        tag_children = [c for c in el.children if isinstance(c, Tag)]
        texts = [c for c in el.children
                 if isinstance(c, NavigableString) and sc_text(str(c))]
        cn_only = bool(tag_children) and not texts and all(
            "cn_txt" in classes_of(c) for c in tag_children)
        if cn_only and self.mode == "mono":
            return []
        inner = merge_adjacent_text(self._children_blocks(el))
        if not sc_has_text(inner):
            return []
        return [sc("div", inner, cls="ld-defcn" if cn_only else "ld-def",
                   lang="zh" if cn_only else None)]

    # -- record ------------------------------------------------------------

    def render_record(self, key, content):
        self.current_key = key
        soup = BeautifulSoup(content, "html.parser")
        for h1 in soup.find_all("h1"):
            h1.decompose()
        root = (soup.find("div", class_="entry_content")
                or soup.find("span", class_="lm5ppbody")
                or soup)
        nodes = self._children_blocks(root)
        return merge_adjacent_text(nodes)
