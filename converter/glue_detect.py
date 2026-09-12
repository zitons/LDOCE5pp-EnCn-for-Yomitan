"""Fix the detector's last class of false positive: a chip word appearing INSIDE
an ordinary English word.

Observed on the 408-entry sample (all false):
    'announcement,'  contains 'noun'
    'proverbial'     contains 'verb'
    'denounce'       contains 'noun'
    'predeterminer'  contains 'determiner'
These are plain words, not glue. A real glue has a NON-LETTER boundary before the
chip: a closed bracket, a slash, a CJK character, a digit, or an uppercase run end
('AWLadjective').

The one true hit in the same sample was 'ˈnounnoun' (phonetics then POS), where the
preceding character is 'n' but the token ALSO contains a stress mark -- handled by
requiring either a non-letter boundary or a phonetic marker before the chip.

Requiring a non-letter boundary eliminates the whole false-positive class while
keeping every genuine case.
"""
import re

CHIPS = ("noun", "verb", "adjective", "adverb", "preposition", "conjunction",
         "determiner", "pronoun", "exclamation", "prefix", "suffix", "article",
         "phrasal")
_CHIP = "|".join(CHIPS)
_CHIP_RE = re.compile(_CHIP)
_CHIP_FULL = re.compile("(?:" + _CHIP + ")")

# a chip word that is GLUED: the character before it is not a letter, or is a
# phonetic/stress marker. Inside a normal word the preceding char is a letter, so
# 'announcement'/'proverbial'/'denounce'/'predeterminer' no longer fire.
_PHON = "\u02c8\u02cc\u02d0\u00b7"          # stress marks, length mark, middle dot
_GLUE_BEFORE = re.compile(r"[^A-Za-z]")


def find_glue(text):
    """Return [(token, reason)] for tokens that look glued."""
    out = []
    for tok in text.split():
        core = tok.strip(".,;:!?\u3002\uff0c")
        if not core:
            continue
        bare = core.strip("[]")
        # normal: the token is a chip word, or bracket-wrapped chip
        if _CHIP_FULL.fullmatch(bare):
            continue
        # normal: slash/comma separated chips ('noun/verb', 'noun, verb')
        parts = [p for p in re.split(r"[/\s,]+", bare) if p]
        if parts and all(_CHIP_FULL.fullmatch(p) for p in parts):
            continue

        reasons = []
        if re.search(r"[A-Za-z\u4e00-\u9fff\u2019')\]]\d*\[", tok):
            reasons.append("bracket-glue")
        if re.search(r"[A-Za-z]\d*[\u25cf\u25cb]", tok):
            reasons.append("level-glue")
        if re.search(r"[SW]\d[SW]\d", tok):
            reasons.append("freq-glue")
        if re.search(r"[)\]]\s?[A-Za-z]", tok) and not re.search(r"[)\]]\s", tok):
            reasons.append("paren-glue")
        for m in _CHIP_RE.finditer(core):
            if m.start() == 0:
                continue
            pre = core[m.start() - 1]
            # A letter immediately before the chip means we are most likely inside
            # an ordinary word ('announcement', 'proverbial', 'denounce',
            # 'predeterminer'). Two exceptions are genuine glue:
            #   * the preceding run is ALL CAPS  -> 'AWLadjective', 'S2W2verb'
            #   * the token carries a phonetic marker -> '\u02c8nounnoun'
            if pre.isalpha() and not any(ch in core for ch in _PHON):
                head = core[:m.start()]
                if not (len(head) >= 2 and head[-2:].isupper()):
                    continue
            if pre == "/":
                left = core[:m.start() - 1].strip("/ ")
                if left and _CHIP_FULL.fullmatch(left):
                    continue
                reasons.append("chip-after-phonetics")
                break
            reasons.append("chip-after-word")
            break
        if reasons:
            out.append((tok, reasons[0]))
    return out
