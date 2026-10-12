"""Convert LDOCE6_New (Longman 6th, English-English) to Yomitan.

A SEPARATE converter from ldoce2yomitan.py on purpose: the user asked that the
LDOCE5++ pipeline not be disturbed, and the two markups share nothing anyway.
It reuses the same format-3 output contract.

Verified structure (converter/_inventory.py, _l6_ease.py). A rich entry such as
'accusation' (46,487 chars) contains:

    span.entry
      span.entryhead                      the blue band
        span.hwd                          the headword
        span.hyphenation > span.hs0       syllable dots
        span.proncodes > span.pron        the pronunciation
        span.pos                          part of speech
        span.frequent / span.level        the frequency badge
        a.bre_snd / a.ame_snd             audio
        span.buttons
          span.popup-button
          div.at-link                     POPUP (collocations / thesaurus /
            span.entry                      phrases / word family)
              span.popheader.popcollo|popthes|popphrase|popwf|popexa
      span.sense                          one per sense
        span.sensenum                     the sense number
        span.def / span.defbold           the definition
        span.signpost                     the signpost band
        span.example > span.nodeword      example with highlighted words
        span.colloinexa                   collocation inside an example
        span.gramexa > span.propform      a grammar note
        span.geo / span.registerlab       regional / register labels
        span.tail                         the trailing cross-reference
      span.phrase > span.phrasetext       phrasal entries
      span.etymology                      etymology

212 distinct classes. This converter emits all of them; the stylesheet
(generate_css) ports LDOCE6_New.css's own visual language -- the entry-head band,
the signpost bands, the boxed collocation/thesaurus sections, the frequency
badges, and the per-type popup header colours.

English-English: no Chinese is emitted at all.
"""
import argparse
import io
import json
import os
import re
import sys
from collections import Counter

# --------------------------------------------------------------- Yomitan SC
SC_WHITELIST = {
    "textAlign", "fontWeight", "fontSize", "color", "backgroundColor",
    "margin", "marginTop", "marginBottom", "marginLeft", "marginRight",
    "padding", "paddingTop", "paddingBottom", "paddingLeft", "paddingRight",
    "textDecoration", "textDecorationLine", "listStyleType", "verticalAlign",
    "clipPath", "wordBreak", "whiteSpace", "cursor", "fontStyle", "textShadow",
    "borderTop", "borderBottom", "borderLeft", "borderRight", "borderRadius",
    "border", "borderColor", "borderWidth", "borderStyle", "fontVariant",
    "textTransform", "letterSpacing", "lineHeight", "display", "opacity",
}


def sc(tag, content, cls=None, **kw):
    d = {}
    if cls:
        d["class"] = cls
    if kw:
        # only genuine CSS properties belong in style; anything else is dropped
        d["style"] = {k: v for k, v in kw.items() if k in SC_WHITELIST}
    node = {"tag": tag}
    if d:
        node["data"] = d
    if content is not None:
        node["content"] = content
    return node


def span(content, cls=None, **kw):
    return sc("span", content, cls, **kw)


def div(content, cls=None, **kw):
    return sc("div", content, cls, **kw)


def details(content, cls=None, **kw):
    return sc("details", content, cls, **kw)


def summary(content, cls=None, **kw):
    return sc("summary", content, cls, **kw)


def strip_tags(s):
    s = re.sub(r"<script\b[^>]*>.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style\b[^>]*>.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# MDX-internal navigation entries, not dictionary headwords. Excluded from the
# package and from any coverage denominator:
#   faq- / guideword / word-set-*    navigation
#   boxes of *   the bundled source content for every entry's popups -- tens of
#                thousands of chars of OTHER entries' popups, not entries
INTERNAL_KEY = re.compile(r"^(faq-|guideword|word-set|boxes of )", re.I)


def generate_css():
    """Stylesheet modelled on the source dictionary's own LDOCE6_New.css.

    Ported from the original (verified by reading all 987 lines of it):
      .entryhead              background #edf4fa, border-top 4px solid #80a4be,
                              border-bottom 1px solid #ababac, padding 4px 8px 2px
      .hwd / .hyphenation     colour #20558E, bold      (the LDOCE6 blue)
      .pos                    italic, colour #27A058    (green)
      .freq                   border solid 1px, small-caps, 80%, bold, red,
                              border-radius 5px, padding 0 3px
      .level                  red, 120%, letter-spacing -2px
      .geo / .registerlab     italic, colour #917F5C    (brown)
      .signpost               background #647FB8, white, bold, uppercase,
                              border-radius 5px, padding 1px 5px
      .spokensect             background #edf4fa, border top+bottom #ababac,
                              padding 3px, margin 1ex 0
      .spokensecthead         bold, colour #85a8c4
      .colloc / .exp          bold, colour #917F5C
      .colloinexa             italic, bold
      .collobox/.thesbox/...  background #EDF4FA, padding 5px, colour #32648B,
                              border top+bottom thin, margin 8px 0
      .secheading/.subheading background rgba(69,119,191,.2), colour #396789,
                              small-caps, uppercase, padding 2px 5px
      .popheader              background #6891b1, white, bold
      .popheader.popcollo     #6891b1   .popphrase  purple
      .popheader.popthes      #6891b1   .popetym     green
      .popheader.popwf        #ffd448   .popexa      #6891b1
      .example                italic, line-height 130%, margin 3px 0
      ul.exas li              italic, colour #398597
      .nodeword               colour #2a4d66, bold
      .sensenum_abc           bold, colour #917F5C
      span.sense:before       border-top 1px solid #ababac
      .ws-head                bold, colour #20558E, larger
      .w / .wfwd              bold
      .realref:before         content "Main Entry:"  small-caps
      .sms:after              content "-> "
      .realmainentry          uppercase
      .arrow                  colour #917F5C, 90%
      .warning                bold, red
      .badexa                 line-through, italic

    The palette is NOT hardcoded: every accent is the original hue mixed with the
    inherited --text-color via color-mix, so it darkens on a light theme and
    lightens on a dark one. (Yomitan wraps this file with addScopeToCss() into
    [data-dictionary="..."]{...}, so a nested theme selector can never match --
    branching on the theme is not possible here.)
    """
    return """/* LDOCE6 (English-English) -> Yomitan, generated by ldoce6en2yomitan
   modelled on the source dictionary's own LDOCE6_New.css */
/* the root the converter actually emits; ld-entry carries the palette below */
[data-sc-class="ld-entry"] { display:block; line-height:1.4; font-size:1em;
  color:var(--text-color,inherit); margin:0 0 12px; }

/* palette: LDOCE6's hues.
   These MUST be declared on ld-entry, the element the converter actually emits as
   the root -- declaring them on a [data-sc-class="ld"] wrapper that is never
   produced left every var() undefined and the whole entry rendered as flat white
   text. Custom properties inherit, so the root covers every descendant.

   THEME HANDLING: surfaces (bands, boxes, pills) are mixed with
   --background-color, which Hoshi's popup.css defines per theme (#fff light /
   #000 dark). The mix ratio is deliberately LOPsided toward the background so a
   band comes out PALE on a light theme and DARK on a dark one -- a 50/50 mix
   lands on a mid tone in both, which is unreadable against either text colour.
   Text accents are mixed the other way, toward --text-color, so they darken on
   light themes and lighten on dark ones. */
[data-sc-class="ld-entry"] {
  --ld-blue:   color-mix(in srgb, #20558E 55%, var(--text-color, currentColor) 45%);
  --ld-green:  color-mix(in srgb, #27A058 55%, var(--text-color, currentColor) 45%);
  --ld-brown:  color-mix(in srgb, #917F5C 55%, var(--text-color, currentColor) 45%);
  --ld-teal:   color-mix(in srgb, #398597 55%, var(--text-color, currentColor) 45%);
  --ld-text2:  color-mix(in srgb, var(--text-color, currentColor) 86%, transparent);
  --ld-dim:    color-mix(in srgb, var(--text-color, currentColor) 72%, transparent);
  --ld-rule:   color-mix(in srgb, #ababac 70%, var(--text-color, currentColor) 30%);
  --ld-band:   color-mix(in srgb, #edf4fa 22%, var(--background-color, currentColor) 78%);
  --ld-bandbd: color-mix(in srgb, #80a4be 78%, var(--text-color, currentColor) 22%);
  --ld-boxbg:  color-mix(in srgb, #EDF4FA 22%, var(--background-color, currentColor) 78%);
  --ld-boxtx:  color-mix(in srgb, #32648B 45%, var(--text-color, currentColor) 55%);
  --ld-sectbg: color-mix(in srgb, #396789 20%, var(--background-color, currentColor) 80%);
  --ld-secttx: color-mix(in srgb, #396789 45%, var(--text-color, currentColor) 55%);
  --ld-signbg: color-mix(in srgb, #647FB8 70%, var(--background-color, currentColor) 30%);
  --ld-signhd: color-mix(in srgb, #85a8c4 55%, var(--text-color, currentColor) 45%);
  --ld-pop:    color-mix(in srgb, #6891b1 70%, var(--background-color, currentColor) 30%);
  --ld-wf:     color-mix(in srgb, #ffd448 85%, var(--background-color, currentColor) 15%);
  --ld-node:   color-mix(in srgb, #2a4d66 55%, var(--text-color, currentColor) 45%);
  --ld-red:    color-mix(in srgb, #d0021b 55%, var(--text-color, currentColor) 45%);
  --ld-purple: color-mix(in srgb, #7d26cd 70%, var(--background-color, currentColor) 30%);
  --ld-onband: #ffffff;
}

/* ---- the entry-head band: the signature LDOCE6 look ---- */
[data-sc-class="ld-head"] { display:block; background:var(--ld-band);
  border-top:4px solid var(--ld-bandbd); border-bottom:1px solid var(--ld-rule);
  padding:4px 8px 2px; margin:0 0 10px; line-height:1.5; }
[data-sc-class="ld-hwd"] { font-weight:700; font-size:1.2em; color:var(--ld-blue); }
[data-sc-class="ld-hyph"] { color:var(--ld-dim); font-size:.85em; margin-left:.4em; }
[data-sc-class="ld-pron"] { color:var(--ld-text2); font-size:.92em; margin-left:.4em; }
[data-sc-class="ld-pos"] { font-style:italic; color:var(--ld-green);
  font-weight:normal; margin-left:.45em; }
[data-sc-class="ld-freq"] { display:inline-block; border:1px solid var(--ld-red);
  color:var(--ld-red); font-variant:small-caps; font-size:78%; font-weight:700;
  text-transform:uppercase; border-radius:5px; padding:0 3px; line-height:1.6;
  margin-left:.4em; }
[data-sc-class="ld-geo"], [data-sc-class="ld-reg"] { font-style:italic;
  color:var(--ld-brown); margin-left:.4em; font-weight:normal; }

[data-sc-class="ld-entry"] { margin:0 0 12px; }

/* ---- signpost band (the original's .spokensect / .signpost) ---- */
[data-sc-class="ld-signpost"] { display:block; background:var(--ld-band);
  border-top:1px solid var(--ld-rule); border-bottom:1px solid var(--ld-rule);
  padding:3px 6px; margin:1ex 0; }
[data-sc-class="ld-signpost-h"] { display:inline-block; background:var(--ld-signbg);
  color:var(--ld-onband); font-weight:700; text-transform:uppercase;
  border-radius:5px; padding:1px 5px; font-size:.85em; }
[data-sc-class="ld-signpost-hd"] { display:block; font-weight:700;
  color:var(--ld-signhd); margin-bottom:4px; }

/* ---- senses, with the original's rule above each ---- */
[data-sc-class="ld-sense"] { display:block; margin:0 0 5px; padding-left:1.9em;
  padding-top:5px; position:relative; }
[data-sc-class="ld-sense"]::before { content:""; display:block;
  border-top:1px solid var(--ld-rule); margin:0 0 3px -1.9em; }
[data-sc-class="ld-sense"]:first-child::before { border-top:none; }
[data-sc-class="ld-snum"] { position:absolute; left:0; top:5px; min-width:1.35em;
  font-weight:700; color:var(--ld-brown); }
[data-sc-class="ld-def"] { color:var(--ld-text, currentColor); }
[data-sc-class="ld-defbold"] { font-weight:700; }
[data-sc-class="ld-ex"] { display:block; font-style:italic; line-height:1.3;
  margin:3px 0; color:var(--ld-teal); }
[data-sc-class="ld-nodeword"] { font-weight:700; color:var(--ld-node); }
[data-sc-class="ld-colloinexa"] { font-style:italic; font-weight:700; }
[data-sc-class="ld-gram"] { color:var(--ld-brown); }
[data-sc-class="ld-gloss"] { color:var(--ld-text2); }

/* ---- boxed collocation / thesaurus / phrase sections ----
   Each is a <details> that starts COLLAPSED. The source dictionary hides these
   popups behind .expandable with display:none; expanding them all turned one
   entry into a wall of text ('make': 69 senses, 1,616 examples). Native
   <details>/<summary> restores the folding -- verified that Yomitan's SC
   generator passes both tags through and that omitting `open` leaves them shut. */
[data-sc-class="ld-box"] { display:block; margin:6px 0; }
[data-sc-class="ld-box-body"] { display:block; background:var(--ld-boxbg);
  color:var(--ld-boxtx); border-top:1px solid var(--ld-rule);
  border-bottom:1px solid var(--ld-rule); padding:5px 7px; }
/* the summary IS the header bar; drop the default disclosure triangle and show a
   chevron instead */
[data-sc-class="ld-box"] > summary { list-style:none; cursor:pointer; }
[data-sc-class="ld-box"] > summary::-webkit-details-marker { display:none; }
/* ONE class per element: Yomitan puts the whole class string into data-sc-class,
   so a combined value never matches [data-sc-class="ld-boxhead"]. */
[data-sc-class="ld-boxhead-collo"], [data-sc-class="ld-boxhead-exa"],
[data-sc-class="ld-boxhead-thes"], [data-sc-class="ld-boxhead-etym"],
[data-sc-class="ld-boxhead-wf"], [data-sc-class="ld-boxhead-phrase"] {
  display:block; font-weight:700; color:var(--ld-onband);
  background:var(--ld-pop); padding:2px 6px;
  font-variant:small-caps; text-transform:uppercase; font-size:.85em; }
[data-sc-class="ld-boxhead-collo"]::after, [data-sc-class="ld-boxhead-exa"]::after,
[data-sc-class="ld-boxhead-thes"]::after, [data-sc-class="ld-boxhead-etym"]::after,
[data-sc-class="ld-boxhead-wf"]::after, [data-sc-class="ld-boxhead-phrase"]::after {
  content:" ▸"; float:right; font-size:.8em; opacity:.85; }
[data-sc-class="ld-box"][open] > summary::after { content:" ▾"; }
[data-sc-class="ld-boxhead-wf"] { background:var(--ld-wf); color:#20303f; }
[data-sc-class="ld-boxhead-phrase"] { background:var(--ld-purple); }
[data-sc-class="ld-boxhead-etym"] { background:var(--ld-green); }
[data-sc-class="ld-sechead"] { display:block; font-weight:700;
  background:var(--ld-sectbg); color:var(--ld-secttx); font-variant:small-caps;
  text-transform:uppercase; padding:2px 5px; margin:6px 0 3px; font-size:.9em; }
[data-sc-class="ld-collo-h"] { font-weight:700; color:var(--ld-brown); }
[data-sc-class="ld-collo-ex"] { display:block; margin-left:.6em; color:var(--ld-text2); }
[data-sc-class="ld-wfwd"] { font-weight:700; color:var(--ld-blue); }

/* ---- phrases and grammar notes ---- */
[data-sc-class="ld-phrase"] { display:block; font-weight:700; color:var(--ld-brown);
  margin:6px 0 2px; }
[data-sc-class="ld-gramexa"] { display:block; font-weight:700; margin-top:6px; }

/* ---- trailing cross-reference / etymology ---- */
[data-sc-class="ld-tail"] { display:block; border-top:1px solid var(--ld-rule);
  margin-top:8px; padding-top:6px; }
[data-sc-class="ld-etym"] { display:block; font-size:.88em; color:var(--ld-text2);
  margin-top:4px; }
[data-sc-class="ld-refnote"] { font-variant:small-caps; color:var(--ld-brown); }
"""


class Parser:
    def __init__(self):
        self.unknown = Counter()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _balanced(html, open_start):
        """Inner HTML of the element whose '<' is at open_start.

        The tag name is read from the OPENING tag itself, then open/close of that
        same name are counted from just past it.
        """
        m = re.match(r"<(\w+)", html[open_start:])
        if not m:
            return None
        tag = m.group(1).lower()
        gt = html.find(">", open_start)
        if gt < 0:
            return None
        body_start = gt + 1
        depth = 1
        for tok in re.finditer(r"<(/?)(\w+)[^>]*?(/?)>", html[body_start:]):
            closing, name, selfclose = (tok.group(1), tok.group(2).lower(),
                                        tok.group(3))
            if name != tag or selfclose:
                continue
            if closing:
                depth -= 1
                if depth == 0:
                    return html[body_start:body_start + tok.start()]
            else:
                depth += 1
        return html[body_start:]

    def _cls_inner(self, html, cls):
        for m in re.finditer(r'<(\w+)[^>]*\bclass="([^"]*)"[^>]*>', html, re.I):
            if cls in m.group(2).split():
                return self._balanced(html, m.start())
        return None

    def _cls_text(self, html, cls):
        inner = self._cls_inner(html, cls)
        return strip_tags(inner) if inner else None

    def _all(self, html, cls):
        """Inner HTML of EVERY element whose class list contains `cls`."""
        out = []
        for m in re.finditer(r'<(\w+)[^>]*\bclass="([^"]*)"[^>]*>', html, re.I):
            if cls in m.group(2).split():
                out.append(self._balanced(html, m.start()))
        return out

    def _elems(self, html, cls):
        """(position, inner) of every element whose class list contains cls."""
        out = []
        for m in re.finditer(r'<(\w+)[^>]*\bclass="([^"]*)"[^>]*>', html, re.I):
            if cls in m.group(2).split():
                out.append((m.start(), self._balanced(html, m.start())))
        return out

    # -------------------------------------------------------------- entry
    def parse(self, key, html):
        # The record contains several span.entry elements: the real one, plus
        # popup content (span.category > div.content > span.entry for Word Family,
        # div.at-link > span.entry for collocations), plus cross-reference stubs.
        # Prefer one carrying an entryhead; otherwise keep the first candidate.
        cands = []
        for m in re.finditer(r'<(\w+)[^>]*\bclass="([^"]*)"[^>]*>', html, re.I):
            if "entry" not in m.group(2).split():
                continue
            cands.append(self._balanced(html, m.start()))
        outer = None
        for c in cands:
            if self._cls_inner(c, "entryhead") is not None:
                outer = c
                break
        if outer is None:
            # No entryhead anywhere. 'a bit' is THREE sibling span.entry elements
            # (4,071 + 3,007 + 1,890 chars) holding one sense each; taking only
            # the first lost 2 senses and 2 definitions. Concatenate them all --
            # the popup entries are stripped later by the at-link/buttons removal.
            outer = "".join(cands) if cands else None

        if outer is None:
            # No span.entry at all.
            if self._cls_inner(html, "gramexa") is not None:
                return self._parse_gramexa(key, html)
            return self._parse_colloexa(key, html)

        head = self._cls_inner(outer, "entryhead")
        if head is None:
            # No entryhead. ORDER MATTERS:
            #   * a lexunit sub-entry often CONTAINS a gramexa or a colloexa, so
            #     checking those first hijacked the entry ('5 percent...' became
            #     "percent of", 'a bit' became "a bit better/older/easier etc").
            #   * lexunit-with-senses is the strongest signal.
            lex = self._cls_inner(outer, "lexunit")
            if lex is not None and self._cls_inner(outer, "sense") is not None:
                # A sub-entry with no entryhead. The FIRST lexunit is NOT the
                # headword -- for 'a bit' it is the sub-sense phrase
                # 'a bit better/older/easier etc'. Use the record key, and emit
                # each sense's lexunit/def/example as its own sense. def and
                # example are SIBLINGS of lexunit inside the sense.
                out = [div([span(key.strip(), "ld-hwd")], "ld-head")]
                n = 0
                for s in self._all(outer, "sense"):
                    n += 1
                    kids = [span(str(n), "ld-snum")]
                    lu = self._cls_text(s, "lexunit")
                    if lu:
                        kids.append(span(lu, "ld-defbold"))
                    for d in (strip_tags(x) for x in self._all(s, "def")):
                        if d:
                            kids.append(span(d, "ld-def"))
                    for em in self._elems(s, "example"):
                        t = strip_tags(em[1])
                        if t:
                            kids.append(div(t, "ld-ex"))
                    if len(kids) > 1:
                        out.append(div(kids, "ld-sense"))
                if len(out) > 1:
                    return div(out, "ld-entry")
            if self._cls_inner(html, "colloexa") is not None:
                # pass the WHOLE record, not `outer`: the span.subsense blocks that
                # carry the remaining definitions are SIBLINGS of span.entry, not
                # children, so searching only inside outer lost them.
                r = self._parse_colloexa(key, html)
                if r is not None:
                    return r
            if lex is not None:
                # a bare lexunit with no sense wrapper
                out = [div([span(key.strip(), "ld-hwd")], "ld-head")]
                for d in (strip_tags(x) for x in self._all(outer, "def")):
                    if d:
                        out.append(span(d, "ld-def"))
                for em in self._elems(outer, "example"):
                    t = strip_tags(em[1])
                    if t:
                        out.append(div(t, "ld-ex"))
                if len(out) > 1:
                    return div(out, "ld-entry")
            if self._cls_inner(html, "gramexa") is not None:
                r = self._parse_gramexa(key, html)
                if r is not None:
                    return r
            wf = self._cls_inner(html, "wf")
            if wf is not None:
                return self._parse_wordfamily(key, wf)
            rr = (self._cls_inner(html, "realref")
                  or self._cls_inner(outer, "realref"))
            if rr is not None:
                t = strip_tags(rr)
                if t:
                    return div([div([span(key.strip(), "ld-hwd")], "ld-head"),
                                div("Main Entry: " + t, "ld-def")], "ld-entry")
            return None

        # ---- the entry-head band -------------------------------------
        hwd = (self._cls_text(head, "hwd")
               or self._cls_text(head, "phrvbhwd")
               or key.strip())
        headbits = [span(hwd, "ld-hwd")]
        hyph = self._cls_text(head, "hyphenation")
        if hyph:
            headbits.append(span(hyph, "ld-hyph"))
        pron = self._cls_text(head, "pron")
        if pron:
            headbits.append(span(pron, "ld-pron"))
        pos = self._cls_text(head, "pos")
        if pos:
            headbits.append(span(pos, "ld-pos"))
        for cls, out_cls in (("frequent", "ld-freq"), ("level", "ld-freq")):
            t = self._cls_text(head, cls)
            if t:
                headbits.append(span(t, out_cls))
                break
        out = [div(headbits, "ld-head")]

        # ---- the body, minus the popup blocks ------------------------
        # Two things must NOT be done here:
        #   * a non-greedy `.*?</div>` to strip popups -- the at-link div and the
        #     buttons span both contain nested divs/spans, so it stops at the first
        #     inner close tag and leaves the popup's tail in the body.
        #   * outer.replace(head, " ", 1) -- the source's entryhead <span> is not
        #     always correctly closed, so _balanced runs to the END of the entry
        #     (11,333 chars for 'abbreviate') and the replace deletes the whole
        #     entry, leaving 0 definitions. Slice at the entryhead's opening tag
        #     and the first real body element instead.
        body = outer
        hm = re.search(r'<(\w+)[^>]*\bclass="[^"]*\bentryhead\b[^"]*"[^>]*>',
                       outer, re.I)
        if hm is not None:
            tail = outer[hm.end():]
            cut = len(tail)
            for pat in (r'<span[^>]*\bclass="[^"]*\bsense\b',
                        r'<div[^>]*\bclass="[^"]*\bverbtable\b',
                        r'<span[^>]*\bclass="[^"]*\bdef\b',
                        r'<div\b'):
                mm = re.search(pat, tail, re.I)
                if mm and mm.start() < cut:
                    cut = mm.start()
            body = tail[cut:] if cut < len(tail) else ""
        # strip the popups with balanced matching
        for cls in ("at-link", "buttons"):
            while True:
                hit = None
                for m in re.finditer(
                        r'<(\w+)[^>]*\bclass="([^"]*)"[^>]*>', body, re.I):
                    if cls in m.group(2).split():
                        hit = m
                        break
                if hit is None:
                    break
                inner = self._balanced(body, hit.start())
                if inner is None:
                    body = body[:hit.start()] + " " + body[hit.end():]
                else:
                    end = hit.start() + len(inner) + len(hit.group(0))
                    body = body[:hit.start()] + " " + body[end:]

        # ---- the popups themselves become visible sections -----------
        # (in the source they are hidden behind .popup-button; in a flat Yomitan
        #  popup there is nothing to click, so render them inline as boxes)
        for pm in re.finditer(
                r'<div[^>]*class="[^"]*\bat-link\b[^"]*"[^>]*>', outer, re.I):
            pop = self._balanced(outer, pm.start())
            if pop is None:
                continue
            kind = "collo"
            ph = self._cls_inner(pop, "popheader")
            if ph is not None:
                pt = strip_tags(ph).casefold()
                if "thes" in pt:
                    kind = "thes"
                elif "phrase" in pt:
                    kind = "phrase"
                elif "word family" in pt:
                    kind = "wf"
                elif "etym" in pt:
                    kind = "etym"
                elif "example" in pt:
                    kind = "exa"
            self._popup(pop, out, kind)

        # ---- senses ---------------------------------------------------
        n = 0
        for sm in re.finditer(
                r'<(\w+)[^>]*\bclass="([^"]*)"[^>]*>', body, re.I):
            if "sense" not in sm.group(2).split():
                continue
            n += 1
            self._sense(self._balanced(body, sm.start()), out, n)

        # Some entries have NO span.sense wrapper at all -- their definitions sit
        # directly in the entry body (e.g. 'abbreviate', whose structure is a
        # verbtable with col1/col2/verb_form plus bare def elements). Emitting
        # nothing for them lost the whole entry.
        if n == 0:
            self._sense(body, out, 1)

        # ---- phrases outside senses ----------------------------------
        for pm in re.finditer(
                r'<(\w+)[^>]*\bclass="([^"]*)"[^>]*>', body, re.I):
            if "phrase" not in pm.group(2).split():
                continue
            t = self._cls_text(self._balanced(body, pm.start()), "phrasetext") \
                or strip_tags(self._balanced(body, pm.start()))
            if t:
                out.append(div(t, "ld-phrase"))

        # ---- etymology ----------------------------------------------
        et = self._cls_text(body, "etymology")
        if et:
            out.append(div(et, "ld-etym"))

        # ---- trailing cross-reference --------------------------------
        tail = self._cls_inner(body, "tail")
        if tail is not None:
            t = strip_tags(tail)
            if t:
                out.append(div(t, "ld-tail"))

        if not out:
            return None
        return div(out, "ld-entry")

    # ------------------------------------------------------------- pieces
    def _sense(self, s, out, n):
        parts = [span(str(n), "ld-snum")]
        # signpost band
        sp = self._cls_inner(s, "signpost")
        if sp is not None:
            t = strip_tags(sp)
            if t:
                parts.append(div(t, "ld-signpost-h"))
        # regional / register labels
        for cls, ocls in (("geo", "ld-geo"), ("registerlab", "ld-reg"),
                          ("gram", "ld-gram")):
            t = self._cls_text(s, cls)
            if t:
                parts.append(span(t, ocls))
        # A sense may hold several definitions, one per subsense
        # (e.g. '180' has 2 defs inside 2 subsenses). Taking only the first lost
        # every definition after it.
        ds = [L_t for L_t in (strip_tags(d) for d in self._all(s, "def")) if L_t]
        if not ds:
            d = (self._cls_text(s, "lexunit")
                 or self._cls_text(s, "Crossref")
                 or self._cls_text(s, "realmainentry"))
            if d:
                ds = [d]
        for i, d in enumerate(ds):
            parts.append(span(d, "ld-def"))
        db = self._cls_text(s, "defbold")
        if db:
            parts.append(span(db, "ld-defbold"))
        gl = self._cls_text(s, "gloss")
        if gl:
            parts.append(span(gl, "ld-gloss"))
        # examples, keeping the highlighted words
        for eg in self._all(s, "example"):
            self._example(eg, parts)
        # a grammar note
        for gm in self._all(s, "gramexa"):
            t = strip_tags(gm)
            if t:
                parts.append(div(t, "ld-gramexa"))
        if len(parts) > 1:
            out.append(div(parts, "ld-sense"))

    def _example(self, eg, parts):
        """Render an example, keeping span.nodeword highlighting."""
        nodes = []
        pos = 0
        for m in re.finditer(
                r'<(\w+)[^>]*\bclass="([^"]*)"[^>]*>', eg, re.I):
            if "nodeword" not in m.group(2).split():
                continue
            before = strip_tags(eg[pos:m.start()])
            if before:
                nodes.append(before)
            inner = self._balanced(eg, m.start())
            t = strip_tags(inner)
            if t:
                nodes.append(span(t, "ld-nodeword"))
            gt = eg.find(">", m.start())
            pos = gt + 1
            # skip to the end of this nodeword element
            close = eg.find("</", pos)
            while close != -1:
                nm = re.match(r"</(\w+)", eg[close:])
                if nm and nm.group(1).lower() == m.group(1).lower():
                    pos = eg.find(">", close) + 1
                    break
                close = eg.find("</", close + 1)
        rest = strip_tags(eg[pos:])
        if rest:
            nodes.append(rest)
        if not nodes:
            t = strip_tags(eg)
            if t:
                nodes.append(t)
        if nodes:
            parts.append(div(nodes, "ld-ex"))

    def _popup(self, pop, out, kind):
        """Render one hidden popup as a COLLAPSED <details> section.

        The source dictionary hides every collocation / thesaurus / phrase /
        word-family popup behind .expandable with `display:none` and a
        .popup-button. Rendering them expanded turned one entry into a wall of
        text -- 'make' carries 69 senses and 1,616 examples -- which is exactly
        the lookup friction the folding was there to prevent. Native
        <details>/<summary> restores it: verified that Yomitan's SC generator
        passes both tags through, and that omitting `open` leaves them collapsed.
        """
        # the popup may hold several entries of its own
        entries = self._all(pop, "entry") or [pop]
        header = None
        kids = []
        for e in entries:
            ph = self._cls_inner(e, "popheader")
            if ph is not None:
                t = strip_tags(ph)
                if t and header is None:
                    header = t
            # section headings
            for sh in self._all(e, "secheading") + self._all(e, "subheading"):
                t = strip_tags(sh)
                if t:
                    kids.append(div(t, "ld-sechead"))
            # collocations
            for cm in self._elems(e, "collocate"):
                inner = cm[1]
                h = self._cls_text(inner, "colloc")
                if h:
                    kids.append(div(h, "ld-collo-h"))
                for ex in self._all(inner, "content"):
                    t = strip_tags(ex)
                    if t:
                        kids.append(div(t, "ld-collo-ex"))
            # thesaurus entries
            for tm in self._elems(e, "thespropform") + self._elems(e, "exponent"):
                t = strip_tags(tm[1])
                if t:
                    kids.append(div(t, "ld-collo-h"))
            for dm in self._elems(e, "exp"):
                t = strip_tags(dm[1])
                if t:
                    kids.append(div(t, "ld-collo-ex"))
            # plain examples
            for ex in self._all(e, "example"):
                t = strip_tags(ex)
                if t:
                    kids.append(div(t, "ld-ex"))
            # phrases
            for pm in self._elems(e, "phrasetext"):
                t = strip_tags(pm[1])
                if t:
                    kids.append(div(t, "ld-phrase"))
            # word family
            for wm in self._elems(e, "w"):
                t = strip_tags(wm[1])
                if t:
                    kids.append(span(t, "ld-wfwd"))
        if not kids:
            return
        if header is None:
            header = {"collo": "Collocations", "thes": "Thesaurus",
                      "phrase": "Phrases", "wf": "Word family",
                      "etym": "Word origin", "exa": "Examples"}.get(
                          kind, "More")
        # ONE class on the summary: Yomitan puts the whole class string into
        # data-sc-class, so a combined value never matches the selector.
        out.append(details([summary(header, f"ld-boxhead-{kind}"),
                            div(kids, "ld-box-body")], "ld-box"))

    def _parse_gramexa(self, key, html):
        """A grammar-example entry: propform + optional example."""
        h = self._cls_text(html, "propform") or key.strip()
        out = [div([span(h, "ld-hwd")], "ld-head")]
        reg = self._cls_text(html, "registerlab")
        if reg:
            out.append(span(reg, "ld-reg"))
        for em in self._elems(html, "example"):
            t = strip_tags(em[1])
            if t:
                out.append(div(t, "ld-ex"))
        if len(out) < 2:
            out.append(span(h, "ld-def"))
        return div(out, "ld-entry")

    def _parse_wordfamily(self, key, wf):
        """A Word Family stub: <span class="wf"><span class="group">
        <span class="pos">noun</span> <span class="wfwd">word</span> · ..."""
        out = [div([span(key.strip(), "ld-hwd"),
                    span("word family", "ld-pos")], "ld-head")]
        kids = []
        for gm in self._elems(wf, "group"):
            g = gm[1]
            pos = self._cls_text(g, "pos")
            words = [strip_tags(self._balanced(g, m.start()))
                     for m in re.finditer(
                         r'<(\w+)[^>]*\bclass="([^"]*)"[^>]*>', g, re.I)
                     if "wfwd" in m.group(2).split()]
            words = [w for w in words if w]
            if pos and words:
                kids.append(div([span(pos + ": ", "ld-collo-h"),
                                 span(" · ".join(words), "ld-wfwd")],
                                "ld-collo-ex"))
        if not kids:
            return None
        # collapsed by default, like the source's Word Family popup
        out.append(details([summary("Word family", "ld-boxhead-wf"),
                            div(kids, "ld-box-body")], "ld-box"))
        return div(out, "ld-entry")

    def _parse_colloexa(self, key, html, wrap=True):
        """A bare entry: WORD + examples (or a bare lexunit sense)."""
        h = (self._cls_text(html, "collo")
             or self._cls_text(html, "lexunit")
             or self._cls_text(html, "propform")
             or self._cls_text(html, "phrvbhwd")
             or key.strip())
        out = [div([span(h, "ld-hwd")], "ld-head")]
        for cls, ocls in (("def", "ld-def"), ("gloss", "ld-gloss"),
                          ("Crossref", "ld-def"), ("realmainentry", "ld-def")):
            t = self._cls_text(html, cls)
            if t:
                out.append(span(t, ocls))
                break
        for em in self._elems(html, "example"):
            t = strip_tags(em[1])
            if t:
                out.append(div(t, "ld-ex"))
        # A colloexa is often followed by sibling span.subsense blocks holding the
        # remaining definitions ('a bit better/older/easier etc' has its 2nd sense
        # in a subsense). Without this those definitions were dropped.
        n = 0
        for sm in self._elems(html, "subsense"):
            n += 1
            kids = [span(str(n), "ld-snum")]
            num = self._cls_text(sm[1], "sensenum")
            if num:
                kids = [span(num, "ld-snum")]
            d = self._cls_text(sm[1], "def")
            if d:
                kids.append(span(d, "ld-def"))
            for em in self._elems(sm[1], "example"):
                t = strip_tags(em[1])
                if t:
                    kids.append(div(t, "ld-ex"))
            if len(kids) > 1:
                out.append(div(kids, "ld-sense"))
        # a bare headword with nothing else is still a queryable headword
        return div(out, "ld-entry")


def iter_records(path):
    from mdict_utils.reader import MDX
    m = MDX(path)
    for key, val in m.items():
        k = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
        b = val if isinstance(val, bytes) else str(val).encode()
        yield k, b.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", required=True)
    ap.add_argument("-o", required=True)
    ap.add_argument("--revision", default="2026.10.09")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    p = Parser()
    rows = []
    by_key = {}
    seq = 0
    n = 0
    skipped = 0
    redirects = 0
    dupes = 0
    for key, html in iter_records(args.i):
        n += 1
        if args.limit and n > args.limit:
            break
        if html.lstrip().startswith("@@@LINK="):
            tgt = html.lstrip()[len("@@@LINK="):].split("\n")[0].split("|")[0].strip()
            if tgt:
                rows.append([key.strip(), "", "", "", -10,
                             [[tgt, ["redirect"]]], seq, ""])
                seq += 1
                redirects += 1
            else:
                skipped += 1
            continue
        if INTERNAL_KEY.match(key.strip()):
            skipped += 1
            continue
        try:
            content = p.parse(key, html)
        except Exception:
            content = None
        if content is None:
            skipped += 1
            continue
        kk = key.strip()
        # MDX keys are NOT unique -- `a` appears twice: once with two capital-A
        # homonyms (grade A, blood group A) and once with the lowercase article.
        # Yomitan shows only ONE row per expression, so replacing kept just the
        # bigger record and silently dropped the other homonyms entirely.
        # MERGE the two instead: concatenate their sense/box children under one
        # entry wrapper.
        if kk in by_key:
            dupes += 1
            i = by_key[kk]
            old = rows[i][5][0]["content"]
            oldkids = old.get("content") or []
            newkids = content.get("content") or []

            def heads(kids):
                return [n for n in kids
                        if isinstance(n, dict)
                        and (n.get("data") or {}).get("class") == "ld-head"]

            def body_of(kids):
                return [n for n in kids
                        if not (isinstance(n, dict)
                                and (n.get("data") or {}).get("class") == "ld-head")]

            oh, nh = heads(oldkids), heads(newkids)

            # Keep every DISTINCT headword's head band, but only the richest one
            # per headword. Merging 'abhor' produced TWO ld-head bands -- one from
            # the Word Family stub record (hwd "abhor" + pos "word family") and
            # one from the real entry (hwd + hyph + pron + pos) -- so the entry
            # rendered its headword twice with "word family" as the part of
            # speech. Different headword text (the 'a' / 'A' homonyms) must both
            # survive, so dedupe on the headword text, not on the band.
            def hwd_text(h):
                for n in (h.get("content") or []):
                    if isinstance(n, dict) and \
                            (n.get("data") or {}).get("class") == "ld-hwd":
                        return str(n.get("content", ""))
                return ""

            def rank(h):
                # more children == more information (pron, hyph, pos, freq)
                return len(json.dumps(h, ensure_ascii=False))

            best = {}
            order = []
            for h in oh + nh:
                t = hwd_text(h)
                if t not in best:
                    best[t] = h
                    order.append(t)
                elif rank(h) > rank(best[t]):
                    best[t] = h
            oh = [best[t] for t in order]
            kids = oh + body_of(oldkids) + body_of(newkids)
            rows[i][5] = [{"type": "structured-content",
                           "content": {"tag": "div",
                                       "data": {"class": "ld-entry"},
                                       "content": kids}}]
            continue
        by_key[kk] = len(rows)
        rows.append([kk, "", "", "", 10,
                     [{"type": "structured-content", "content": content}],
                     seq, ""])
        seq += 1

    print(f"scanned {n:,} records, {len(rows):,} rows "
          f"({redirects:,} redirects, {dupes:,} duplicate keys resolved), "
          f"{skipped:,} skipped")

    os.makedirs(args.o, exist_ok=True)
    idx = {"title": "Longman Dictionary of Contemporary English 6th (En-En)",
           "format": 3, "revision": args.revision, "sequenced": True,
           "sourceLanguage": "en", "targetLanguage": "en"}
    css = generate_css()
    batch = 10000
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        name = f"term_bank_{i // batch + 1}.json"
        with io.open(os.path.join(args.o, name), "w", encoding="utf-8") as f:
            f.write(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")))
        print(f"   wrote {name} ({len(chunk):,} rows)")
    with io.open(os.path.join(args.o, "index.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(idx, ensure_ascii=False, indent=2))
    with io.open(os.path.join(args.o, "styles.css"), "w", encoding="utf-8") as f:
        f.write(css)
    with io.open(os.path.join(args.o, "tag_bank_1.json"), "w", encoding="utf-8") as f:
        f.write("[]")
    print(f"done: {len(rows):,} rows")


if __name__ == "__main__":
    main()
