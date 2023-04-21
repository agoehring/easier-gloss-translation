# originally written by Anne Goehring

import spacy
import sys

from spacy.language import Language


def print_token(token):
    print(token.text, token.ent_type_, token.lemma_, token.pos_, token.tag_, token.dep_, token.head, token.morph,
          file=sys.stderr)


def attach_svp(tokens):
    for token in tokens:
        # fix the wrong verb lemma first
        if token.pos_ == "VERB":
            token.lemma_ = token.lemma_.lower()
            if not token.lemma_.endswith('n'):
                token.lemma_ += 'n'
        # and prefix the separable verb particle to the corrected lemma
        elif token.dep_ == 'svp':
            token.head.lemma_ = token.lemma_ + token.head.lemma_


def get_clauses(tokens):
    # for token in tokens:
    #    print_token(token)
    diff = lambda l1, l2: [x for x in l1 if x not in l2]
    verbs = [t for t in tokens if (t.pos_ == "VERB" and t.dep_ != "oc")
             or (t.pos_ == "AUX" and t.dep_ == "mo" and t.head.pos_ == "VERB")  # AUX in subclause
             or t.dep_ == "ROOT"  # ROOT to catch AUX in main clause
             ]
    subtrees = [[t for t in v.subtree] for v in verbs]
    clauses = [s for s in subtrees]
    subtrees.sort(key=len, reverse=True)
    new_clauses = []
    for clause in clauses:
        new_clause = clause
        for s in subtrees:
            if len(s) < len(new_clause):
                diff_clause = diff(new_clause, s)
                if diff_clause:
                    new_clause = diff_clause
        new_clauses.append(new_clause)

    return new_clauses


def reorder_sub_main(clauses):
    # find which clause is the subordinate
    # wenn KOUS ->cp-> benötigen ->mo-> Suchen: MAIN-SUBwenn to be reordered as SUBwenn-MAIN+dann?
    # Wenn KOUS ->cp-> benötigen ->re-> dann: already ordered as SUBwenn-MAINdann
    sub_clause = -1
    main_clause = -1
    main_verb = None

    for i, clause in enumerate(clauses):
        for token in clause:
            if token.tag_ == "KOUS" and token.dep_ == "cp" and token.head.dep_ == "mo":
                main_verb = token.head.head
                sub_clause = i

    if sub_clause >= 0:
        assert main_verb is not None

        # print(f"sub_clause: {clauses[sub_clause]}", file=sys.stderr)
        for j, clause in enumerate(clauses):
            if main_verb in clause:
                main_clause = j
        # if main_clause >= 0: # assert as there should be a main clause for the subordinate!
        #    print(f"main_clause: {clauses[main_clause]}", file=sys.stderr)

        if sub_clause > main_clause:
            # swap(clauses, sub_clause, main_clause)
            # TODO: instead of simply swapping them, should rather put the subclause in front of the corresponding main clause, in the case there are more than 2 clauses...
            clauses[sub_clause], clauses[main_clause] = clauses[main_clause], clauses[sub_clause]

    return clauses


def get_triplets(pairs, word_order='sov'):
    # pairs: [(s,v), (o,v)]
    triplets = []

    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            # same verb
            if pairs[i][1] == pairs[j][1]:
                v = pairs[i][1]  # or pairs[j][1]
                if pairs[i][0].dep_ in {'sb', 'nsubj'}:
                    s = pairs[i][0]
                    o = pairs[j][0]
                else:
                    s = pairs[j][0]
                    o = pairs[i][0]
                if word_order == 'sov':
                    triplets.append((s, o, v))
                elif word_order == 'svo':
                    triplets.append((s, v, o))
                elif word_order == 'osv':
                    triplets.append((o, s, v))

    return triplets


def swap(tokens, token_a, token_b):
    # token_a(fter) should swap with token_b(efore) in the sequence of tokens
    # [ ...b...a...] => [...a...b...]
    new_tokens = []

    # move the verb
    if token_a.head == token_b:
        verb = token_b
        subtree = [t for t in token_a.subtree]
        # print('move the verb after the subtree', file=sys.stderr)
        insubtree = False
        for t in tokens:
            if t == verb:
                continue
            if t in subtree:
                insubtree = True
            elif insubtree:
                new_tokens.append(verb)
                insubtree = False
            new_tokens.append(t)
        if insubtree:
            new_tokens.append(verb)

    elif token_b.head == token_a:
        verb = token_a
        subtree = [t for t in token_b.subtree]
        put_a = False
        # print('move the verb before the subtree', file=sys.stderr)
        for t in tokens:
            if t == verb:
                continue
            if t in subtree and not put_a:
                new_tokens.append(verb)
                put_a = True
            new_tokens.append(t)
    else:
        # print('swap the subject and the object', file=sys.stderr)
        subtree_a = [t for t in token_a.subtree]
        subtree_b = [t for t in token_b.subtree]
        put_a = False
        for t in [t for t in tokens if t not in subtree_a]:
            if t in subtree_b and not put_a:
                new_tokens.extend(subtree_a)
                put_a = True
            new_tokens.append(t)

    return new_tokens


def reorder_svo_triplets(clause, word_order='sov'):
    pairs = []
    for token in clause:
        # print_token(token)
        if token.dep_ in {"sb", "oa",  # DE
                          "nsubj", "obj", "obl:arg",  # FR
                          }:
            pairs.append((token, token.head))

    # print(pairs, file=sys.stderr)
    reordered_triplets = get_triplets(pairs, word_order=word_order)
    # print(word_order, 'reordered:', reordered_triplets, file=sys.stderr)
    if reordered_triplets:
        # 6 possible (a,b,c)-triplet order
        (token_a, token_b, token_c) = reordered_triplets[0]
        if (token_a.i < token_b.i) and (token_b.i < token_c.i):
            # print('# 1,2,3 => no change', file=sys.stderr)
            pass
        elif (token_a.i < token_b.i) and (token_b.i > token_c.i):
            # print('# 1,3,2 => swap 3,2', file=sys.stderr)
            # print_token(token_b)
            # print_token(token_c)
            clause = swap(clause, token_b, token_c)
        elif (token_a.i > token_b.i) and (token_a.i < token_c.i):
            # print('# 2,1,3 => swap 2,1', file=sys.stderr)
            clause = swap(clause, token_a, token_b)
        elif (token_a.i < token_b.i) and (token_a.i > token_c.i):
            print('# 2,3,1 => put 1 before', file=sys.stderr)  # TODO
            pass
        elif (token_a.i > token_b.i) and (token_a.i > token_c.i):
            print('# 3,1,2 => put 3 after', file=sys.stderr)  # TODO
            pass
        elif (token_a.i > token_b.i) and (token_b.i > token_c.i):
            # print('# 3,2,1 => swap 3,1', file=sys.stderr)
            clause = swap(clause, token_a, token_c)

    return clause


def haben_main_verb(token):
    if token.lemma_ == "haben":
        # is there a dependent main verb?
        for c in token.children:
            if c.pos_ == "VERB" and c.dep_ == "oc":
                return False
        return True

    return False


def gloss_de_poss_pronoun(token):
    # DE: mein/dein/sein/ihr/Ihr/unser/euer
    pposat_map = {'M': 'mein', 'm': 'mein', 'D': 'dein', 'd': 'dein', 'S': 'sein', 's': 'sein', 'i': 'ihr',
                  'I': 'Ihr', 'U': 'unser', 'u': 'unser', 'E': 'euer', 'e': 'euer'}

    # return 'IX-'+pposat_map[token.text[0]]
    return '(' + pposat_map[token.text[0]] + ')'


def glossify(tokens):
    glossed_tokens = []

    for t in tokens:
        # print_token(t)

        # default: lemmatize
        gloss = t.lemma_

        # Plural nouns with suffix "+"
        if t.tag_ == "NN" and "Number=Plur" in t.morph:
            gloss += '+'

        # word form for adverbs (as spacy DE models sometimes set a wrong lemma)
        elif t.pos_ == 'ADV':
            gloss = t.text.lower()

        # mark German attributive possessive pronouns: put the base form in parentheses, e.g. (mein)
        elif t.tag_ == "PPOSAT":
            gloss = gloss_de_poss_pronoun(t)

        # lowercased word form for pronouns since the lemma sometimes looses the person information
        elif t.tag_ in ['PPER', 'PRF', 'PDS',  # DE, e.g. "Wir  ich PRON PPER ..."
                        'PRON', 'DET',  # FR, e.g. "sa  son DET DET ..."
                        ]:
            gloss = t.text.lower() + '-IX'

        # DE "haben" as main verb should be glossed as "DA"
        elif haben_main_verb(t):
            gloss = "da"

        # other forms of "haben" and "sein" (auxiliary) should be skipped
        # FR: avons  avoir AUX AUX aux:tense
        elif (t.lemma_ in {"habe", "haben", "sein"}  # DE
              or (t.lemma_ == "avoir" and t.pos_ == "AUX")):  # FR
            continue

        # DE: lemma of NER-identified location entities preceded by preposition
        if t.ent_type_ == "LOC" and t.head.pos_ == "ADP":
            glossed_tokens.append(t.head.text)

        # output both "wordform/lemma" to help the dictionary lookup
        if gloss != t.text:
            gloss = t.text + "/" + gloss

        glossed_tokens.append(gloss)

    return glossed_tokens


def clause_to_gloss(clause):
    # Rule 1: Extract subject-verb-object triplets and reorder them
    clause = reorder_svo_triplets(clause)

    # Rule 2: Discard all tokens with unwanted PoS
    tokens = [t for t in clause if t.pos_ in {"NOUN", "PROPN", "VERB", "AUX", "ADJ", "NUM"}
              or (t.pos_ == "ADV" and t.dep_ != "svp")
              or (t.pos_ == "PRON" and t.dep_ != "ep")
              or t.tag_ in {"PTKNEG", "KON", "PPOSAT"}  # TODO: "PDAT" e.g. gloss("dieses")=IX?
              or (t.tag_ == "DET" and "Poss=Yes" in t.morph)  # son  son DET DET det ami Number=Sing|Poss=Yes
              or (t.tag_ == "CCONJ")  # FR: mais
              ]

    # Rule 3: Move adverbs to the start?
    # TODO: Move verb modifying adverbs before the verb in each clause
    adverbs = [t for t in tokens if t.pos_ == "ADV" and t.dep_ == "mo" and t.head.pos_ == "VERB"]
    tokens = [t for t in tokens if t not in adverbs]
    tokens = adverbs + tokens

    # Rule 4: Move location words to the start
    # TODO: move only if it modifies the verb?
    locations = [t for t in tokens if t.ent_type_ == "LOC"]
    tokens = [t for t in tokens if t not in locations]
    tokens = locations + tokens

    # Rule 5: Move negation words to the end
    negations = [t for t in tokens if t.dep_ == "ng"]
    tokens = [t for t in tokens if t not in negations]
    tokens.extend(negations)

    # TODO: is compound splitting necessary? only taking the first noun loses information!
    # Rule 6: Replace compound nouns with the first noun
    for i, t in enumerate(tokens):
        if t.dep_ == "compound":
            tokens[i] = t.head

    # Rule 7: Glossify all tokens, i.e. lemmatize most tokens
    glossed_tokens = glossify(tokens)

    return glossed_tokens


def text_to_gloss(text: str, spacy_model: Language, lang: str = 'de'):
    if lang == 'fr':
        doc = spacy_model(text)
    # elif lang == 'it':
    #    doc = it_nlp(text)
    else:
        doc = spacy_model(text)
        # Rule 0: Attach separable verb particle to the verb lemma
        attach_svp(doc)

    # split sentence into separate clauses
    clauses = get_clauses(doc)
    # print(clauses, file=sys.stderr)

    # reorder clauses
    clauses = reorder_sub_main(clauses)
    # print("reordered sub and main clauses:", clauses, file=sys.stderr)

    # glossify each clause
    glossed_clauses = []
    for clause in clauses:
        glossed_tokens = clause_to_gloss(clause)
        glossed_clauses.append(glossed_tokens)

    # Final Rule: Begin sequence with a capital
    glossed_clauses[0][0] = glossed_clauses[0][0].capitalize()

    # simply end the sentence with a period: gloss = " ".join([g for clause in glossed_clauses for g in clause])
    # or more the "glosses way":
    # clause separator "|" and end of sentence "||"
    gloss = " | ".join([" ".join([g for g in clause]) for clause in glossed_clauses])

    return gloss + " ||"


def main():
    if len(sys.argv) > 2:
        lang = sys.argv[1]
        text = sys.argv[2]
    elif len(sys.argv) > 1:
        lang = 'de'
        text = sys.argv[1]
    else:
        lang = 'de'
        # text = 'Die Autobahnraststätte in Olten ist leer.'
        # text = 'Ich habe dich nicht angerufen.'
        # text = 'Die Hunde beissen schnell die sehr tapferen Frauen.'
        text = 'Suchen Sie einen Notfalltreffpunkt auf, wenn Sie Auskünfte oder Hilfe benötigen.'
        # text = 'Wenn Sie Hilfe brauchen, dann suchen Sie einen Notfalltreffpunkt auf.'

    if lang == "de":
        spacy_model = spacy.load("de_core_news_lg")
    elif lang == "fr":
        spacy_model = spacy.load("fr_core_news_lg")
    else:
        raise NotImplementedError("Don't know language '%s'." % lang)

    output = text_to_gloss(text, spacy_model=spacy_model, lang=lang)

    print(f"text:\t{text}\ngloss:\t{output}")


if __name__ == '__main__':
    main()
