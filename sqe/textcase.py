"""S127: Title Case for display names (XO 2026-11-20). No imports from the engine: debrief, models and the GUI all use it."""

_SMALL = {"a", "an", "and", "at", "in", "of", "on", "or", "the", "to"}
_ACRONYMS = {"TOT", "SAM", "SEAD", "DEAD", "CAS", "EWR", "AWACS", "OCA", "SA", "HQ"}


def title_case(text: str, keep_caps: bool = False) -> str:
    """Small words (a, an, and, at, in, of, on, or, the, to) stay lower case except the first of a phrase; acronyms and any word with a digit (SA-6, T3, 14:20) stay as written.
    Each part of a hyphenated word is capitalised (Sukhumi-Babushara), but a part that is exactly the Arabic article 'al' stays lower case unless it starts the whole name
    ('Abu al-Duhur', 'Al-Dumayr', 'Al Qusayr' at the start). keep_caps: a word already in capitals stays as written (FARP)."""
    out = []
    for i, w in enumerate(text.split(" ")):
        core = w.rstrip(",.;:")
        if any(c.isdigit() for c in core) or core in _ACRONYMS or (keep_caps and len(core) > 1 and core.isupper()):
            out.append(w)
        elif core.lower() in _SMALL and i and not out[-1].endswith((",", ";", ":")):
            out.append(w.lower())
        elif core.lower() == "al" and i and not out[-1].endswith((",", ";", ":")) and w == core:
            out.append(w.lower())
        else:
            k = len(w) - len(w.lstrip("("))
            parts = w[k:].split("-")
            out.append(w[:k] + "-".join(p.lower() if ((j or i) and p.lower().rstrip(",.;:") == "al" and len(parts) > 1) else p[:1].upper() + p[1:].lower() for j, p in enumerate(parts)))
    return " ".join(out)
