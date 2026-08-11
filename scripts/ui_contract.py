"""Freeze the webUI's interactive surface, then prove a restyle did not shrink it.

The webUI binds behaviour to element ids: `document.getElementById("eval-start")`,
`querySelector("#screen-list")`, `[data-tab=...]`. A restyle that renames or drops an
id breaks the feature with no error at build time -- the page loads, the button is
simply dead. This script makes that failure mechanical instead of a matter of care.

    python scripts/ui_contract.py            # record the baseline
    python scripts/ui_contract.py --check    # fail if anything was removed

`--check` exits 1 on any removal. Additions are always fine: a redesign is allowed to
add controls, never to silently lose them.

Stdlib only, matching the rest of the repo's tooling.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "webui" / "static"
CONTRACT_PATH = Path(__file__).resolve().parent.parent / "src" / "webui" / "ui-contract.json"

# Elements whose presence is a user-facing affordance. A restyle may restyle them,
# move them, or wrap them -- it may not delete them.
INTERACTIVE_TAGS = {"button", "input", "select", "textarea", "form", "details", "summary", "a"}


class SurfaceParser(HTMLParser):
    """Collect ids, interactive controls, and data-* hooks from the markup."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.controls: list[str] = []
        self.data_hooks: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        element_id = attr.get("id")
        if element_id:
            self.ids.add(element_id)

        if tag in INTERACTIVE_TAGS:
            # Identify a control by id when it has one, else by a stable
            # description, so an unlabelled button still has to survive.
            if element_id:
                key = f"{tag}#{element_id}"
            else:
                hint = attr.get("type") or attr.get("href") or attr.get("data-tab") or ""
                key = f"{tag}[{hint}]" if hint else tag
            self.controls.append(key)

        for name, value in attr.items():
            if name.startswith("data-"):
                self.data_hooks.add(f"{name}={value}" if value else name)


def js_referenced_ids(js_files: list[Path]) -> set[str]:
    """Every id the JavaScript reaches for.

    This is the load-bearing set: if the JS asks for an id the DOM no longer has,
    the feature is dead. Covers getElementById("x"), querySelector("#x"), and the
    el("x") helper the views use.
    """
    patterns = [
        re.compile(r"""getElementById\(\s*["'`]([\w-]+)["'`]"""),
        re.compile(r"""querySelector(?:All)?\(\s*["'`]#([\w-]+)"""),
        re.compile(r"""\bel\(\s*["'`]([\w-]+)["'`]\s*\)"""),
    ]
    found: set[str] = set()
    for path in js_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            found.update(pattern.findall(text))
    return found


def js_referenced_selectors(js_files: list[Path]) -> set[str]:
    """data-* attribute selectors the JS queries, e.g. [data-tab="results"]."""
    pattern = re.compile(r"""\[(data-[\w-]+)\s*(?:=\s*["'`]?([\w-]+))?""")
    found: set[str] = set()
    for path in js_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, value in pattern.findall(text):
            found.add(f"{name}={value}" if value else name)
    return found


def build_contract() -> dict:
    html_path = STATIC_DIR / "index.html"
    js_files = sorted(STATIC_DIR.glob("*.js"))

    parser = SurfaceParser()
    parser.feed(html_path.read_text(encoding="utf-8", errors="replace"))

    referenced = js_referenced_ids(js_files)
    # The subset that actually matters most: ids the JS binds to AND the DOM defines.
    bound = sorted(referenced & parser.ids)

    return {
        "dom_ids": sorted(parser.ids),
        "controls": sorted(parser.controls),
        "data_hooks": sorted(parser.data_hooks),
        "js_referenced_ids": sorted(referenced),
        "js_bound_ids": bound,
        "js_data_selectors": sorted(js_referenced_selectors(js_files)),
        "sources": {
            "html": str(html_path.relative_to(STATIC_DIR.parent.parent.parent)),
            "js": [str(p.name) for p in js_files],
        },
    }


def check(baseline: dict, current: dict) -> int:
    """Report every removal. Additions are not failures."""
    problems: list[str] = []

    for key, label in (
        ("dom_ids", "element id"),
        ("controls", "interactive control"),
        ("data_hooks", "data-* hook"),
        ("js_bound_ids", "JS-bound id"),
    ):
        lost = sorted(set(baseline.get(key, [])) - set(current.get(key, [])))
        for item in lost:
            problems.append(f"  REMOVED {label}: {item}")

    # The dangling check does not need a baseline: any id the JS reaches for that
    # the DOM no longer defines is broken right now, however it got that way.
    dangling = sorted(set(current.get("js_referenced_ids", [])) - set(current.get("dom_ids", [])))
    # Ids created dynamically by the views legitimately never appear in index.html,
    # so only flag ones the baseline proved were served by the static markup.
    baseline_static = set(baseline.get("dom_ids", []))
    dangling = [d for d in dangling if d in baseline_static]
    for item in dangling:
        problems.append(f"  DANGLING: JS references #{item} but the DOM no longer defines it")

    if problems:
        print("ui_contract: FAILED -- the restyle removed part of the interactive surface\n")
        print("\n".join(problems))
        print(f"\n{len(problems)} problem(s). Nothing may be dropped; restyle it in place instead.")
        return 1

    added = len(set(current.get("dom_ids", [])) - set(baseline.get("dom_ids", [])))
    print(
        f"ui_contract: OK -- {len(current['dom_ids'])} ids, "
        f"{len(current['controls'])} controls, {len(current['data_hooks'])} data hooks, "
        f"{len(current['js_bound_ids'])} JS-bound ids all still present"
        + (f" ({added} added)" if added else "")
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="compare against the recorded baseline")
    args = ap.parse_args(argv)

    current = build_contract()

    if not args.check:
        CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(
            f"ui_contract: recorded {len(current['dom_ids'])} ids, "
            f"{len(current['controls'])} controls, {len(current['data_hooks'])} data hooks, "
            f"{len(current['js_bound_ids'])} JS-bound ids -> "
            f"{CONTRACT_PATH.relative_to(CONTRACT_PATH.parent.parent)}"
        )
        return 0

    if not CONTRACT_PATH.is_file():
        print(f"ui_contract: no baseline at {CONTRACT_PATH}. Run without --check first.")
        return 1

    baseline = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return check(baseline, current)


if __name__ == "__main__":
    sys.exit(main())
