"""Regression tests for services/transliteration_service.py and
services/ol_chiki_transliteration.py. Run directly: python test_transliteration.py
(no pytest dependency -- plain asserts, matching this project's existing test scripts).
"""

from services.transliteration_service import transliterate_to_latin
from services.ol_chiki_transliteration import transliterate_ol_chiki, BASE_MAP


# -- Core scripts: ISO scheme, no leaked characters --------------------------- #

def test_marathi_devanagari():
    result = transliterate_to_latin("राहुल कुमार")
    assert result.status == "transliterated"
    assert result.script == "devanagari"
    assert "?" not in result.text


def test_gujarati():
    result = transliterate_to_latin("રાહુલ કુમાર")
    assert result.status == "transliterated"
    assert result.script == "gujarati"


def test_english_already_latin():
    result = transliterate_to_latin("Rahul Kumar")
    assert result.status == "already_latin"


def test_tamil_no_leaked_characters():
    # This is the specific bug found during investigation: the ITRANS scheme
    # left "ன" (U+0BA9, Tamil script) completely untransliterated in "மீனா"
    # (Meena). ISO must render it as a Latin letter (with diacritics, e.g.
    # "ṉ") instead -- diacritic-bearing Latin characters are expected and
    # correct here, so this checks for actual TAMIL-block characters
    # specifically (U+0B80-U+0BFF), not just "non-ASCII".
    result = transliterate_to_latin("மீனா சிங்")
    assert result.status == "transliterated"
    assert result.script == "tamil"
    leaked_tamil = [c for c in result.text if 0x0B80 <= ord(c) <= 0x0BFF]
    assert not leaked_tamil, f"leaked raw Tamil characters: {leaked_tamil} in {result.text!r}"


def test_dogri_uses_existing_devanagari_path():
    # ILLUSTRATIVE sample text only -- not verified by a Dogri speaker.
    result = transliterate_to_latin("राहुल कुमार")
    assert result.status == "transliterated"
    assert result.script == "devanagari"


def test_urdu_perso_arabic_remains_unsupported():
    result = transliterate_to_latin("آرو شرما")
    assert result.status == "unsupported_script"


def test_empty_text():
    result = transliterate_to_latin("")
    assert result.status == "empty"


def test_english_with_ocr_space_marker_is_already_latin():
    # Real bug found via an actual end-to-end API test: OCR markdown uses "▁"
    # (U+2581) as its word-separator instead of a real space. That single
    # non-letter symbol was wrongly disqualifying otherwise-pure-English OCR
    # text from being recognized as already-Latin.
    result = transliterate_to_latin("Child▁Name:▁Sanjay▁Singh")
    assert result.status == "already_latin"


def test_tamil_with_ocr_space_marker_still_detected():
    # The same fix must not break detection of GENUINE non-Latin text that
    # happens to also contain the OCR space-marker mixed in (i.e. real OCR
    # output), which is the normal case, not an edge case.
    result = transliterate_to_latin("சஞ்சய்▁சிங்")
    assert result.status == "transliterated"
    assert result.script == "tamil"


# -- Ol Chiki (Santali): unaffected by the ISO scheme change ------------------ #

EXPECTED_BASE = {
    "ᱚ": "a", "ᱟ": "a", "ᱤ": "i", "ᱩ": "u", "ᱮ": "e", "ᱳ": "o",
    "ᱠ": "k", "ᱜ": "g", "ᱶ": "ng", "ᱪ": "c", "ᱡ": "j", "ᱧ": "ny",
    "ᱴ": "t", "ᱰ": "d", "ᱲ": "r", "ᱬ": "n", "ᱛ": "t", "ᱫ": "d",
    "ᱱ": "n", "ᱯ": "p", "ᱵ": "b", "ᱢ": "m", "ᱭ": "y", "ᱨ": "r",
    "ᱞ": "l", "ᱣ": "w", "ᱥ": "s", "ᱦ": "h", "ᱷ": "h", "ᱝ": "m",
}


def test_ol_chiki_every_base_letter():
    assert set(EXPECTED_BASE) == set(BASE_MAP)
    for letter, expected in EXPECTED_BASE.items():
        result = transliterate_ol_chiki(letter)
        assert result.text == expected and result.certain

def test_ol_chiki_integration_via_transliteration_service():
    result = transliterate_to_latin("ᱚᱨᱳᱣ")  # illustrative mapping-table exercise, not a verified word
    assert result.status == "transliterated"
    assert result.script == "ol_chiki"
    assert result.text == "arow"


if __name__ == "__main__":
    import sys
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
