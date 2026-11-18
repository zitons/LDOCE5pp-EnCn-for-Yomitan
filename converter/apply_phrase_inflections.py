"""Attach auditable, LDOCE6-only inflection redirects to an alias graph.

The input graph is snapshotted: newly generated spellings are never inflected
again. Only canonical targets survive, and canonical body keys always win.
"""

import re
from collections import Counter, defaultdict

from phrase_inflections import inflection_variants


_SIMPLE = re.compile(r"[A-Za-z]+\Z")
_PREPS = frozenset("of in on at by for from to with without under over into upon".split())
_POSTPOSITIVE = frozenset("martial general elect apparent designate emeritus major minor".split())
# Dictionary notation is looked up as written, never in an inflected form.
_NOTATION = re.compile(r"[/()↔!?]|\b(?:sb|sth|etc)\b", re.I)
# These spellings drop the verb the phrase is built on.
_HEADLESS_RULES = frozenset({"lookup_omit_initial_be"})
_SINGULAR_MARKERS = frozenset("a an the one each every no this that".split())
_OBJECT_STARTS = frozenset(
    """somebody someone something somebody's someone's yourself oneself your the a an it
    me you him her us them this that my his our their its myself himself herself itself
    ourselves themselves yourselves""".split())


def _norm(value):
    return " ".join(value.replace("↔", " ").split()).casefold()


def _squash(value):
    return re.sub(r"[\s\-]+", "", value).casefold()


def _countable(gram):
    return bool(re.search(r"\bcountable\b|\bc\b", gram.casefold()))


def apply_inflections(db, canonical_keys, aliases, preferred_pos):
    """Mutate aliases[query][canonical_target] sets and return audit counters.

    ``db`` is a sqlite3 connection with source_head_grammar,
    source_word_forms, lexical_pos and occurrences tables. POS and countability
    come exclusively from that source metadata: the phrase's own entry head,
    else the homograph whose sense contains it (source_entry_pos), else the
    first word's primary class. Explicit single-word verb forms are filtered
    to alphabetic words before applying them to a phrase head.
    """
    stats = Counter()
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"source_head_grammar", "source_word_forms"} <= tables:
        return Counter({"metadata_absent": 1})
    canonical = set(canonical_keys)
    grammar = defaultdict(list)
    forms = defaultdict(lambda: defaultdict(set))
    lexicon = defaultdict(set)
    preferred = {_norm(k): v for k, v in preferred_pos.items()}
    for word, pos in db.execute("SELECT word,pos FROM lexical_pos"):
        lexicon[_norm(word)].add(pos)
    for word, pos, gram, syllables in db.execute(
            "SELECT word,pos,gram,syllables FROM source_head_grammar"):
        grammar[_norm(word)].append((pos, gram or "", syllables))
    for word, form, kind in db.execute("SELECT word,form,kind FROM source_word_forms"):
        forms[_norm(word)][kind].add(form)
    # given, broken: listed as verbs, but they are forms of give and break.
    derived = {form.casefold() for word, kinds in forms.items()
               for kind in ("past", "participle", "ing", "third")
               for form in kinds.get(kind, ()) if form.casefold() != word}
    derived -= {word for word, rows in grammar.items() if any(r[0] == "verb" for r in rows)}
    phrasal = {_norm(row[0]) for row in db.execute(
        "SELECT DISTINCT phrase FROM occurrences WHERE kind IN ('phrvbhwd','phrv')")}
    # Sense-level phrases: word classes and headwords of their homographs.
    context = defaultdict(lambda: defaultdict(set))
    if "source_entry_pos" in tables:
        for phrase, parent, pos in db.execute(
                """SELECT o.phrase,o.parent,e.pos FROM occurrences o JOIN source_entry_pos e
                   ON e.record_id=o.record_id AND o.xpath LIKE e.div||'/%'
                   WHERE o.kind='lexunit'"""):
            context[_norm(phrase)][pos].add(_norm(parent))
    # Snapshot canonical + existing aliases, preserving every direct target.
    snapshot = {key: {key} for key in canonical}
    for key, targets in list(aliases.items()):
        snapshot.setdefault(key, set()).update(t for t in targets if t in canonical)

    # The most hyphenated spelling of each wording, per target.
    hyphens = defaultdict(int)
    for key, targets in snapshot.items():
        for target in targets:
            pair = (target, _squash(key))
            hyphens[pair] = max(hyphens[pair], key.count("-"))

    def add(query, target, rules):
        if query in canonical:
            stats["canonical_body_wins"] += 1
            return
        if query == target:
            return
        if target not in aliases[query]:
            stats["pairs_added"] += 1
        current = aliases[query][target]
        for rule in rules - current:
            stats["rule:" + rule] += 1
        current.update(rules)

    for phrase, targets in snapshot.items():
        if not targets:
            continue
        if _NOTATION.search(phrase):
            stats["notation_form_skipped"] += 1
            continue
        words = phrase.split()
        if len(words) < 2 and "-" not in phrase:
            continue
        first = words[0].casefold()
        own = _norm(phrase)
        for target in targets:
            # 'tie in' written for 'tie-in' is inflected through the hyphenated
            # spelling below; alone it would be read as verb + preposition.
            if phrase.count("-") < hyphens[(target, _squash(phrase))]:
                stats["dehyphenated_form_deferred"] += 1
                continue
            goal = _norm(target)
            relevant = [own] if own in grammar else [own, goal]
            evidence = [row for key in relevant for row in grammar.get(key, ())]
            head_pos = {row[0] for row in evidence}
            senses = context.get(goal, {})
            verb = None
            noun = None
            phrasal_evidence = own in phrasal or goal in phrasal
            lexical_verb = (len(words) > 1 and _SIMPLE.fullmatch(words[0])
                            and "verb" in lexicon[first] and first not in derived
                            and not _HEADLESS_RULES & aliases.get(phrase, {}).get(target, set()))
            # bowl somebody a googly, force the pace: an object or article
            # directly after a word that is never a preposition or adverb.
            transitive = (len(words) > 1 and words[1].casefold() in _OBJECT_STARTS
                          and not {"preposition", "adverb"} & lexicon[first])
            if not lexical_verb:
                allowed = False
            elif head_pos:
                # A complete head's noun-only reading outranks the spelling of
                # its first word (work permit must not become worked permit).
                allowed = "verb" in head_pos or phrasal_evidence
                if not allowed:
                    stats["noun_only_verb_blocked" if head_pos <= {"noun"} else "nonverb_head_blocked"] += 1
            elif phrasal_evidence:
                allowed = True
            elif senses:
                # hang by a thread sits in hang (verb); leap of faith in leap
                # (noun). Under another headword (give somebody a hand, in
                # hand) the first word's primary class decides.
                other = {p for pos, parents in senses.items() if pos != "verb" for p in parents}
                allowed = first in senses.get("verb", ()) or (
                    first not in other and (preferred.get(first) == "verb" or transitive))
                if not allowed:
                    stats["sense_context_verb_blocked"] += 1
            else:
                # Cross-reference boxes carry no word class. Proper names and
                # titles (Miss Universe) are not verb phrases.
                allowed = (preferred.get(first) == "verb" or transitive) and not target[:1].isupper()
                if not allowed:
                    stats["unclassified_verb_blocked"] += 1
            if allowed:
                verb = {}
                for kind in ("past", "participle", "ing", "third"):
                    verb[kind] = {v for v in forms[first][kind] if _SIMPLE.fullmatch(v)}
                stats["verb_candidates"] += 1

            noun_rows = [r for r in evidence if r[0] == "noun"]
            if noun_rows:
                explicit = set()
                for key in relevant:
                    explicit.update(forms[key]["plural"])
                noun = {"plurals": explicit, "countable": any(_countable(r[1]) for r in noun_rows)}
                if explicit:
                    stats["explicit_plural_candidates"] += 1
                elif noun["countable"]:
                    prep = next((i for i, word in enumerate(words) if word.casefold() in _PREPS), None)
                    # Source complete noun heading authorizes the construction;
                    # source lexical noun evidence identifies its internal head.
                    index = prep - 1 if prep is not None else len(words) - 1
                    if index >= 0 and "noun" in lexicon[words[index].casefold()]:
                        selected_forms = {v for v in forms[words[index].casefold()]["plural"]
                                          if _SIMPLE.fullmatch(v)}
                        if prep is not None:
                            noun["head_index"] = index
                            noun["head_plurals"] = selected_forms
                        elif words[index].casefold() not in _POSTPOSITIVE:
                            noun["last_plurals"] = selected_forms
                        else:
                            noun["countable"] = False
                            stats["postpositive_noun_head_blocked"] += 1
                    else:
                        noun["countable"] = False
                        stats["unverified_noun_head_blocked"] += 1
                    stats["countable_noun_candidates"] += 1
            elif (not head_pos and verb is None and senses and set(senses) <= {"noun"}
                  and all(_SIMPLE.fullmatch(w) for w in words)
                  and not _SINGULAR_MARKERS & {w.casefold() for w in words}):
                # A noun phrase inside a countable noun's sense, built on that
                # noun: leap of faith -> leaps of faith. A verb idiom filed
                # under its noun (give somebody a dig) is not pluralized.
                parents = {p for p in senses["noun"] if any(
                    r[0] == "noun" and _countable(r[1]) for r in grammar.get(p, ()))}
                lowered = [w.casefold() for w in words]
                if (len(words) > 2 and lowered[0] in parents and lowered[1] in {"of", "in", "for"}
                        and lowered[-1] != lowered[0]):
                    noun = {"plurals": set(), "countable": True, "head_index": 0,
                            "head_plurals": {v for v in forms[lowered[0]]["plural"] if _SIMPLE.fullmatch(v)}}
                    stats["sense_noun_head_candidates"] += 1
                elif lowered[-1] in parents and not _PREPS & set(lowered):
                    noun = {"plurals": set(), "countable": True,
                            "last_plurals": {v for v in forms[lowered[-1]]["plural"] if _SIMPLE.fullmatch(v)}}
                    stats["sense_noun_last_candidates"] += 1

            spaced = phrase.replace("-", " ")
            mirror = spaced != phrase and target in snapshot.get(spaced, ())
            for query, rules in inflection_variants(phrase, verb=verb, noun=noun).items():
                # be going to -> 'being going to' is not English.
                if re.match(r"being \w+ing\b", query, re.I):
                    continue
                add(query, target, rules)
                if mirror:
                    add(query.replace("-", " "), target, rules)
    return stats
