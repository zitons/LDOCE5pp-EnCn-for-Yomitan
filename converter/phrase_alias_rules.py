"""Source-only phrase query rules, informed by an audit of LDOCE5++ redirects.

This is an independent implementation, not the unavailable upstream compiler.
All generated keys redirect to the original LDOCE6 phrase/sense. No dictionary
other than LDOCE6 supplies spellings, vocabulary or definitions.
"""
import itertools
import re

LIMIT = 256
OBJECT = r"(?:somebody|something|sb|sth)"


def clean(s):
    return ' '.join(s.split())


def optional_forms(phrase):
    """Brackets explicitly mark omission; (s) is attached to its word."""
    if re.search(r'\([^()]*\([^()]*\)',phrase):
        return {phrase}
    groups=re.findall(r'\(([^()]*)\)',phrase)
    if any(len(g.split())>6 or re.search(r'\b(?:especially|usually|also|meaning|British|American)\b',g) for g in groups):
        return {phrase}
    forms={''}
    for part in re.split(r'(\([^()]*\))',phrase):
        choices=['',part[1:-1]] if part.startswith('(') and part.endswith(')') else [part]
        if len(forms)*len(choices)>LIMIT:return {phrase}
        forms={a+b for a in forms for b in choices}
    return {clean(s) for s in forms if s.strip()}


def orthographic_forms(form):
    straight=form.translate(str.maketrans({'’':"'",'‘':"'",'–':'-','—':'-','‑':'-','‐':'-'}))
    variants={straight}
    for s in list(variants):
        variants.add(s.rstrip(' !?.…'))
    return {clean(s) for s in variants if s.strip()}


def separable_forms(raw):
    """Resolve independent object/particle slots only with an explicit ↔."""
    if raw.count('↔')!=1:return set()
    objects=rf"\b{OBJECT}(?:/{OBJECT})+\b"
    forms={raw}
    for _ in range(3):
        expanded=set()
        for form in forms:
            m=re.search(objects,form)
            if m:
                expanded.update(form[:m.start()]+w+form[m.end():] for w in m[0].split('/'))
            else:expanded.add(form)
        forms=expanded
    particles={'away','back','down','in','off','on','out','over','round','through','together','up','aside','apart','along','around','under'}
    expanded=set()
    for form in forms:
        left,right=form.split('↔');tokens=right.split()
        if tokens and '/' in tokens[0] and set(tokens[0].split('/'))<=particles:
            expanded.update(clean(left+' ↔ '+p+' '+' '.join(tokens[1:])) for p in tokens[0].split('/'))
        else:expanded.add(form)
    return {f for f in expanded if '/' not in f}


def full_alternatives(phrase):
    """Whole wordings joined by slashes: make up your mind/make your mind up.

    Every side repeats the same first word, which a word-level choice never
    does (be mad about/for/on somebody has one-word sides).
    """
    sides=[];depth=0;start=0
    for i,ch in enumerate(phrase):
        if ch=='(':depth+=1
        elif ch==')':depth-=1
        elif ch=='/' and depth==0:
            sides.append(phrase[start:i]);start=i+1
    sides.append(phrase[start:])
    if len(sides)<2 or depth:return set()
    sides=[clean(s) for s in sides]
    sides[-1]=re.sub(r'\s+etc$','',sides[-1])
    plain=[re.sub(r'\([^()]*\)','',s).split() for s in sides]
    if any(len(words)<2 for words in plain):return set()
    first={words[0].casefold() for words in plain}
    if len(first)!=1:return set()
    # be supposed to do/be something: the short side borrows the long one's words.
    if first<={'be','the','a','an','to','of'} and any(len(words)<3 for words in plain):return set()
    return set(sides)


def grouped_slashes(form, lexicon, preferred):
    """Resolve a whole choice group, preserving multiword alternatives.

    Unlike a token-wise Cartesian product, an alternative may contain several
    words. Unsupported boundaries are left to example evidence/review.
    """
    form=clean(form)
    if '/' not in form or re.search(r'[()]',form):return set()
    # Expand person/object slots first, without conflating them with predicates.
    pat=rf"\b{OBJECT}(?:'s)?(?:/{OBJECT}(?:'s)?)+\b"
    m=re.search(pat,form)
    if m:
        result=set()
        for choice in m[0].split('/'):
            for v in grouped_slashes(form[:m.start()]+choice+form[m.end():],lexicon,preferred):
                result.add(v)
        return result
    chunks=form.split('/')
    if len(chunks)>6:return set()
    def tags(w):
        w=w.strip(".,!?'\"").casefold()
        result={preferred[w]} if w in preferred else set(lexicon.get(w,set()))
        if w.endswith('s'):
            for base in [w[:-1],w[:-2] if w.endswith('es') else '',w[:-3]+'y' if w.endswith('ies') else '']:
                if 'noun' in lexicon.get(base,set()):result.add('noun')
        return result
    def noun_phrase(words):
        if not words:return False
        words=list(words)
        article=words[0] in {'a','an','the'}
        if article:words=words[1:]
        noun_tags=tags(words[-1])|set(lexicon.get(words[-1].casefold(),set())) if words and article else tags(words[-1]) if words else set()
        return bool(words) and 'noun' in noun_tags and all(tags(w)&{'noun','adjective'} for w in words[:-1])
    def predicate(words):
        if not words:return False
        return words[0] in {'be',"can't",'cannot','can','could','will','would','must'} or 'verb' in tags(words[0])
    first=chunks[0].split(); last=chunks[-1].split(); middle=[x.split() for x in chunks[1:-1]]
    # 'etc' is a word boundary, never a substring (not the 'etc' in stretch).
    tail=[]
    if 'etc' in last or 'etc.' in last:
        i=next(i for i,w in enumerate(last) if w in {'etc','etc.'})
        tail=last[i+1:];last=last[:i]
    alternatives=None;prefix=[]
    # Repeated articles disambiguate an appetite/a thirst/a sweat.
    articles={'a','an','the'}
    if last and last[0] in articles and all(x and x[0] in articles for x in middle):
        starts=[i for i,w in enumerate(first) if w in articles]
        if starts:
            i=starts[0] if first[0] in articles else starts[-1]
            choices=[first[i:],*middle,last]
            if all(noun_phrase(x) for x in choices):prefix=first[:i];alternatives=choices
    # A noun list may include compound nouns: hat/football boots/briefcase.
    if (alternatives is None and middle and any(len(x)>1 for x in [*middle,last])
            and noun_phrase(last) and all(noun_phrase(x) for x in middle)):
        i=len(first)-1
        while i>0 and tags(first[i-1])&{'adjective','noun'} and first[i-1] not in articles:
            i-=1
        choices=[first[i:],*middle,last]
        # The left edge must be explicit or the repeated head must show that
        # the alternatives are whole noun phrases, not shared modifiers.
        boundary=i>0 and (first[i-1] in articles or first[i-1] in {'your','his','her','their','our','my'})
        repeated_head=all(x[-1]==choices[0][-1] for x in choices)
        if all(noun_phrase(x) for x in choices) and (boundary or repeated_head or tail):
            prefix=first[:i];alternatives=choices
    # Complete predicate alternatives: be sick of / can't stand / hate ...
    if alternatives is None and predicate(first) and all(predicate(x) for x in middle) and predicate(last):
        if tail:
            alternatives=[first,*middle,last]
        elif len(chunks)==2:
            common=0
            while common<min(len(first),len(last)) and first[-1-common]==last[-1-common]:common+=1
            if common:
                tail=last[-common:];alternatives=[first[:-common],last[:-common]]
        else:
            # Shared object phrase begins at a determiner/placeholder. The
            # preceding rightmost predicate must contain no lexical object.
            i=1 if all(len(x)==1 for x in [first,*middle]) else next(
                (i for i,w in enumerate(last[1:],1) if w in articles or re.fullmatch(OBJECT,w)),None)
            if i is not None:
                preps={'from','to','on','at','in','of','for','with','by','into','onto','upon','over','under','through'}
                while i>1 and last[i-1] in preps:i-=1
                tail=last[i:];alternatives=[first,*middle,last[:i]]
                # get to like/know/understand ... shares 'get to'; be
                # torn/split/rent ... shares the copula.
                if len(first)>1 and all(len(x)==1 for x in middle) and (
                        (first[0]=='be' and len(first)==2) or
                        (first[-2]=='to' and 'verb' in lexicon.get(first[-1].casefold(),set()))):
                    prefix=first[:-1];alternatives=[first[-1:],*middle,last[:i]]
        # An explicit etc boundary must not drop a shared infinitive prefix:
        # go to show/prove/indicate etc something -> go to prove something.
        if (alternatives is not None and not prefix and len(first)>1 and
                first[-2]=='to' and 'verb' in lexicon.get(first[-1].casefold(),set()) and
                all(len(x)==1 for x in [*middle,last])):
            prefix=first[:-1];alternatives=[first[-1:],*middle,last]
    if alternatives is None:return set()
    return {clean(' '.join(prefix+a+tail)) for a in alternatives if a}


def enhanced_variants(phrase, raw_forms, lexicon, preferred, examples, simple, attests):
    result={};review=[]
    def add(value,rule):
        value=clean(value)
        if value and value!=phrase:result.setdefault(value,set()).add(rule)
    resolved={phrase}
    for form in optional_forms(phrase):
        if '/' not in form and '(' not in form:
            resolved.add(form)
            if form!=phrase:add(form,'explicit_optional_group')
        else:
            proposals=simple(form)
            grouped=grouped_slashes(form,lexicon,preferred)
            for candidate in grouped:
                if attests(candidate, examples):
                    add(candidate,'source_example_attested');resolved.add(candidate)
                else:
                    review.append('unattested_grouped_candidate: '+candidate)
            for candidate in proposals:
                if not re.search(r'[/()]',candidate):
                    add(candidate,'source_validated_local_choices');resolved.add(candidate)
            if '/' in form and not grouped and not proposals:
                review.append('unresolved_group_boundary: '+form)
    # Separable syntax needs the original marker, not the canonicalized key.
    for raw in raw_forms:
        if '↔' not in raw:continue
        forms=optional_forms(raw)
        for form in forms:
            candidates={form}|set(simple(form))|separable_forms(form)
            for candidate in candidates:
                if candidate in separable_forms(form):
                    original_order=clean(candidate.replace('↔',' '))
                    resolved.add(original_order);add(original_order,'source_separable_independent_slots')
                m=re.fullmatch(rf'(.+?)\s+({OBJECT})\s*↔\s*(.+)',candidate)
                if m and not re.search(r'[/()]',candidate):
                    suffix=m[3].split()
                    if any(re.fullmatch(OBJECT,w) for w in suffix):
                        value=clean(' '.join([m[1],suffix[0],m[2],*suffix[1:]]))
                    else:value=clean(m[1]+' '+m[3]+' '+m[2])
                    resolved.add(value)
                    add(value,'source_separable_object_position')
    # Only an explicitly trailing article is an unambiguous indexing order.
    # A capitalized comma can also belong to a title; do not guess name order.
    if phrase.count(',')==1 and not re.search(r'[/()\d]|\betc\b',phrase) and phrase.rsplit(',',1)[1].strip().casefold() in {'a','an','the'}:
        left,right=phrase.split(',',1)
        if re.fullmatch(r"[\w .'’-]+",left) and re.fullmatch(r"[\w .'’-]+",right.strip()):
            value=clean(right+' '+left);resolved.add(value);add(value,'source_comma_order')
    for form in sorted(resolved):
        if re.search(r'[/()↔]',form):continue
        forms={form}
        for value in list(forms):
            short=re.sub(r"\bsome(?:body|thing)(?:'s)?\b",lambda m: m[0].replace('somebody','sb').replace('something','sth'),value)
            forms.add(short)
            if short!=value:add(short,'placeholder_abbreviation')
        for value in forms:
            for v in orthographic_forms(value):
                if v!=value:add(v,'source_orthographic_variant')
    if len(result)>LIMIT:
        # Avoid truncating a family into an arbitrary, sort-order-dependent set.
        return {},review+['enhanced_variant_limit']
    return result,sorted(set(review))
