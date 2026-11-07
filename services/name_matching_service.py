import re

from rapidfuzz import fuzz

from services.normalization_service import normalize_name, normalize_name_keep_words
from services.transliteration_service import transliterate_to_latin
from services.phonetic_folding_service import fold_for_comparison

# Starting thresholds only -- illustrative, validated against a hand-built test
# matrix (see test_name_matching.py), NOT yet against real birth certificates at
# scale. These need to be re-tuned once tested against real documents.
MATCH_THRESHOLD = 90
MISMATCH_THRESHOLD = 65

# A name is usable for fuzzy comparison once transliterated to Latin script (or
# if it was already Latin). "unsupported_script", "error" and "empty" are not.
_USABLE_STATUSES = {"transliterated", "already_latin"}


def _words(text: str) -> list[str]:
    """Splits text into words for windowing purposes. The OCR model's markdown
    uses "▁" (U+2581) as its word-separator instead of a real space character
    -- confirmed by direct testing against a real document: plain str.split()
    doesn't recognize "▁" as whitespace, so a multi-field OCR block like
    "Father's Name:▁Pramod▁Singh\\nOccupation:▁...\\nMother's Name:▁..." was
    splitting into whole LINES (each still "▁"-joined internally) instead of
    individual words, making word-count-matched windowing meaningless. "▁" is
    replaced with a real space here before splitting.
    """
    return text.replace("▁", " ").split()


def _candidate_segments(block_text: str) -> list[str]:
    """Splits a (possibly multi-field) OCR block into per-line candidate
    segments for windowing, instead of treating the whole block as one flat
    sequence of words.

    Found necessary via a real false-positive on an actual multi-field
    document (a biodata with ~130 words across 17 OCR blocks): windowing
    across an entire block let the scorer combine words from UNRELATED,
    NON-ADJACENT lines into one "window" (e.g. "I" from one paragraph plus
    "entertainment" from a different paragraph several lines later),
    producing a coincidental 50% score against a completely unrelated entered
    name. Restricting windows to within a single line at a time prevents this
    category of coincidental cross-field match.

    Each line is further reduced to the text after its LAST colon, when one
    is present (most real-world fields in these documents follow a
    "label : value" pattern, e.g. "தந்தையின் பெயர் : திரு. பிரமோத் சிங்" --
    "Father's name : Mr. Pramod Singh"). This also fixes a second real
    false-positive from the same document: the label text itself
    ("பிறந்த இடம்:" / "birth place:") was being windowed and scored as a
    candidate, which a name obviously never is. Lines without a colon (e.g.
    a bare name on its own line, or free-form prose) fall back to using the
    whole line, so documents that aren't label:value structured are
    unaffected.
    """
    segments = []
    for line in block_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            segments.append(line.rsplit(":", 1)[1].strip())
        else:
            segments.append(line)
    return [s for s in segments if s]


def classify_name_match(entered_name: str, document_blocks: list[str]) -> dict:
    entered_raw = (entered_name or "").strip()
    entered_norm = normalize_name(entered_name or "")
    candidates = [block for block in document_blocks if block and block.strip()]

    if not entered_norm:
        return {
            "status": "MANUAL_REVIEW", "score": None, "method": None,
            "reason": "No name was provided to verify",
        }
    if not candidates:
        return {
            "status": "MANUAL_REVIEW", "score": None, "method": None,
            "reason": "No readable text was extracted from the document",
        }

    # Tier 1: exact match -- no normalization at all.
    for block in candidates:
        if entered_raw and entered_raw == block.strip():
            return {
                "status": "MATCH", "score": 100, "method": "exact",
                "reason": "Exact match against document text",
            }

    # Tier 2: normalized match -- same script, differs only by case,
    # punctuation or whitespace (e.g. "Rahul Kumar" vs "RAHUL  KUMAR."). The
    # containment check is WORD-BOUNDARY-AWARE (\b...\b on a space-preserving
    # normalization), not a raw substring check: a raw substring check would
    # wrongly match "Kumar" against "Kumaran" (a different, longer word that
    # merely starts with the same letters) -- confirmed by direct testing to
    # be a real false-positive risk, not a hypothetical one.
    entered_words = normalize_name_keep_words(entered_name)
    for block in candidates:
        block_norm = normalize_name(block)
        block_words = normalize_name_keep_words(block)
        if block_norm and entered_norm == block_norm:
            return {
                "status": "MATCH", "score": 100, "method": "normalized",
                "reason": "Match after normalizing case, punctuation and whitespace",
            }
        if entered_words and block_words and re.search(
            r"(?<!\w)" + re.escape(entered_words) + r"(?!\w)", block_words
        ):
            return {
                "status": "MATCH", "score": 100, "method": "normalized",
                "reason": "Match after normalizing case, punctuation and whitespace",
            }

    # Tier 3: cross-script fuzzy matching. The ENTERED name is transliterated
    # here too (not just the document) -- comparison direction must not
    # matter, so a name typed directly in e.g. Tamil or Telugu is handled the
    # same way as one typed in English.
    entered_translit = transliterate_to_latin(entered_name)
    if entered_translit.status not in _USABLE_STATUSES:
        return {
            "status": "MANUAL_REVIEW", "score": None, "method": None,
            "reason": "The entered name's script could not be reliably transliterated -- needs manual review",
        }

    entered_word_count = max(1, len(_words(entered_translit.text)))

    best_score = -1
    best_entered_script = entered_translit.script
    best_document_script = None
    saw_supported_script = False

    # Compared against word-count-matched sliding windows of each block, not the
    # whole block at once, and with a STRICT whole-string ratio rather than
    # rapidfuzz's partial_ratio. Verified by direct testing that this matters:
    # a block often contains more than just the name (e.g. "Child Name: Sanjay
    # Singh Registration No 12345"), and using partial_ratio to tolerate that
    # surrounding text also let it find an internal best-alignment that scored
    # "Meena Singh" vs. "Reena Singh" (two different people) at 91% -- a false
    # approval. Comparing explicit, word-boundary-aligned windows with a strict
    # ratio finds a genuinely-present name just as well, without that leniency.
    for block in candidates:
        block_result = transliterate_to_latin(block)
        if block_result.status not in _USABLE_STATUSES:
            continue
        saw_supported_script = True

        # Aggressive phonetic folding (nasal assimilation, voicing/aspiration,
        # silent-h/schwa) is applied only when at least one side genuinely went
        # through script transliteration -- i.e. there is real transliteration-
        # scheme ambiguity to resolve. When BOTH sides were already plain Latin
        # script (no transliteration occurred on either side), that ambiguity
        # doesn't exist, and applying the aggressive rules anyway was confirmed
        # by direct testing to create a false positive: "Singh" and "Sinha" (two
        # different real surnames) folded to an identical string and scored
        # 100%. Recomputed per block, not once, since a document can mix blocks
        # of different scripts/statuses.
        aggressive = not (
            entered_translit.status == "already_latin"
            and block_result.status == "already_latin"
        )
        entered_folded = fold_for_comparison(entered_translit.text, aggressive=aggressive)

        # Windowed per LINE/field segment, not across the whole block -- see
        # _candidate_segments' docstring for the real false-positives this
        # prevents (cross-line word combinations, and label text itself being
        # treated as a candidate).
        for segment in _candidate_segments(block_result.text):
            words = _words(segment)
            # A segment with FEWER words than the entered name is not treated
            # as a candidate at all -- comparing a short fragment directly
            # against a longer entered name is a short-string ratio-scoring
            # artifact, not a meaningful comparison. Found via a real
            # false-positive on an actual document: a one-word field value
            # ("இல்லை" / "no", from a "Mangalik: No" field) was being compared
            # whole against a two-word entered name and scored 53% purely
            # from short-string noise, not genuine similarity.
            if len(words) < entered_word_count:
                continue
            if len(words) == entered_word_count:
                windows = [segment]
            else:
                windows = [
                    " ".join(words[i : i + entered_word_count])
                    for i in range(len(words) - entered_word_count + 1)
                ]

            for window in windows:
                # A person's name never contains a digit. Found via a real
                # false-positive on an actual document: the segment
                # "8 லட்சம்+" ("8 lakh+", an annual-income field)
                # transliterated and folded to something that coincidentally
                # scored 50% against an unrelated entered name -- not because
                # of any genuine similarity, but purely because digits/symbols
                # are stripped during folding, leaving just enough letters to
                # resemble it by chance. str.isdigit() catches native-script
                # digits (Tamil, Devanagari, etc.), not just 0-9.
                if any(c.isdigit() for c in window):
                    continue
                score = fuzz.ratio(entered_folded, fold_for_comparison(window, aggressive=aggressive))
                if score > best_score:
                    best_score = score
                    best_document_script = block_result.script

    if not saw_supported_script:
        return {
            "status": "MANUAL_REVIEW", "score": None, "method": None,
            "reason": "Document script could not be reliably transliterated -- needs manual review",
        }

    if best_score < 0:
        # Every candidate segment in the document was shorter than the entered
        # name (see the word-count guard above) -- there was nothing of
        # sufficient length to meaningfully compare against, so this is a
        # distinct case from "compared and found dissimilar".
        return {
            "status": "MANUAL_REVIEW", "score": None, "method": None,
            "reason": "No text of sufficient length was found in the document to compare against -- needs manual review",
        }

    strategy = (
        f"phonetic-folded, word-window comparison "
        f"(entered: {best_entered_script or 'latin'} -> document: {best_document_script})"
    )

    if best_score >= MATCH_THRESHOLD:
        return {
            "status": "MATCH", "score": best_score, "method": "fuzzy_transliterated",
            "reason": f"Fuzzy match ({best_score:.0f}%) via {strategy}",
        }
    if best_score <= MISMATCH_THRESHOLD:
        return {
            "status": "MISMATCH", "score": best_score, "method": "fuzzy_transliterated",
            "reason": f"No sufficiently similar name found (best match {best_score:.0f}%) via {strategy}",
        }
    return {
        "status": "MANUAL_REVIEW", "score": best_score, "method": "fuzzy_transliterated",
        "reason": f"Similarity score ({best_score:.0f}%) is ambiguous -- needs manual review ({strategy})",
    }
