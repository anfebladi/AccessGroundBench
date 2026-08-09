# AccessGroundBench — agent run instructions

Run every command from the repository root.

## Environment: already configured, do not change

`.env` is configured and verified with a live test call. It contains a working
`VLM_MODEL` and a funded `OPENROUTER_API_KEY`.

Rules:

- Edit **only** `USE_A11Y_TREE` and `COORD_SPACE` in `.env`, and only where the
  stages below say to.
- Never change `VLM_MODEL`. Never switch providers. Never suggest Ollama, OpenAI,
  Anthropic, or Gemini alternatives.
- `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are unused placeholders. They are
  supposed to look like that. Ignore them.
- On any failure: report the real error and stop. Do **not** change `VLM_MODEL`
  to work around it — that silently benchmarks the wrong model and writes a
  mislabeled CSV.
- Do not run `agb collect`, `agb profile`, `agb capture`, or anything using `adb`.
  There is no emulator; the dataset is already captured.
- `agb evaluate` reads model and experiment settings from `.env`. Its only operational
  flags are `--fresh` and `--force-unlock`; do not pass model or prompt-mode flags.

## Paths

Let `R` = `dataset/evaluation_results_openrouter_qwen_qwen3-vl-235b-a22b-instruct`

So `R.csv` is the vision-only result and `R_with_tree.csv` is the tree-injected one.
If `VLM_MODEL` is ever changed, `R` is `dataset/evaluation_results_` + the model id
with every `/` replaced by `_`.

## Stage 0 — confirm the coordinate convention

Models disagree on how to express a point. Most answer in absolute image pixels;
several (Qwen-VL, Gemini, GLM-V) answer on a 0-1000 grid regardless of image
size. Scoring the wrong one gives **0% accuracy on every row** — not a low score,
an impossible one — and every McNemar row comes back `Inconclusive (floor)`.

If baseline accuracy comes out at or near zero, this is almost certainly why.
Diagnose it from an existing CSV without spending any API calls:

```bash
agb rescore --csv R.csv --check
```

Whichever convention shows materially higher accuracy is the right one. Set
`COORD_SPACE=pixel` or `COORD_SPACE=norm1000` in `.env` accordingly. To repair a
CSV that was already scored wrong (no API calls, writes a `.bak` first):

```bash
agb rescore --csv R.csv --coord-space norm1000
```

The convention belongs to the **model plus the prompt**, not the model alone.
Re-check it whenever `USE_A11Y_TREE` changes: the tree lists real pixel bounds,
which can push a model that normally answers in `norm1000` into answering in
pixels. Observed so far, vision-only:

| Model | Convention |
| --- | --- |
| `openrouter/qwen/qwen3-vl-*` | `norm1000` |
| `openrouter/z-ai/glm-*v*` | `norm1000` |
| `gemini/gemini-3.1-pro-preview` | `norm1000` |
| OpenAI models, Ferret-UI | `pixel` |

Known caveat: with the tree injected, `glm-5v-turbo` answered mostly in pixels
but returned roughly a fifth of responses in `norm1000`, so no single setting
scored that arm correctly. If `--check` shows both conventions scoring
non-trivially, the run has mixed formats — report it rather than picking one.

## Stage 1 — vision-only

Set `USE_A11Y_TREE=false` in `.env`, then:

```bash
agb evaluate
```

~335 rows, several minutes. Do not abort on individual row failures.
On repeated 429s, set `VLM_PACE_SECONDS=1` and rerun.

## Stage 2 — McNemar

```bash
agb analyze --csv R.csv
```

Always pass `--csv`; the bare command reanalyzes every old CSV in `dataset/`.

Read the `Summary for ...` table. Last column is one of:

| Verdict | Meaning |
| --- | --- |
| `SIGNIFICANT` | p < 0.05 |
| `Not Sig.` | p >= 0.05, baseline accuracy >= 50% |
| `Inconclusive (floor)` | p >= 0.05, baseline accuracy < 50% |

Profiles: `elder_text_heavy`, `elder_zoom_heavy`, `elder_combo_max`,
`elder_combo_rtl`, `colorblind_deuteranomaly`.

## Stage 3 — only if at least one profile is SIGNIFICANT

Set `USE_A11Y_TREE=true` in `.env` (leave `VLM_MODEL` alone), then:

```bash
agb evaluate
agb analyze --csv R_with_tree.csv
agb analyze --compare-a R.csv --compare-b R_with_tree.csv
```

Stage 1 output is not overwritten — the tree run writes a separate `_with_tree` file.
Both `--compare-a` and `--compare-b` are required together; that mode ignores `--csv`.

If every profile is `Inconclusive (floor)`: stop. Baseline accuracy is under 50%,
McNemar is underpowered by construction, and the null result means nothing.

If every profile is `Not Sig.` with baseline >= 50%: stop. The model is resilient.

## Report back

Both summary tables verbatim, whether tree injection recovered the degradation,
and the full paths of every CSV written.
