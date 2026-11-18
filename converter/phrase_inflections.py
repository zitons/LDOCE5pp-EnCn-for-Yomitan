"""Conservative, source-first inflection aliases for LDOCE6 phrase entries.

``inflection_variants`` returns {complete_query: {audit_rule, ...}}. The caller
must establish the phrase's lexical category: spelling alone cannot distinguish
the noun ``work permit`` from a verb phrase. No aliases are emitted by default.

verb: past/participle/ing/third are sets of FIRST-WORD forms, and syllables is
an optional integer. Explicit forms replace regular fallback for that category.
noun: plurals are complete phrase forms, last_plurals are final-word forms;
countable=True authorizes regular final-word plurals. Explicit forms do not
require countable=True. Empty source sets mean unavailable, not prohibited.
An optional head_index (zero-based whitespace token index) and head_plurals
let a caller select a source-validated interior noun, e.g. point of order.
The module never guesses that index; countable=True authorizes its fallback.

This module neither inflects arbitrary interior words nor expands placeholders.
It returns query aliases only; callers retain the original definition target.
"""

from __future__ import annotations

import re
from collections import defaultdict


_WORD = re.compile(r"[A-Za-z]+\Z")
_HYPHENATED = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*\Z")
# passer-by, runner-up, mother-in-law, bride-to-be pluralize an inner word.
_AGENT_PARTICLE = re.compile(
    r"(?:er|or)-(?:by|up|on|in|out|off|over)\Z|-(?:in|of|at|to)-[a-z]+\Z")
_VOWELS = frozenset("aeiou")
_GRAMMAR = {
    "be": {"past": {"was", "were"}, "participle": {"been"},
           "ing": {"being"}, "third": {"is"}},
    "have": {"past": {"had"}, "participle": {"had"},
             "ing": {"having"}, "third": {"has"}},
    "do": {"past": {"did"}, "participle": {"done"},
           "ing": {"doing"}, "third": {"does"}},
    "go": {"past": {"went"}, "participle": {"gone"},
           "ing": {"going"}, "third": {"goes"}},
}
# Prevent regular past forms when the source has not supplied an irregular.
# This is a deny-list, not a replacement English dictionary. Source forms win.
_IRREGULAR = frozenset("""
abide arise awake bear beat become befall beget begin behold bend bereave
beseech beset bet bid bind bite bleed blow break breed bring broadcast build
burn burst buy cast catch choose cling come cost creep cut deal dig dive draw
dream drink drive dwell eat fall feed feel fight find fit flee fling fly forbid
forecast foresee foretell forget forgive forsake freeze get gild give grind grow
hang hear hew hide hit hold hurt inlay input keep kneel knit know lay lead lean
leap learn leave lend let lie light lose make mean meet mislead mistake mow
offset outdo outgrow outrun overcome overdo overtake overthrow pay plead prove
put quit read rend rid ride ring rise run saw say see seek sell send set sew
shake shear shed shine shoe shoot show shrink shut sing sink sit slay sleep
slide sling slink slit smell sneak sow speak speed spell spend spill spin spit
split spoil spread spring stand steal stick sting stink stride strike string
strive swear sweat sweep swell swim swing take teach tear tell think thrive
throw thrust tread undergo understand undertake undo uphold upset wake wear
weave wed weep wet win wind withdraw withhold withstand wring write
""".split())
_IRREGULAR_NOUNS = {
    "child": "children", "man": "men", "woman": "women", "person": "people",
    "tooth": "teeth", "foot": "feet", "mouse": "mice", "goose": "geese",
    "ox": "oxen",
}
_UNSAFE_NOUNS = frozenset("""
fish sheep deer aircraft offspring species series means salmon trout moose
bison buffalo swine cactus focus fungus nucleus syllabus analysis basis crisis
diagnosis hypothesis oasis parenthesis thesis criterion phenomenon datum medium
index matrix appendix radius stimulus vertebra alumna alumnus formula larva
life wife knife leaf loaf wolf half calf shelf thief self scarf hoof dwarf
belief chief roof cliff proof staff penny die brother
""".split())
_PREPOSITIONS = frozenset("of in on at by for from to with without under over into upon".split())
_POSTPOSITIVE = frozenset("martial general elect apparent designate emeritus major minor".split())


def _forms(value):
    if isinstance(value, str):
        value = [value]
    return {s.strip() for s in value or () if isinstance(s, str) and s.strip()}


def _case_like(value, original):
    if original.isupper():
        return value.upper()
    if original.istitle():
        return value[:1].upper() + value[1:]
    return value


def _cvc(word):
    # 'qu' contributes a single consonant sound: quit -> quitting.
    stem = word.replace("qu", "q")
    return (len(stem) >= 3 and stem[-1] not in _VOWELS
            and stem[-1] not in "wxy" and stem[-2] in _VOWELS
            and stem[-3] not in _VOWELS)


_VERB_PREFIXES = ("re", "un", "out", "over", "under", "mis", "inter", "up",
                  "in", "off", "sub", "fore", "with", "for", "be")
# Compounds whose final one-syllable element doubles: hashtagged, keylogging.
_DOUBLING = frozenset("hashtag keylog liveblog".split())


def _prefixed_irregular(word):
    # reset, sublet, undercut, outbid: an irregular verb behind a prefix.
    return any(word.startswith(p) and word[len(p):] in _IRREGULAR
               for p in _VERB_PREFIXES)


def _regular_verb(word, category, syllables):
    if category == "third":
        if word.endswith("y") and len(word) > 1 and word[-2] not in _VOWELS:
            return word[:-1] + "ies"
        if word.endswith(("s", "x", "z", "ch", "sh")):
            return word + "es" if word != "quiz" else "quizzes"
        return word + "s"
    if category in ("past", "participle") and (
            word in _IRREGULAR or _prefixed_irregular(word)):
        return None
    if word.endswith("c"):
        # panic/panicked versus arc/arced: source evidence required.
        return None
    if category == "ing":
        if word.endswith("ie"):
            return word[:-2] + "ying"
        if (word.endswith("e") and not word.endswith(("ee", "oe", "ye"))
                and word not in {"singe", "swinge"}):
            return word[:-1] + "ing"
    else:
        if word.endswith("e"):
            return word + "d"
        if word.endswith("y") and len(word) > 1 and word[-2] not in _VOWELS:
            return word[:-1] + "ied"
    suffix = "ing" if category == "ing" else "ed"
    if _cvc(word):
        # A CVC ending with one vowel group is one syllable (hem -> hemmed).
        # Source syllable counts are per homograph and unreliable for this.
        if (len(re.findall(r"[aeiouy]+", word)) == 1 or word in _DOUBLING
                or _prefixed_irregular(word)):
            return word + word[-1] + suffix
        # LDOCE6 declares stress-final doubling (referred, committed) in the
        # entry head, and declared forms replace this fallback. An undeclared
        # multisyllable verb is therefore the plain kind: ordered, visited.
        return word + suffix
    return word + suffix


def _regular_plural(word):
    if word in _IRREGULAR_NOUNS:
        return _IRREGULAR_NOUNS[word]
    if word in _UNSAFE_NOUNS or word.endswith(("f", "fe", "o")):
        return None
    if word.endswith("y") and len(word) > 1 and word[-2] not in _VOWELS:
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "z", "ch", "sh")):
        if word.endswith("z") and not word.endswith("zz"):
            return None
        return word + "es"
    return word + "s"


def inflection_variants(form, *, verb=None, noun=None):
    """Generate auditable inflected full-query aliases; see module contract.

    No rule is inferred from the phrase text's apparent POS. Both arguments may
    be supplied when the caller has independently established both readings.
    """
    aliases = defaultdict(set)
    if not isinstance(form, str) or not form.strip():
        return {}
    form = form.strip()

    def add(value, rule):
        if value != form:
            aliases[value].add(rule)

    first_match = re.match(r"([A-Za-z]+)(?=\s|$)(.*)\Z", form, re.S)
    if verb is not None and first_match:
        first, remainder = first_match.groups()
        base = first.lower()
        declared = {c: _forms(verb.get(c)) for c in ("past", "participle", "ing", "third")}
        for category in ("past", "participle", "ing", "third"):
            explicit = declared[category]
            if explicit:
                values, rule = explicit, "source_verb_" + category
            elif base in _GRAMMAR:
                values, rule = _GRAMMAR[base][category], "grammar_verb_" + category
            elif category in ("past", "participle") and (declared["past"] or declared["participle"]):
                # A verb with one declared principal part is not regular;
                # never pair 'forgot' with an invented 'forgeted'.
                continue
            else:
                candidate = _regular_verb(base, category, verb.get("syllables"))
                doubled = base + base[-1]
                if category == "ing" and doubled + "ed" in declared["past"] | declared["participle"]:
                    candidate = doubled + "ing"
                values = {candidate} if candidate else set()
                rule = "regular_verb_" + category
            for value in values:
                if _WORD.fullmatch(value):
                    add(_case_like(value, first) + remainder, rule)

    if noun is not None:
        explicit = _forms(noun.get("plurals"))
        for value in explicit:
            # A whole-phrase source plural may change an interior word.
            if form.isupper():
                value = value.upper()
            elif form[:1].isupper() and value[:1].islower():
                value = value[:1].upper() + value[1:]
            add(value, "source_noun_plural")
        final_match = re.match(r"(.*?)([A-Za-z]+)\Z", form, re.S)
        last_forms = _forms(noun.get("last_plurals"))
        head_index = noun.get("head_index")
        if not explicit and head_index is not None:
            tokens = list(re.finditer(r"\S+", form))
            if (type(head_index) is int and 0 <= head_index < len(tokens)
                    and _WORD.fullmatch(tokens[head_index].group())):
                match = tokens[head_index]
                head = match.group()
                values = _forms(noun.get("head_plurals"))
                rule = "source_noun_head_plural"
                if not values and noun.get("countable") is True:
                    candidate = _regular_plural(head.lower())
                    values = {candidate} if candidate else set()
                    rule = "regular_noun_head_plural"
                for value in values:
                    if _WORD.fullmatch(value):
                        add(form[:match.start()] + _case_like(value, head)
                            + form[match.end():], rule)
        elif not explicit and final_match:
            prefix, last = final_match.groups()
            if last_forms:
                for value in last_forms:
                    if _WORD.fullmatch(value):
                        add(prefix + _case_like(value, last), "source_noun_last_plural")
            elif noun.get("countable") is True:
                words = form.lower().split()
                # Explicit forms above remain valid for these compounds.
                if (all(_HYPHENATED.fullmatch(w) for w in words)
                        and not _AGENT_PARTICLE.search(words[-1])
                        and not any(w in _PREPOSITIONS for w in words[:-1])
                        and not (len(words) > 1 and words[-1] in _POSTPOSITIVE)):
                    plural = _regular_plural(last.lower())
                    if plural:
                        add(prefix + _case_like(plural, last), "regular_noun_plural")
    return dict(aliases)
