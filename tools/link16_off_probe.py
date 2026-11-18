"""S103a probe: with the campaign's Link 16 switch OFF, only the Link 16 parts of a mission differ.

    set PYTHONHASHSEED=0          (Windows: the tool cannot restart itself, see miz_identity.py)
    python tools/link16_off_probe.py [--jobs N]

Builds the whole `tools/miz_identity.py` case list twice (parallel since S109, one worker per case: about a minute; --jobs N, 1 = the old serial path, about 3 to 4 minutes): once as today (Link 16 on) and once with every campaign created with
`link16=False` (the `SQE_IDENT_NO_LINK16` switch of miz_identity). Then, for every mission built, it removes the Link 16 parts from both texts and demands the rest is identical:
  - mission file: every `datalinks:` block of a unit, the `STN_L16`, `SADL_TN`, `VoiceCallsignLabel` and `VoiceCallsignNumber` properties;
  - dictionary (briefing text): the "Link 16: ..." sentence;
  - the .miz kneeboard page "2_fuel_codes_package.png" (the STN column goes) may differ; every other file must be byte-identical.
Prints the counts and every other difference it finds; exit 0 = only Link 16 parts differ."""
import os
import re
import sys

if os.environ.get("PYTHONHASHSEED") != "0":
    sys.exit("set PYTHONHASHSEED=0 first (the identity tool pins string hashing)")
os.environ.pop("SQE_IDENT_NO_LINK16", None)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import miz_identity as mi

KEEP_PAGE = "2_fuel_codes_package.png"
PROPS = re.compile(r"^\s*(STN_L16|SADL_TN|VoiceCallsignLabel|VoiceCallsignNumber):")
BRIEF = re.compile(r"Link 16: your wing are members.*?Station numbers \(STN\) are on your kneeboard\.(?:\\n)?")      # the text is a repr: a line break is a backslash and an n


def strip_mission(text: str) -> str:
    out, skip = [], None
    for ln in text.split("\n"):
        ind = len(ln) - len(ln.lstrip(" "))
        if skip is not None:
            if not ln.strip() or ind > skip:               # an empty value prints as a blank line inside the block
                continue
            skip = None
        if ln.strip() == "datalinks:":
            skip = ind
            continue
        if PROPS.match(ln):
            continue
        out.append(ln)
    return "\n".join(out)


def main(jobs=None) -> int:
    on = mi.run(jobs)
    os.environ["SQE_IDENT_NO_LINK16"] = "1"
    off = mi.run(jobs)
    n_miss = n_page = n_brief = n_l16 = bad = 0
    for key in sorted(set(on) | set(off)):
        if key not in on or key not in off:
            print(f"  {key}: only in {'on' if key in on else 'off'}"); bad += 1; continue
        n_miss += 1
        for m in sorted(set(on[key]) | set(off[key])):
            a, b = on[key].get(m), off[key].get(m)
            if a == b:
                continue
            if a is None or b is None:
                print(f"  {key} :: {m}: only in {'on' if b is None else 'off'}"); bad += 1; continue
            if m.endswith(KEEP_PAGE.replace("/", "__")) or m.endswith("2_fuel_codes_package.png"):
                n_page += 1; continue
            if m == "mission":
                a2, b2 = strip_mission(a), strip_mission(b)
                n_l16 += a != a2
            elif m.endswith("dictionary"):
                a2, b2 = BRIEF.sub("", a), b
                n_brief += a != a2
            else:
                a2, b2 = a, b
            if a2 != b2:
                bad += 1
                print(f"  {key} :: {m}: differs beyond Link 16")
                k = next((i for i, (c1, c2) in enumerate(zip(a2, b2)) if c1 != c2), min(len(a2), len(b2)))      # the first character that differs, with a little around it
                print(f"    on : ...{a2[max(0, k - 60):k + 100]!r}")
                print(f"    off: ...{b2[max(0, k - 60):k + 100]!r}")
    print(f"{n_miss} missions compared; Link 16 parts removed from {n_l16} mission files and {n_brief} briefings; {n_page} kneeboard page 2 images differ; "
          f"{bad} differences BEYOND Link 16")
    return 1 if bad else 0


if __name__ == "__main__":
    _jobs, _ = mi.parallel.pop_jobs(sys.argv[1:])
    sys.exit(main(_jobs))
