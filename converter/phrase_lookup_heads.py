"""Bounded source lemma entrances; never enumerate words filling argument slots."""
import re
from collections import defaultdict

OBJECT = r"(?:somebody|something|someone|sb|sth)(?:/(?:somebody|something|someone|sb|sth))*"
PARTICLES = set('away back down in off on out over round through together up aside apart along around under'.split())


def usable(key):
    return len(key.split()) >= 2 and not re.search(
        r'[/()\u2194]|\b(?:somebody|something|someone|sb|sth|etc|oneself)\b', key, re.I)


def entrances(form):
    """Omit only a leading copula and/or a complete terminal object slot."""
    result = defaultdict(set)
    forms = {form}
    if form.startswith('be '):
        forms.add(form[3:])
        result[form[3:]].add('initial_be_lookup_head')
    for value in forms:
        shorter = re.sub(r'\s+' + OBJECT + r'$', '', value)
        if shorter != value:
            result[shorter].add('terminal_object_lookup_head')
    return result


def separable_head(raw):
    """Caller must supply an original phrvbhwd, not a guessed separable form."""
    m = re.fullmatch(r'(\w+)\s+' + OBJECT + r'\s*\u2194\s*(\w+)', raw)
    return m[1]+' '+m[2] if m and m[2] in PARTICLES else None


def phrasal_lookup_head(raw):
    """Use only an original phrvbhwd: omit generic arguments, keep lexical words.

    This lookup core does not assert that an object can move across a particle.
    Possessive slots and unresolved source alternatives remain unsupported.
    """
    core = re.sub(r"(?<![\w'\u2019])" + OBJECT + r"(?![\w'\u2019])", '', raw)
    core = ' '.join(core.replace('\u2194', ' ').split()).lower()
    return core if usable(core) else None


def collect_heads(spellings, separable_sources, existing):
    """Return key -> target -> source-rule set, preserving existing content."""
    folded = {' '.join(k.casefold().split()) for k in existing}
    result = defaultdict(lambda: defaultdict(set))

    def add(key, target, rule):
        key = ' '.join(key.split())
        if usable(key) and key.casefold() not in folded and key.casefold() != ' '.join(target.casefold().split()):
            result[key][target].add(rule)

    for form, targets in spellings:
        for key, rules in entrances(form).items():
            for target in targets:
                for rule in rules:
                    add(key, target, rule)
    for raw, target in separable_sources:
        key = phrasal_lookup_head(raw)
        if key:
            rule = ('explicit_separable_phrasal_head' if separable_head(raw)
                    else 'source_phrasal_argument_lookup_head')
            add(key, target, rule)
    return result
