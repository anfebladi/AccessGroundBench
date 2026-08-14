# Third-party notices

AccessGroundBench's own source code is MIT-licensed (see [`LICENSE`](LICENSE)). This
file covers everything in or reachable from this repository that is **not** ours:
dependencies, redistributed binary assets, model code and weights fetched from
elsewhere, and the third-party user interfaces that appear inside the dataset's
screenshots.

Nothing here restricts the MIT grant over our code. It records what else you receive,
and what you accept when you run the optional components.

---

## 1. Python dependencies

Declared in [`pyproject.toml`](pyproject.toml); exact resolved versions are pinned in
`uv.lock`. Not vendored — installed from PyPI by `uv sync`.

| Package | Version | Licence |
|---|---|---|
| `litellm` | 1.91.3 | MIT |
| `numpy` | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| `Pillow` | 12.3.0 | MIT-CMU (HPND) |
| `python-dotenv` | 1.2.2 | BSD-3-Clause |
| `scipy` | 1.17.1 | BSD-3-Clause |
| `fastapi` | 0.141.1 | MIT (optional, `ui` extra) |
| `uvicorn` | 0.52.1 | BSD-3-Clause (optional, `ui` extra) |

All are permissive. To regenerate this table:

```bash
uv run python -c "import importlib.metadata as md; [print(n, md.version(n), md.metadata(n).get('License-Expression') or md.metadata(n).get('License')) for n in ['litellm','numpy','Pillow','python-dotenv','scipy','fastapi','uvicorn']]"
```

Ferret-UI runs in its own separate environment with its own requirements
(`ferret_ui/requirements.txt`) — see §4.

## 2. JavaScript / npm dependencies (web UI frontend)

`src/webui/frontend/` is a React + TypeScript + Vite application. Dependencies are not
vendored; `npm ci` installs them from the tracked `package-lock.json`. **358 packages**
are in the resolved tree (direct plus transitive, including dev and build tooling):

| Licence | Packages |
|---|---:|
| MIT | 279 |
| Apache-2.0 | 29 |
| MPL-2.0 | 24 |
| ISC | 16 |
| BSD-3-Clause | 5 |
| BSD-2-Clause | 2 |
| 0BSD / MIT-0 / Unlicense | 3 |

All are permissive or weak-copyleft; none is GPL/AGPL, and none imposes a condition on
this repository's own source. To regenerate:

```bash
cd src/webui/frontend && npm ci && npx license-checker --summary
```

**Two groups worth naming explicitly**, since a bare summary hides them:

- **MPL-2.0 (24 packages) — all of them are `lightningcss`** and its per-platform
  prebuilt binaries, pulled in by `@tailwindcss/vite`. MPL-2.0 is *file-level* copyleft:
  its condition attaches to modified MPL-licensed files, not to code that merely uses
  the tool. lightningcss is a **build-time CSS transformer** that never enters the
  shipped bundle, and we do not modify it, so nothing is owed beyond this notice.
- **Apache-2.0 (29 packages)** — chiefly `typescript` (and its per-platform binaries),
  `playwright` / `@playwright/test`, and `class-variance-authority`. All but
  `class-variance-authority` and `detect-libc` are dev/test-only. Apache-2.0 §4(b)
  requires notices to travel with redistributed source; this file is that notice.

Direct dependencies, for reference: React 19, React-DOM, ten `@radix-ui/*` packages,
Tailwind CSS 4 + `@tailwindcss/vite`, `@nivo/bar`, `@nivo/scatterplot`,
`class-variance-authority`, `clsx`, `tailwind-merge`; dev: TypeScript, Vite,
`@vitejs/plugin-react`, Vitest, jsdom, Playwright, Testing Library.

> **Use `npm ci`, not `npm install`.** The lockfile is the reproducibility guarantee.

## 3. Bundled fonts — Geist and Geist Mono (SIL OFL 1.1)

Unlike everything in §1–2, these are **redistributed here as binaries**:

- `src/webui/frontend/public/geist.woff2` — Geist
- `src/webui/frontend/public/geistmono.woff2` — Geist Mono

Copyright 2024 The Geist Project Authors (<https://github.com/vercel/geist-font>),
licensed under the **SIL Open Font License, Version 1.1**. The full licence text ships
alongside the files at `src/webui/frontend/public/FONTS-LICENSE.txt`, as the OFL
requires. Both are subsetted (latin, weights 400–600) but otherwise unmodified.

The OFL reserves the font names: if you modify these files, you must **rename** them —
a derivative may not be distributed under the name "Geist".

## 4. Ferret-UI — model code and weights (optional component, NOT redistributed)

Ferret-UI is an **optional** local baseline. It is not required to run the benchmark,
and neither its code nor its weights are stored in this repository.

**Code.** Seven upstream modules (`builder.py`, `conversation.py`, `inference.py`,
`model_UI.py`, `mm_utils.py`, `clip_encoder.py`, `constants.py`) are **downloaded at
setup time** by [`ferret_ui/download_scripts.py`](ferret_ui/download_scripts.py) from
the `jadechoghari/Ferret-UI-Llama8b` repository on Hugging Face, and are gitignored.
They were previously vendored here and have been removed: they are third-party code we
are not the party entitled to license, and shipping them inside an MIT tree would have
misstated their terms. You obtain them from upstream, under upstream's terms.

Everything else under `ferret_ui/` — `ferret_server.py`, `cli_runner.py`,
`download_scripts.py`, `verify_env.py`, `requirements.txt`, `start_server.bat` — is this
project's own code and is MIT.

**Weights and provenance chain.** The model derives from
**Apple Ferret-UI → Meta Llama 3 → LLaVA**, with a CLIP vision encoder. We redistribute
no weights, so running Ferret-UI means accepting the upstream terms directly at download
time. Those terms were checked against the sources rather than assumed:

| Layer | Terms |
|---|---|
| `jadechoghari/Ferret-UI-Llama8b` | **No licence declared** — no licence tag, no LICENSE file, no license metadata field. A community redistribution, not an official Apple release. |
| Apple `ml-ferret` (upstream Ferret) | **CC BY-NC 4.0**, *"intended and licensed for research use only"*; *"models trained using the dataset should not be used outside of research purposes"* |
| Base weights | **Meta Llama 3 Community License** — acceptable-use policy, "Built with Meta Llama 3" attribution, and a 700M-monthly-active-user threshold above which a separate Meta licence is required |

**The operative restriction is research-only use**, inherited from Apple's CC BY-NC 4.0.
The Hugging Face repository grants nothing explicitly, and an absent licence is not a
permissive one — so the upstream terms continue to govern, and the most restrictive of
them binds.

For this project that is not a problem: running the benchmark and publishing the
resulting numbers is research use, which is exactly what CC BY-NC 4.0 permits, subject to
attribution (cite arXiv:2404.05719). Commercial use of Ferret-UI is not permitted at any
point in the chain.

This constrains only the optional Ferret-UI component. Every other model in the roster
runs over a hosted API and carries no comparable restriction, so no other result in the
benchmark is affected. See [`docs/ferret-ui.md`](docs/ferret-ui.md).

## 5. Screenshots of Android and Google applications (the dataset)

The dataset under `experiment/dataset/images/` consists of screen captures of the
**Android** operating system and of first-party applications (Clock, Contacts, Phone,
Messages, Settings, Maps, Play Store, Photos, YouTube) running on a Google Pixel 6
emulator image.

- Android, the applications, their user interfaces, icons, layouts and names are the
  property of **Google LLC** and its licensors. All trademarks are their owners'.
- We claim **no ownership or licence** over any of that content. It is included solely
  as measurement stimuli, under a research-use rationale — the same basis on which UI
  grounding datasets such as RICO and Android-in-the-Wild distribute screen captures.
- The MIT licence covers our code, labels, analysis and documentation. It does **not**
  and cannot grant rights over the depicted third-party interfaces.
- No affiliation with or endorsement by Google is implied.

If you are a rights holder and object to any capture's inclusion, the screen can be
removed and the analysis re-run without it; the pipeline supports per-screen exclusion.

## 6. Personal data in the dataset

The dataset is **not free of personal data**, by explicit decision. The author's own
first name remains legible in the `contacts_*.png` captures, included with the author's
consent. It is not used as a benchmark target and appears in no prompt, label file or
result CSV. The `gmail` screen, which rendered a real inbox, has been removed from the
default dataset for this reason. See the README's dataset section for the full
statement.
