import re
from dataclasses import dataclass

from indic_transliteration import sanscript
from indic_transliteration.detect import detect as detect_script

from services.ol_chiki_transliteration import transliterate_ol_chiki

_OL_CHIKI_RE = re.compile(r"[᱐-᱿]")


def _has_non_ascii_letter(text: str) -> bool:
    """True only if TEXT contains a non-ASCII ALPHABETIC character -- not just
    any non-ASCII byte. Found necessary by direct testing: the OCR model's
    markdown output uses "▁" (U+2581, a tokenizer space-marker) in place of
    plain spaces, e.g. "Child▁Name:▁Sanjay▁Singh". That single symbol is
    non-ASCII but not a letter ("▁".isalpha() is False); treating its mere
    presence as "this isn't Latin script" caused otherwise-pure-English OCR
    text to be misclassified as unsupported_script and routed to
    MANUAL_REVIEW, confirmed via a real end-to-end API test.
    """
    return any(c.isalpha() and ord(c) > 127 for c in text)

# Scripts directly tested with real sample text and confirmed to produce
# correct, complete Latin transliteration via indic-transliteration.
#
# Perso-Arabic (covers Urdu, and the Perso-Arabic form of Kashmiri/Sindhi)
# and Meitei Mayek (Manipuri) were explicitly tested and produced garbled,
# half-converted output -- they are deliberately left out rather than
# silently mis-transliterated. AI4Bharat IndicXlit was investigated as a
# potential fix for these, but its "fairseq" dependency fails to build on
# this Python version, and it separately pins torch==2.2.0, which conflicts
# with this project's torch (OCR requires a newer version for MPS support).
# It is not integrated for these reasons.
#
# Ol Chiki (Santhali) is handled separately below via a dedicated rule-based
# mapper (services/ol_chiki_transliteration.py), built from the Library of
# Congress romanization table and the official Unicode chart -- not via
# indic-transliteration, whose own "ol_chiki" scheme was tested and found to
# produce garbled output.
SUPPORTED_NATIVE_SCRIPTS = {
    "devanagari",  # Hindi, Marathi, Sanskrit, Nepali, Dogri (modern usage), Maithili, Konkani
    "bengali",     # Bengali, Assamese, Manipuri (when written in Bengali script)
    "assamese",
    "gujarati",
    "gurmukhi",    # Punjabi
    "kannada",
    "malayalam",
    "oriya",       # Odia
    "tamil",
    "telugu",
}

@dataclass
class TransliterationResult:
    text: str
    script: str | None
    status: str  # "already_latin" | "transliterated" | "unsupported_script" | "empty" | "error"


def transliterate_to_latin(text: str) -> TransliterationResult:
    if not text or not text.strip():
        return TransliterationResult(text="", script=None, status="empty")

    # Text with no non-ASCII LETTER is reliably already Latin script. Stray
    # non-ASCII symbols (e.g. the OCR model's "▁" space-marker) don't count --
    # see _has_non_ascii_letter's docstring for the real bug this fixes.
    if not _has_non_ascii_letter(text):
        return TransliterationResult(text=text, script=None, status="already_latin")

    # Ol Chiki is handled by our own rule-based mapper, not indic-transliteration's
    # detector -- checked here, before falling through to detect_script(), via a
    # direct Unicode-block check (U+1C50-U+1C7F), which is exact rather than a guess.
    if _OL_CHIKI_RE.search(text):
        result = transliterate_ol_chiki(text)
        if not result.certain:
            return TransliterationResult(text=text, script="ol_chiki", status="unsupported_script")
        return TransliterationResult(text=result.text, script="ol_chiki", status="transliterated")

    try:
        script = detect_script(text)
    except Exception:
        return TransliterationResult(text=text, script=None, status="error")

    # The text contains non-ASCII characters, so if indic-transliteration's
    # detector reports anything other than one of our verified native
    # scripts -- including a "Roman" scheme name -- that is itself evidence
    # of a misdetection (confirmed: it labels untouched Perso-Arabic text as
    # the Roman "hk" scheme), not proof the text is actually Latin. Treat it
    # as unsupported rather than risk silently comparing raw native-script
    # text as if it were already transliterated.
    if script not in SUPPORTED_NATIVE_SCRIPTS:
        return TransliterationResult(text=text, script=script, status="unsupported_script")

    # ISO (ISO 15919), not ITRANS: ITRANS was found to have a real coverage gap for
    # Tamil -- it silently left the character "ன" untransliterated in "மீனா"
    # (Meena), leaking raw Tamil into what was reported as a successful
    # transliteration. ISO was directly verified to transliterate the same text
    # completely, with no leaked characters. ISO encodes several sounds using
    # Latin letters with combining diacritics (e.g. ñ, ṅ, ṭ, ḍ, ṛ, ṇ, ṃ, ī, ā) --
    # services/phonetic_folding_service.py is responsible for folding these to
    # plain ASCII via Unicode NFKD decomposition; this function intentionally
    # returns the full-fidelity ISO output, not an ASCII-reduced form.
    try:
        latin = sanscript.transliterate(text, script, sanscript.ISO)
    except Exception:
        return TransliterationResult(text=text, script=script, status="error")

    return TransliterationResult(text=latin, script=script, status="transliterated")
