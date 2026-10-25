from difflib import SequenceMatcher


def _name_similarity(requested, matched):
    requested = requested.casefold().strip()
    candidates = [matched.casefold().strip()]
    candidates += [part.strip() for part in matched.casefold().split("//")]
    return max(SequenceMatcher(None, requested, c).ratio() for c in candidates)


cases = [
    ("Lightnng Bolt", "Lightning Bolt"),      # typo, should pass
    ("Stormshriek Feral", "Stormshriek Feral // Flush Out"),  # DFC face, pass
    ("Valakut Stoneforge", "Valakut Awakening // Valakut Stoneforge"),  # pass
    ("Sol Rin", "Sol Ring"),                  # typo, pass
    ("asdfghjkl", "Black Lotus"),             # garbage, reject
    ("Bolt", "Lightning Bolt"),               # too short/ambiguous
]
for req, matched in cases:
    s = _name_similarity(req, matched)
    verdict = "PASS" if s >= 0.6 else "REJECT"
    print(f"{s:.2f}  {verdict}  {req!r} -> {matched!r}")
