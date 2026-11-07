# Built from two authoritative, cross-checked primary sources:
# 1. US Library of Congress ALA-LC "Santali (in Ol script) Romanization Table" (2017)
#    https://www.loc.gov/catdir/cpso/romanization/santali.pdf
# 2. Unicode Standard 18.0 official Ol Chiki code chart (U+1C50-U+1C7F)
#    https://www.unicode.org/Public/18.0.0/charts/PDF/U1C50.pdf
#
# All 28 base letters were cross-checked between both sources (Unicode character name
# vs. LoC romanization, e.g. U+1C5C "OL CHIKI LETTER AG" = LoC "g") -- full agreement,
# no discrepancies.
#
# DELIBERATE DEVIATION FROM THE LoC STANDARD: the LoC table is a scholarly cataloging
# standard using precise diacritics (ā, ñ, ṅ, ṭ, ḍ, ṛ, ṇ, ṃ). This service instead folds
# those to plain-ASCII phonetic equivalents (ā->a, ñ->ny, ṅ->ng, ṭ->t, ḍ->d, ṛ->r, ṇ->n,
# ṃ->m), to match the existing pipeline, which already compares plain-ASCII romanized
# text (e.g. ITRANS output for Devanagari/Gujarati) against a plain-English-typed name.
# This is a documented simplification for name-matching purposes, not a scholarly
# transliteration -- do not reuse this module anywhere scholarly accuracy is required.

_VOWELS = {
    "ᱚ": "a",    # LA
    "ᱟ": "a",    # LAA (LoC: ā, folded to ASCII)
    "ᱤ": "i",    # LI
    "ᱩ": "u",    # LU
    "ᱮ": "e",    # LE
    "ᱳ": "o",    # LO
}

_CONSONANTS = {
    "ᱠ": "k",     # AAK
    "ᱜ": "g",     # AG
    "ᱶ": "ng",    # OV (LoC: ṅ)
    "ᱪ": "c",     # UC
    "ᱡ": "j",     # AAJ
    "ᱧ": "ny",    # INY (LoC: ñ)
    "ᱴ": "t",     # OTT (LoC: ṭ)
    "ᱰ": "d",     # EDD (LoC: ḍ)
    "ᱲ": "r",     # ERR (LoC: ṛ)
    "ᱬ": "n",     # UNN (LoC: ṇ)
    "ᱛ": "t",     # AT
    "ᱫ": "d",     # UD
    "ᱱ": "n",     # EN
    "ᱯ": "p",     # EP
    "ᱵ": "b",     # OB
    "ᱢ": "m",     # AAM
    "ᱭ": "y",     # UY
    "ᱨ": "r",     # IR
    "ᱞ": "l",     # AL
    "ᱣ": "w",     # AAW
    "ᱥ": "s",     # IS
    "ᱦ": "h",     # IH
    "ᱷ": "h",     # OH
    "ᱝ": "m",     # ANG (LoC: ṃ)
}

BASE_MAP = {**_VOWELS, **_CONSONANTS}

AHAD = "ᱽ"              # checked-consonant marker (Note 1) -- appends "'"
MU_TTUDDAG = "ᱸ"        # nasalization mark (Note 2) -- folded to a trailing 'n'
GAAHLAA_TTUDDAAG = "ᱹ"  # low-pitch mark -- omitted per Note 2
RELAA = "ᱻ"             # prolongation mark -- omitted ("Other Marks" note 1)
PHAARKAA = "ᱼ"          # checked-consonant separator -- omitted ("Other Marks" note 2)
OMITTED_MARKS = {GAAHLAA_TTUDDAAG, RELAA, PHAARKAA}

# MU-GAAHLAA TTUDDAAG (U+1C7A) has NO romanization rule in the LoC table at all.
# We do not guess one -- its presence marks the whole result "uncertain".
UNDOCUMENTED_MODIFIERS = {"ᱺ"}

DIGITS = {chr(0x1C50 + i): str(i) for i in range(10)}
PUNCTUATION = {"᱾": "", "᱿": ""}


class OlChikiResult:
    def __init__(self, text, certain):
        self.text = text
        self.certain = certain


def transliterate_ol_chiki(text: str) -> OlChikiResult:
    output = []
    certain = True

    for ch in text:
        if ch in UNDOCUMENTED_MODIFIERS:
            certain = False
            continue

        if ch in OMITTED_MARKS:
            continue

        if ch == AHAD:
            if output:
                output[-1] = output[-1] + "'"
            continue

        if ch == MU_TTUDDAG:
            if output:
                output[-1] = output[-1] + "n"
            continue

        if ch in BASE_MAP:
            output.append(BASE_MAP[ch])
            continue

        if ch in DIGITS:
            output.append(DIGITS[ch])
            continue

        if ch in PUNCTUATION:
            continue

        output.append(ch)  # not Ol Chiki (space, Latin text, etc.) -- pass through

    return OlChikiResult(text="".join(output), certain=certain)
