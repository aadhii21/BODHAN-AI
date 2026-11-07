import re


def normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", "", name)
    return name


def normalize_name_keep_words(name: str) -> str:
    """Like normalize_name, but keeps single spaces between words instead of
    removing them entirely. Needed wherever a comparison must respect word
    boundaries -- e.g. "kumar" should match "kumar singh" (same first word)
    but must NOT match "kumaran" (a different, longer word that merely starts
    with the same letters). normalize_name's full space removal makes that
    distinction impossible to express, since "kumar" becomes a literal
    character-substring of "kumaran" either way.
    """
    name = name.lower().strip()
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name
