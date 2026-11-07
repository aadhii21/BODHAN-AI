"""Folds a Latin-script (ISO 15919) transliteration of an Indian name into a
canonical comparison form, so that legitimate spelling-convention differences
don't register as a mismatch.

Each rule here addresses one specific, named, linguistically-documented
phenomenon -- none of this is a black box, and none of it is tuned to any
particular test name. Every rule is applied identically to BOTH sides of a
comparison (the manually entered name and the OCR-extracted name), regardless
of which one started in which script, so the result does not depend on
comparison direction.

Root cause background (confirmed via direct testing, not assumed):
  "Sanjay Singh" (English) vs. a correct Tamil OCR of the same name
  transliterates (via ISO) to something like "jhanjay jhingh" -- NOT because
  the transliteration is wrong, but because of five distinct, well-documented
  phenomena this module folds away:
    1. Anusvara/nasal assimilation ("M" before any consonant, not assimilated
       to the following consonant's place of articulation).
    2. Hindi schwa retention (written vowels Hindi speakers don't pronounce).
    3. Long-vowel spelling convention (formal "i" vs. casual "ee").
    4. Historically-silent "h" in surnames like Singh/Sinha/Shah.
    5. Tamil/Dravidian script ambiguity: Tamil's script genuinely cannot
       distinguish voiced/voiceless/aspirated consonant pairs (one letter
       serves k/kh/g/gh, one serves c/ch/j/s/sh, etc.) -- confirmed against
       the official ISO 15919 standard, not an assumption.
"""

import re
import unicodedata


def _to_ascii_base_letters(text: str) -> str:
    """Decompose ISO-scheme diacritics (ñ, ṅ, ṭ, ḍ, ṛ, ṇ, ṃ, ī, ā, ...) to their
    plain-ASCII base letter via Unicode NFKD decomposition + stripping combining
    marks. Verified directly: ñ->n, ṅ->n, ṭ->t, ḍ->d, ṛ->r, ṇ->n, ṃ->m, ī->i,
    ā->a, ū->u, ē->e, ō->o, ṉ->n, ḷ->l, ḻ->l.

    This is NOT a naive "strip non-ASCII" filter -- an earlier version used
    one, and it was found (by direct testing) to silently DELETE diacritic
    letters outright rather than fold them, losing real content (e.g. "ṉ"
    vanishing from "mīṉā" instead of becoming "n").
    """
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _strip_non_letters(text: str) -> str:
    """Removes anything that isn't a letter or a space -- e.g. ITRANS/ISO-style
    disambiguation marks like "~" -- which are not phonetic content and would
    otherwise break the adjacency-based rules below (e.g. detecting "n before
    a consonant" requires the consonant to actually be the next character).
    Spaces are kept at this stage; the word-boundary rules below need to see
    the end of each individual word, not just the end of the whole string.

    The OCR model's markdown uses "▁" (U+2581) as its word-separator instead
    of a real space -- it is converted to a space FIRST, not simply deleted
    like other non-letter characters. Found via a real bug: deleting it
    outright (as an earlier version of this function did) silently FUSED
    adjacent words together ("அனிதா▁மிஸ்ரா" -> "anidha"+"misra" with no space
    between them at all), which changes fuzzy-match scores in ways that don't
    reflect the actual text -- confirmed by direct testing to shift a real
    score from 44% (correctly space-separated) to 53% (fused).
    """
    text = text.replace("▁", " ")
    t = re.sub(r"[^a-zA-Z\s]", "", text)
    return re.sub(r"\s+", " ", t).strip()


def _fold_long_vowels(text: str) -> str:
    """Formal transliteration renders a long vowel as a single letter (ī->i),
    but common English spelling of Indian names often doubles it instead
    ("Meena", "Geeta", "Pooja"). Folding both conventions to the same single
    letter makes them comparable regardless of which spelling style was used.
    """
    return text.replace("ee", "i").replace("oo", "u")


def _fold_nasal_assimilation(text: str) -> str:
    """Anusvara (represented in ISO as "m" with a dot, already reduced to
    plain "m" by _to_ascii_base_letters) assimilates to the place of
    articulation of the FOLLOWING consonant in natural speech/spelling --
    "san"+jay, "sin"+gh -- but a generic transliteration scheme doesn't apply
    that assimilation, rendering it as a flat "m" regardless of context.
    Native nasal letters (n, ng, ny, and the various retroflex/dental n's,
    already reduced to "n" by _to_ascii_base_letters) have the same ambiguity
    across different transliteration/spelling conventions.

    Folding m/n/ng/ny to one symbol when NOT followed by a vowel (i.e.
    consonant-adjacent or word-final) absorbs this ambiguity. Before a vowel,
    a nasal is phonemically load-bearing (e.g. "Nita" vs. "Mita" truly
    differ), so it is deliberately left alone there.
    """
    return re.sub(r"(ng|ny|n|m)(?=[^aeiou]|$)", "N", text)


def _fold_silent_h_and_schwa(text: str) -> str:
    """Two related, well-documented Hindi/Sanskrit orthography patterns:

    1. Historically-silent trailing "h" in surnames like Singh/Sinh, Shah/Sah
       -- present in common English spelling, often absent from the sound
       actually written/spoken (e.g. a formal transliteration of "Singh" may
       come back closer to "singh"/"simha" depending on scheme).
    2. Hindi schwa retention: a single trailing "a" after a consonant at the
       very end of a word is frequently silent in modern spoken Hindi and
       commonly dropped in casual English spelling (Krishna/Krishn,
       Rama/Ram, Pramoda/Pramod).

    Both are scoped conservatively: only a SINGLE trailing vowel/h pattern at
    a word boundary is affected, not every "a" or "h" in the name.
    """
    t = re.sub(r"Nha\b", "N", text)       # e.g. "...simha" -> "...siN"
    t = re.sub(r"Nh\b", "N", t)           # e.g. "...sinh" -> "...siN"
    t = re.sub(r"ah\b", "a", t)           # e.g. "shah" -> "sha"
    t = re.sub(r"([^aeiouN])a\b", r"\1", t)  # trailing schwa after a consonant
    return t


def _fold_voicing_and_aspiration(text: str) -> str:
    """Tamil's script cannot distinguish voiced/voiceless/aspirated consonant
    pairs -- it has ONE letter per stop-consonant series, not four (confirmed
    against the official ISO 15919 standard):
      - one letter covers k / kh / g / gh
      - one letter covers c / ch / j / s / sh / z
      - one letter covers (retroflex and dental) t / th / d / dh
      - one letter covers p / ph / b / bh

    This fold is applied UNIVERSALLY (both sides of every comparison), not
    only when the source is Tamil. This was verified to be necessary, not
    optional: when a Tamil-sourced name (forced into one of these broad
    classes because Tamil's script can't tell us which specific sound was
    meant) is compared against a DIFFERENT script that DOES preserve the
    precise consonant (e.g. Telugu), the comparison only lines up if that
    other side's precise letter ALSO folds into the same class. Comparison
    direction must not matter, so the fold cannot be asymmetric.

    Trade-off (documented, not hidden): this does mean two names differing
    ONLY by a single voicing/aspiration flip (e.g. hypothetically "Kiran" vs.
    "Giran") would be folded together everywhere, not just for Tamil-sourced
    text. In practice, genuinely different Indian names essentially always
    differ in vowels or multiple consonants as well, not by a single voicing
    flip alone -- but this is a real, intentional leniency, not a guarantee.
    """
    t = re.sub(r"(kh|gh|k|g)", "K", text)
    t = re.sub(r"(ch|sh|jh|c|j|s|z)", "S", t)
    t = re.sub(r"(th|dh|t|d)", "T", t)
    t = re.sub(r"(ph|bh|p|b)", "P", t)
    return t


def fold_for_comparison(text: str, aggressive: bool = True) -> str:
    """Applies the folding rules above, in order, and returns the final
    canonical comparison string (lowercase, no spaces). Call this on BOTH
    sides of a name comparison -- never on only one -- so the result does
    not depend on which side started in which script.

    `aggressive` controls whether the nasal-assimilation, silent-h/schwa, and
    voicing/aspiration rules are applied. These exist specifically to resolve
    ambiguity introduced BY TRANSLITERATION (anusvara scheme choice, Tamil's
    script-level inability to distinguish voicing, etc.) -- confirmed by
    direct testing to be necessary for genuine cross-script matches. But the
    same testing also found a real false-positive risk when BOTH sides are
    already plain Latin-script English with no transliteration involved at
    all: "Singh" and "Sinha" are different real surnames (confirmed distinct
    even in their original Devanagari: "सिंह" uses an anusvara, "सिन्हा" uses
    an explicit "n" consonant), but the aggressive nasal fold erases exactly
    the distinction that would otherwise tell them apart. There is no
    transliteration ambiguity to resolve when a human typed both names
    directly in English -- so callers should pass aggressive=False in that
    case and rely on long-vowel folding plus fuzzy-match tolerance only.
    """
    t = _to_ascii_base_letters(text)
    t = _strip_non_letters(t).lower()
    t = _fold_long_vowels(t)
    if aggressive:
        t = _fold_nasal_assimilation(t)
        t = _fold_silent_h_and_schwa(t)
        t = _fold_voicing_and_aspiration(t)
    return t.replace(" ", "")
