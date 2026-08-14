# AccessGroundBench

**Does turning on accessibility settings break VLM phone agents?**

Vision-language model agents that operate phones are pitched as an accessibility win.
But they are trained and benchmarked on *default-configured* screens — while the users
most likely to need an agent (older adults, low-vision users) are exactly the users
whose phones are not default-configured. AccessGroundBench measures what happens when
they are not.

Concretely, it measures **UI text grounding**: given a screenshot and the name of an
on-screen element, return the pixel coordinates you would tap to hit it. The same model
answers the same query on a baseline screenshot and on each accessibility-modified
screenshot of the *same screen* — a paired, within-subject design — and the difference is
tested statistically.

The benchmark separates two things that are usually conflated:

- **Reachability** — whether a baseline target still *exists* on the modified screen at
  all. This is a property of the layout, not of the model.
- **Grounding accuracy** — whether the model locates a target that is present in *both*
  layouts. A target pushed off-screen is a layout failure, not a model failure, and is
  never scored as a miss.

## Headline findings

From the current run: **12 screens, 138 targets, 17 models** on the vision arm and 16 on
the accessibility-tree arm.

1. **The largest effect is not about models at all.** The compounded profile
   (1.6× font, 520 dpi) removes **24.6%** of interactive text from the reachable screen.
   No agent, however good, can tap what is not rendered.
2. **Text reflow is the failure mode, not visual distortion.** Font scaling significantly
   degrades grounding, and so do both compound profiles. Density inflation *alone* does
   not — it trends slightly the other way, because targets get bigger.
3. **Injecting the accessibility tree helps, but does not fix it.** Overall accuracy rises
   89.7% → 92.9%, concentrated in models that had headroom. The accessibility profiles
   remain significant *within* the tree arm. One model (GLM-V) is significantly **worse**
   with the tree.

**What this does *not* show:** "frontier VLMs collapse under accessibility settings."
Most sit above 95% baseline accuracy with only a handful of changed answers, which makes
the per-model tests structurally underpowered — their null results are not evidence of
resilience. Read the [limitations](#limitations-read-before-citing) before citing
anything.

Full statistical treatment, including every formula and a worked example, is in
[`docs/methods.md`](docs/methods.md).

## Requirements

- Python 3.11 or later, and [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ and npm — only for the optional web UI
- Android Studio / AVD and Android SDK Platform Tools (`adb`) — only to **collect** new
  captures. Evaluating and analysing the shipped dataset needs no emulator.
- A CUDA-capable GPU (~10 GB VRAM) — only for the optional local Ferret-UI baseline

## Quickstart

```bash
uv sync
cp .env.example .env
# edit .env: set VLM_MODEL and the matching provider API key
uv run agb evaluate          # score a model against the shipped dataset
uv run agb analyze           # produce the statistical tables
```

That is the whole loop for an existing dataset — no emulator, no collection step. Prefix
every command with `uv run`; this is also the Windows workflow.

On macOS and Linux you can optionally install a launcher so bare `agb ...` works from
anywhere inside the clone:

```bash
./scripts/install-agb.sh      # installs to ${XDG_BIN_HOME:-$HOME/.local/bin}/agb
```

The installer does not edit your shell configuration. If the destination is not on
`PATH`, follow the guidance it prints and start a new shell.

See [`docs/setup.md`](docs/setup.md) for provider configuration, emulator preparation,
and coordinate conventions.

## Adding your own model

Set `VLM_MODEL` in `.env` to a comma-separated list; each entry runs in sequence and gets
its own result file. The prefix selects the transport:

| Prefix | Requires |
|---|---|
| `openai/` `gemini/` `anthropic/` | native LiteLLM plus the matching `*_API_KEY` |
| `openai_compatible/<model>` | `OPENAI_COMPATIBLE_BASE_URL` + `OPENAI_COMPATIBLE_API_KEY` |
| `local/ferret-ui-llama8b` | a local Ferret-UI server ([`docs/ferret-ui.md`](docs/ferret-ui.md)) |

```dotenv
VLM_MODEL=anthropic/claude-opus-5, openai_compatible/qwen/qwen3-vl-235b-a22b-instruct
USE_A11Y_TREE=false     # true injects a partial accessibility tree, writing *_tree.csv
```

Results are named after the **model**, not the route used to reach it, so a gateway in
front of a model does not leak into published filenames.

> **Two things to check for any new model**, both of which have silently cost real
> accuracy here:
>
> 1. **Does the provider downscale your image?** If so the model answers in the space it
>    was *shown*, not the space your prompt describes. Declare the cap in
>    `MAX_IMAGE_EDGE` and the pipeline resizes, records, and rescales correctly. Left
>    undeclared, two models scored **17% instead of ~100%**.
> 2. **Does it answer in normalised 0–1000 coordinates** rather than pixels? Several do.
>    A low score is far more often a coordinate-space mismatch than a grounding failure —
>    run `agb rescore --csv <result.csv> --check` before believing one.

## Reproducing the results

```bash
uv run agb evaluate                    # resumes by default; --fresh restarts
uv run agb analyze                     # writes the full table set
uv run agb rescore --csv experiment/outputs/evaluations/MODEL_vision.csv --check
```

Evaluation appends one row per `(screen, target, profile)` and is **resumable** — an
interrupted run does not lose paid API calls. Nothing that truncates or rewrites a
result file does so without first copying it aside into a `.backups/` directory.

Analysis writes to `experiment/outputs/analysis/`. Every dataset owns exactly one output
root — the active one uses `experiment/outputs/`, and any other dataset (an archive, or a
directory passed to `--data-dir`) owns an `outputs/` directory inside itself. That is what
stops re-analysing an archive from overwriting the current run's tables.

Collecting a *new* dataset needs a configured emulator and is documented separately —
see [`docs/collection.md`](docs/collection.md) and the
[live collection runbook](docs/runbooks/collection.md). `uv run agb collect --dry-run`
checks the logic without one.

## Web UI

A local browser front end over the same commands — evaluate a model, browse results, run
the analysis, without memorising environment variables.

```bash
uv sync --extra ui
cd src/webui/frontend && npm ci && cd -
uv run agb ui
```

Use `npm ci`, not `npm install`: the tracked `package-lock.json` is what makes the
frontend reproducible. `agb ui` serves on `http://127.0.0.1:8080` (bound to localhost,
never exposed to the network) with its API on port 8081.

Every action displays the equivalent `agb` command it ran, and it writes results in
exactly the same place and format the CLI does — the UI is a front end, not a second
pipeline. See [`docs/ui.md`](docs/ui.md).

## Repository layout

```text
src/                     Python package and the `agb` command
src/webui/frontend/      React + TypeScript web UI
ferret_ui/               Optional local Ferret-UI server (separate environment)
docs/                    Reference documentation and runbooks
tests/                   Unit tests
experiment/
  dataset/               Input captures, labels, raw XML, and the manifest
  outputs/               Results derived from it: evaluations/ and analysis/
  archive/               Superseded runs -- local only, gitignored, not citable
    experiment_1/        Each archive is self-contained: its captures plus
    experiment_2/          its own outputs/ holding that run's tables
```

One experiment is a dataset plus everything derived from it, so both live under a single
root. Captures under `experiment/dataset/` **are** committed; `experiment/archive/` is
not — those runs predate several scoring fixes and must not be cited.

## The profiles

| Profile | Font scale | Density | Colour filter | Isolates |
|---|---:|---|---|---|
| `baseline` | 1.0 | 420 dpi | — | control |
| `elder_text_heavy` | 1.4 | 420 dpi | — | text reflow |
| `elder_zoom_heavy` | 1.0 | 480 dpi | — | element inflation |
| `elder_combo_mid` | 1.5 | 480 dpi | — | second geometry point |
| `elder_combo_max` | 1.6 | 520 dpi | — | compounded worst case |
| `colorblind_deuteranomaly` | 1.0 | 420 dpi | deuteranomaly | colour only |

An RTL-mirroring arm was collected and **dropped**: measurement showed 0% actual
mirroring across every screen even with the setting correctly applied, so reporting it as
an RTL condition would have been false. The colour filter is applied in software to the
PNG, because `adb screencap` reads display buffers *before* Android's hardware
daltonizer would touch them.

## Limitations (read before citing)

- **Ceiling effects.** Most models exceed 95% baseline accuracy, so per-model tests have
  very few discordant pairs. Of 85 per-model tests, 60 are flagged ceiling-limited and 5
  floor-limited. A null result there means low power, not robustness.
- **Survivorship in the compound profiles.** The paired analysis is restricted to targets
  present in both layouts. That is model-independent but *not* profile-independent:
  survival is post-treatment, and the evicted targets are the hard ones. Under
  `elder_combo_max`, dropped targets average 52 characters versus 12 for kept ones. Its
  effect is therefore measured on the easiest surviving subset, and must be reported with
  that caveat rather than as a clean estimate.
- **The model count is not the independent-sample count.** Several of the 17 result files
  are configurations or routes of one base model — roughly 11 independent systems. The
  descriptive sign test in particular treats them as independent and overstates itself.
- **Clustering.** The pooled test clusters on target, but targets also nest within
  screens (~13 per screenshot), so effective n is below nominal.
- **Content drift.** Two screens (`maps`, `play_store`) render live content that can
  change between the opening and closing capture of a screen. `maps` measured 40% drift
  in this run.

## Dataset provenance and licensing

The code, labels, analysis and documentation in this repository are MIT-licensed
([`LICENSE`](LICENSE)).

**The screenshots are not ours to license.** They capture Android and Google's
first-party applications on a Pixel 6 emulator; those interfaces are the property of
Google LLC and its licensors, and are included as measurement stimuli under a
research-use rationale, as with RICO and Android-in-the-Wild. No affiliation or
endorsement is implied.

**The dataset is not free of personal data, and this README will not pretend otherwise.**
The author's own first name is legible in the `contacts_*.png` captures, included with
consent. It is not used as a benchmark target and appears in no prompt, label file, or
result CSV. The `gmail` screen was **removed** from the default dataset because its
targets were real message subjects, senders and timestamps from a live account — both a
disclosure problem and a reproducibility one, since that text cannot reproduce across
collections the way a static app's UI text can.

The screen remains fully supported for anyone collecting on their own account:
`agb collect --screens gmail` works, and the exclusion is enforced by a test so it cannot
silently drift back. **Its absence is a privacy decision, not a missing feature** — and
anyone who re-enables it inherits the same caveat.

**One model carries a usage restriction.** The optional local Ferret-UI baseline inherits
**CC BY-NC 4.0, research use only**, from Apple's upstream Ferret, plus the Meta Llama 3
Community License on its base weights. Running the benchmark and publishing the numbers
is research use and therefore permitted, with attribution (arXiv:2404.05719); commercial
use is not. No other model in the roster is affected — the rest run over hosted APIs.

Third-party dependencies, redistributed fonts, and the full Ferret-UI / Llama 3 licence
chain are documented in [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

## Citing

See [`CITATION.cff`](CITATION.cff), or use GitHub's "Cite this repository" control.

## Documentation

- [`docs/methods.md`](docs/methods.md) — formulas, estimands, and interpretation limits
- [`docs/setup.md`](docs/setup.md) — installation, environment variables, emulator
  preparation, and coordinate-space guidance
- [`docs/cli-reference.md`](docs/cli-reference.md) — complete `agb` command reference
- [`docs/ui.md`](docs/ui.md) — local web UI: install, tour, dataset picker,
  bring-your-own-model, and how it maps to the CLI
- [`docs/collection.md`](docs/collection.md) — Android emulator collection reference:
  workflow, artifacts, validation, and recovery
- [`docs/runbooks/collection.md`](docs/runbooks/collection.md) — live collection operator
  checklist and stop/recovery actions
- [`docs/runbooks/evaluation.md`](docs/runbooks/evaluation.md) — evaluating existing
  captures, prompt modes, coordinate checks, and reporting
- [`docs/ferret-ui.md`](docs/ferret-ui.md) — optional local Ferret-UI server, and its
  licence terms
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — common failures and remedies
