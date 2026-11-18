"""Finite query spellings for explicit generic person/object slots in LDOCE6.

Names and arbitrary noun phrases are deliberately not enumerated. The original
pattern remains the canonical entry; these are direct lookup aliases only.
"""
import itertools
import re
from collections import Counter

POSSESSIVES = ('my', 'your', 'his', 'her', 'our', 'their')
SLOTS = {
    "somebody's": POSSESSIVES,
    "someone's": POSSESSIVES,
    "one's": POSSESSIVES,
    # LDOCE writes the subject's own possessive as 'your' (put your foot down);
    # running text has 'put her foot down'.
    'your': ('my', 'his', 'her', 'its', 'our', 'their'),
    'somebody': ('me', 'you', 'him', 'her', 'us', 'them'),
    'someone': ('me', 'you', 'him', 'her', 'us', 'them'),
    'something': ('it', 'this', 'that'),
    'yourself': ('myself', 'himself', 'herself', 'itself', 'ourselves', 'themselves', 'yourselves'),
    'oneself': ('myself', 'yourself', 'himself', 'herself', 'itself', 'ourselves', 'themselves', 'yourselves'),
}
PATTERN = re.compile(r"\b(?:somebody's|someone's|one's|somebody|someone|something|yourself|oneself|your)\b(?!['’])")
POSSESSIVE_SLOTS = frozenset({"somebody's", "someone's", "one's", 'your'})
# The object was moved behind the particle here: 'kick out somebody' is
# English, 'kick out them' is not. Only possessive slots are filled.
MOVED_OBJECT_RULES = frozenset({'source_separable_object_position'})


def pronoun_variants(form, possessive_only=False):
    if re.search(r'[/()↔]|\b(?:sb|sth|etc)\b', form):
        return set()
    slots = list(PATTERN.finditer(form))
    # A leading generic person can be a subject, requiring I/he/she rather
    # than me/him/her. Keep that slot intact rather than guess its grammar.
    slots = [m for m in slots if not (m.start() == 0 and m[0] in {'somebody', 'someone'})]
    # 'be someone', 'have something': a bare verb + object slot would turn
    # 'be him' and 'have it' into phrase entries.
    if len(form.split()) < 3:
        slots = [m for m in slots if m[0] not in {'somebody', 'someone', 'something'}]
    if not slots or len(slots) > 2:
        return set()
    pieces = []; end = 0
    for m in slots:
        pieces.append(form[end:m.start()]); end = m.end()
    pieces.append(form[end:])
    result = set()
    # Include each original slot so both partial and complete replacement work.
    choices = [(m[0], *SLOTS[m[0]]) if not possessive_only or m[0] in POSSESSIVE_SLOTS else (m[0],)
               for m in slots]
    for selected in itertools.product(*choices):
        value = ''.join(pieces[i] + word for i, word in enumerate(selected)) + pieces[-1]
        if value != form:
            result.add(value)
    return result


def apply_pronouns(canonical_keys, aliases, blocked=()):
    counts = Counter(); blocked = set(canonical_keys) | set(blocked)
    sources = [(p, {p}, False) for p in canonical_keys]
    sources += [(a, set(targets), any(MOVED_OBJECT_RULES & rules for rules in targets.values()))
                for a, targets in list(aliases.items())]
    for form, targets, moved in sources:
        for value in pronoun_variants(form, possessive_only=moved):
            if value in blocked:
                continue
            for target in targets:
                if 'finite_generic_pronoun' not in aliases[value][target]:
                    counts['finite_generic_pronoun'] += 1
                aliases[value][target].add('finite_generic_pronoun')
    return counts
