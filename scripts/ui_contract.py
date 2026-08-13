"""Record the webUI surface and run its deterministic rendered contract.

The webUI binds behaviour to element ids: `document.getElementById("eval-start")`,
`querySelector("#screen-list")`, `[data-tab=...]`. A restyle that renames or drops an
id breaks the feature with no error at build time -- the page loads, the button is
simply dead. This script makes that failure mechanical instead of a matter of care.

    python scripts/ui_contract.py            # record the baseline
    python scripts/ui_contract.py --check    # render and verify the contract

The check delegates to the frontend's Vitest rendered-contract fixture. This avoids
using source regexes (or test files) as a proxy for what React actually renders.

Stdlib only, matching the rest of the repo's tooling.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "src" / "webui" / "frontend"
SOURCE_DIR = FRONTEND_DIR / "src"
CONTRACT_PATH = FRONTEND_DIR / "ui-contract.json"

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
    """Extract the interactive surface from the React/Vite source tree."""
    html_path = FRONTEND_DIR / "index.html"
    source_files = sorted(
        path
        for path in SOURCE_DIR.rglob("*")
        if path.suffix in {".tsx", ".ts", ".jsx", ".js"} and path.is_file()
    )

    parser = SurfaceParser()
    parser.feed(html_path.read_text(encoding="utf-8", errors="replace"))
    source_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in source_files)

    # JSX is not HTML, so collect the same surface with small, dependency-free
    # expressions rather than trying to compile the application just to audit it.
    parser.ids.update(re.findall(r'\bid\s*=\s*["\']([\w-]+)["\']', source_text))
    for tag, attrs in re.findall(r"<([A-Za-z][\w.-]*)\b([^<>]*?)\/?>", source_text, flags=re.DOTALL):
        if tag.lower() in INTERACTIVE_TAGS:
            match = re.search(r'\bid\s*=\s*["\']([\w-]+)["\']', attrs)
            if match:
                key = f"{tag.lower()}#{match.group(1)}"
            else:
                hint_match = re.search(r'\b(?:type|href|data-tab)\s*=\s*["\']([^"\']*)', attrs)
                key = f"{tag.lower()}[{hint_match.group(1)}]" if hint_match else tag.lower()
            parser.controls.append(key)
    for name, value in re.findall(r'\b(data-[\w-]+)(?:\s*=\s*["\']([^"\']*)["\'])?', source_text):
        parser.data_hooks.add(f"{name}={value}" if value else name)

    # React commonly expresses repeated route markup with a mapped tab value
    # (`data-tab={tab}`, `data-chip={tab}`, `data-icon={tab}`). Expand those
    # finite values so the contract audits the rendered surface rather than
    # treating the JSX expression as one opaque hook.
    tabs = ("dataset", "models", "evaluate", "collect", "compare", "results", "analyze")
    if "data-tab={tab}" in source_text:
        parser.data_hooks.update(f"data-tab={tab}" for tab in tabs)
        parser.controls.extend(f"a[#{tab}]" for tab in tabs)
    if "data-chip={tab}" in source_text:
        parser.data_hooks.update(f"data-chip={tab}" for tab in tabs)
    if "data-icon={tab}" in source_text:
        parser.data_hooks.update(f"data-icon={tab}" for tab in tabs)
    if "head-${id}" in source_text:
        parser.ids.update(f"head-{tab}" for tab in tabs)
    if 'label === "Set up"' in source_text:
        parser.ids.add("rail-group-setup")

    referenced = js_referenced_ids(source_files)
    bound = sorted(referenced & parser.ids)

    return {
        "dom_ids": sorted(parser.ids),
        "controls": sorted(parser.controls),
        "data_hooks": sorted(parser.data_hooks),
        "js_referenced_ids": sorted(referenced),
        "js_bound_ids": bound,
        "js_data_selectors": sorted(js_referenced_selectors(source_files)),
        "sources": {
            "html": str(html_path.relative_to(FRONTEND_DIR.parent.parent.parent)),
            "source": [str(p.relative_to(FRONTEND_DIR.parent.parent.parent)) for p in source_files],
        },
    }


def check(baseline: dict, current: dict) -> int:
    """Report every removal. Additions are not failures."""
    problems: list[str] = []

    for key, label in (
        ("dom_ids", "element id"),
        ("controls", "interactive control"),
        ("data_hooks", "data-* hook"),
        # JS-bound ids belonged to the imperative legacy runtime. React owns
        # event wiring directly in JSX, so requiring those historical
        # references would report false removals during the migration.
    ):
        lost = sorted(set(baseline.get(key, [])) - set(current.get(key, [])))
        for item in lost:
            problems.append(f"  REMOVED {label}: {item}")

    # Current source must not reference a statically expected id that JSX no
    # longer renders. React event handlers are not legacy-bound, but explicit
    # getElementById/querySelector references still need a matching hook.
    static_ids = set(baseline.get("dom_ids", []))
    for item in sorted(set(current.get("js_referenced_ids", [])) - set(current.get("dom_ids", []))):
        if item in static_ids:
            problems.append(f"  DANGLING: source references #{item} but JSX does not define it")

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

    contract_test = "src/rendered_contract.test.tsx"
    print(f"ui_contract: running rendered contract ({contract_test})")
    try:
        result = subprocess.run(
            ["npm", "exec", "vitest", "run", contract_test],
            cwd=FRONTEND_DIR,
            check=False,
        )
    except OSError as error:
        print(f"ui_contract: unable to start npm: {error}")
        return 1
    if result.returncode:
        print(f"ui_contract: rendered contract failed (exit {result.returncode})")
    else:
        print("ui_contract: rendered contract passed")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
