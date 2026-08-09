# METHODS

The mathematics behind AccessGroundBench's three evaluation modes, in one place. Each
mode asks a different question of the same underlying data, and two of them have
validity constraints that are invisible from the CSV output alone. This document states,
per mode: the estimand, the unit of analysis, which formulas apply, a worked example,
and — just as important — what the mode cannot tell you.

The three modes:

1. **Vision-only** (`USE_A11Y_TREE=false`) — does an accessibility profile change a
   VLM's grounding accuracy?
2. **Tree-injected** (`USE_A11Y_TREE=true`) — the same question, with a partial
   accessibility tree given to the model alongside the image.
3. **Cross-file comparison** (`agb analyze --compare-a --compare-b`) — a direct
   comparison between any two result files, most often used to compare mode 1 against
   mode 2.

All formulas below are implemented in `evaluation.grounding.scoring` and the `analysis` package.
Every number in the worked examples is regenerated from
`dataset/experiment_2/` at the time this document is written, not copied from elsewhere.

---

## 0. Symbol table

| Symbol | Meaning |
|---|---|
| *a* | both baseline and comparison arm scored a hit (concordant pass) |
| *b* | baseline hit, comparison arm miss ("broke it") |
| *c* | baseline miss, comparison arm hit ("recovered" / "helped") |
| *d* | both arms missed (concordant fail) |
| *n* | total paired observations, *n = a+b+c+d* unless stated otherwise |
| *b+c* | discordant pairs — the only pairs a McNemar-family test can use |
| α | significance threshold, 0.05 throughout |
| *p̂* | observed proportion (accuracy) |
| *T* | the pooled permutation test statistic |

---

## 1. Shared foundations

Everything in this section is common machinery. Each mode below states which parts of it
apply.

### 1.1 Ground truth and the hit test

For a target with ground-truth box `[x_min, y_min, x_max, y_max]` and a baseline box
`baseline_box`, a predicted point `(x_pred, y_pred)` scores a hit when it falls within the
**baseline** box's width and height (not the current, possibly reflowed, box), centred on
the current box's centre, expanded by a ±30 px touch tolerance
(`evaluation.grounding.scoring.TOLERANCE = 30`):

```
w = (baseline_x_max - baseline_x_min) + 2·TOLERANCE
h = (baseline_y_max - baseline_y_min) + 2·TOLERANCE
cx, cy = centre of the CURRENT box
hit  iff  |x_pred - cx| ≤ w/2  and  |y_pred - cy| ≤ h/2
```

Using the baseline's *size* but the current profile's *centre* holds scoring strictness
constant across profiles: an element that visually inflates under `elder_zoom_heavy`
does not become an easier target just because it is bigger on screen.

### 1.1.1 Coordinate space, and what `raw_response` means

`x_pred, y_pred` are always absolute pixels in the cropped image's space. Getting there
depends on the model, because several families (Gemini, Qwen-VL, GLM-V) answer on a
**0–1000 normalized grid** regardless of the real image size. Those models are recognised
by `evaluation.providers.config.uses_normalized_coords`, prompted on
the scale they already use, and their reply is converted by
`evaluation.grounding.scoring.to_pixel_space`:

```
x_pred = int( round_1dp( x_reply / 1000 · img_width  ) )
y_pred = int( round_1dp( y_reply / 1000 · img_height ) )
```

The `round_1dp` step is load-bearing and not cosmetic. Conversion originally happened
inside the provider layer, which formatted its output as `f"[{cx:.1f}, {cy:.1f}]"` before the
runner truncated with `int()`. Removing the intermediate rounding shifts `x_pred`/`y_pred`
by one pixel for **267 of the 3003** possible integer replies across this dataset's three
image dimensions (1080×2177, 1080×2196, 1080×2219) — ~4% per axis — and since
`score = hit_test(x_pred, …)`, a one-pixel shift can flip a score at a box edge. Keeping
the quantization means every already-collected row reproduces exactly;
the `ToPixelSpaceTests` regression coverage pins it over the full input space.

Conversion is decided **per reply, not per model**. A normalized-convention model can
still answer a given query in pixel space, and
`evaluation.providers.coord_prompting.classify_normalized_reply`
records which happened in the `coord_space` column:

| `coord_space` | meaning | converted? |
|---|---|---|
| `normalized` | reply within 0–1000; taken as grid coordinates | yes |
| `pixel` | a value exceeded 1000, so it cannot be normalized; retried once with a stricter prompt, then recorded as-is | no |
| `unverified` | no coordinate pair could be parsed | no |
| *(blank)* | model was never on the normalized path | no |

> **Non-comparability note (`CLAUDE.md` §9).** `raw_response` holds the model's **verbatim**
> reply only for rows collected **after** the coordinate-mechanism unification (merged
> 2026-08-08). Gemini rows collected before it store the *already-converted pixel value*,
> so the original 0–1000 answer is unrecoverable for those rows and `agb rescore`
> cannot re-derive them offline. Their `x_pred`/`y_pred`/`score` remain correct and
> authoritative — this is a limit on re-analysis, not on validity. The 12 `unverified`
> rows in `gemini-pro-agent` (both arms) are the only rows in that set that were never
> converted at all.
>
> A pixel-space reply whose values happen to fall inside 0–1000 (roughly the top-left 45%
> of these screens) is indistinguishable from a genuinely normalized one from the text
> alone. The compliance retry reduces but does not eliminate this; it is a stated
> limitation of the measurement, not a defect.

### 1.2 Row status

Every evaluated row carries one of three statuses
(`evaluation.storage.results`):

| Status | Meaning | Carries a score? |
|---|---|---|
| `co_present` | target exists in both the baseline and the comparison layout; the model was queried | Yes |
| `off_screen` | target absent from the comparison layout; the model was **never queried** | No — empty |
| `api_error` | the provider call failed | No — retried on resume |

This split exists because an earlier revision scored `off_screen` targets as misses
without querying the model, which counted "the element left the screen" as "the model
looked in the wrong place" — a confound that inflated significant results from 4 tests to
24. All grounding statistics below operate on `co_present` rows only.

### 1.2.1 Cross-profile comparability of the co-present set

**Across models the sample is identical.** `off_screen` is decided by
`evaluation.grounding.targets.find_element_in_profile`, which reads only the captured
label JSON — no model is involved. In `dataset/experiment_2/` all 7 models carry
exactly 865 `co_present` and 140 `off_screen` rows with the same per-profile split, so
the pooled and per-model tests share one sample. Per-model `n` can only diverge through
`api_error`, of which the archive has none.

**Across profiles it is not.** Survival into a profile is a *post-treatment* variable,
so restricting to `co_present` conditions on an outcome of the manipulation. The
targets evicted are systematically the ones the models were already worst at:

| Profile | n kept | baseline acc (kept) | n dropped | baseline acc (dropped) | mean text length kept → dropped |
|---|---:|---:|---:|---:|---|
| `elder_text_heavy` | 146 | 81.2% | 19 | 68.4% | 22 → 53 chars |
| `elder_zoom_heavy` | 151 | 81.1% | 17 | 69.7% | 23 → 48 chars |
| `elder_combo_max` | 112 | 85.3% | 56 | 69.1% | 12 → 52 chars |
| `colorblind_deuteranomaly` | 162 | 81.0% | 6 | 50.0% | 26 → 21 chars |

Kept + dropped is 168 on every row except `elder_text_heavy`, which sums to 165: the
`photos_elder_text_heavy` capture is missing from the archive entirely, so that
screen's 3 targets generated no rows at all in that profile. Going forward
`collection.artifacts.manifest.write_manifest` exits non-zero on exactly this
kind of gap.

The mechanism is that harsher layouts evict long text first, and long text is what
grounding fails on. Because the pairing is within-target, this moves the **baseline arm
itself**: the same model reports a different baseline accuracy depending on which
profile it is being compared against.

| Model | all 168 | `elder_text_heavy` | `elder_zoom_heavy` | `elder_combo_max` |
|---|---:|---:|---:|---:|
| `gpt-5.4` | 51.2% | 53.4% | 53.0% | 67.9% |
| `gpt-5.6-luna` | 94.6% | 96.6% | 96.0% | 99.1% |
| `gpt-5.5` | 98.2% | 97.9% | 98.0% | 99.1% |

**Consequence for interpretation.** A profile's grounding result estimates the effect
*on the targets that survive that profile*, not on the original 168. Pooled p-values
and effect sizes are therefore comparable **across models but not across profiles**.
`elder_combo_max` is the case that matters: it discards 56 of 168 targets, its null
grounding result (pooled p = 0.313) is measured on the 112 easiest, and the `ceiling`
flags it earns are partly produced by the exclusion rather than observed. Its real
finding lives in reachability (§2), which is computed over all 168 baseline targets and
is unaffected by this bias.

This is a known, accepted limitation rather than a defect: correcting it would require
either scoring `off_screen` as failure — reintroducing the confound above — or
restricting every profile to the 109 targets present in all of them, which changes the
estimand. Neither is done; the bias is reported instead.

### 1.2.2 Target-validity filter

A harvested candidate is a valid target only if it is the one string a user would
actually see and tap. Two shapes fail that test, both from Android accessibility
narration crushing a whole UI row into a single `text` attribute:

- **Length.** A target's text exceeds `MAX_TARGET_CHARS` (100 characters).
- **Containment.** A target's box fully encloses another target's box on the same
  screen — the container is the parent of the target it should not compete with.

Both are the shape of Gmail's `viewified_conversation_item_view` row nodes: one
`ViewGroup` carries a synthesized string concatenating sender, subject, and the full
(untruncated) preview body, and encloses its own sender/subject/preview children —
which are already separate, individually-visible targets. Asking a model to locate that
concatenation is not asking it to find a rendered label.

`evaluation.grounding.targets.invalid_targets` applies this filter at harvest time, before any
target is queried: `harvest_targets` never returns an invalid candidate, so no CSV row
and no API call exists for it. This is a sample-*definition* rule, not a post-hoc
statistical correction — it removes targets that were never valid instances of the
grounding task, the same category of decision as requiring baseline-unique text.

`analysis.data.samples.compute_b2_targets` recomputes the identical rule
from a completed
CSV's `co_present` rows. It exists for datasets collected before the harvest-time filter
did (`dataset/experiment_2`, and any hosted-model CSV collected before this change),
where the invalid rows are already on disk and must be filtered out after the fact
rather than never generated. On a fresh collection the two should agree exactly; where
they diverge, it means the CSV predates this filter.

Effect on the current (non-archived) dataset: 7 of gmail's 23 harvested candidates are
excluded (162 → 155 targets across all 13 screens), all by the length rule; none of
gmail's other targets enclose one another, so the containment rule contributes nothing
on this dataset (it exists for a shape the length rule alone would not catch — a short
container label enclosing a target with equally short text, e.g. two overlapping icons).

### 1.3 The 2×2 contingency table

For a set of paired (baseline, comparison) scores,
`analysis.reports.grounding.compute_contingency` counts:

|  | Comparison PASS | Comparison FAIL |
|---|---:|---:|
| **Baseline PASS** | *a* | *b* |
| **Baseline FAIL** | *c* | *d* |

### 1.4 McNemar's test and test selection

McNemar's test asks whether the discordant pairs favour one direction — whether *b* and
*c* differ from what a fair coin would produce.
`analysis.stats.mcnemar_test`
picks the variant by discordant count:

- **n = b+c < 25** — exact two-tailed binomial: discordant pairs ~ Binomial(*n*, 0.5).
  ```
  p = 2 · P(X ≥ max(b, c))    where X ~ Binomial(n, 0.5)
  ```
  Implemented via `scipy.stats.binomtest`.
- **n ≥ 25** — asymptotic χ² with Edwards' continuity correction:
  ```
  χ² = (|b - c| - 1)² / n         p = 1 - CDF_χ²,df=1(χ²)
  ```

The threshold (`ASYMPTOTIC_THRESHOLD = 25`) is unchanged from the original benchmark
design.

**The exact test's hard floor.** The smallest achievable two-tailed exact-binomial
p-value is `2 · 0.5ⁿ` (all discordant pairs in one direction, i.e. `c = 0`). This matters
directly for Section 2: `n = 10` gives `p = 0.00195`, still short of the worked example's
rank-1-of-28 Holm threshold of `0.00179` (§2); `n = 11` gives `p = 0.00098`, which clears
it. So on a 28-test family at this stringency, a per-model comparison needs **at least 11
discordant pairs, all in one direction**, before Holm correction can call it significant
at all — regardless of how lopsided the model's actual behaviour is below that count.

### 1.5 Holm–Bonferroni correction

`analysis.stats.holm_bonferroni` corrects a family of *m* tests: sort
p-values ascending, test rank *i* (0-indexed) against `α / (m - i)`, and stop rejecting
at the first failure — every later (larger) p-value is retained regardless of its own
value. Chosen over plain Bonferroni because it is uniformly more powerful at the same
family-wise error rate, and over Benjamini–Hochberg because it needs no independence
assumption — these tests share underlying data (the same targets, screens, and baseline
arm).

### 1.6 Confidence intervals

**Wilson score interval** (`analysis.stats.wilson_interval`) — for a single
proportion *k/n*:

```
z = Φ⁻¹(1 - α/2)
centre    = (p̂ + z²/2n) / (1 + z²/n)
halfwidth = (z / (1 + z²/n)) · √(p̂(1-p̂)/n + z²/4n²)
```

Used for reachability (§1.9) and any other single-proportion report. Preferred over the
Wald interval `p̂ ± z√(p̂(1-p̂)/n)` because Wald can run outside [0, 1] and has poor
coverage near the boundary — exactly where this benchmark sits, with baseline
accuracies of 88–99%.

**Newcombe method-10 interval**
(`analysis.stats.paired_difference_interval`) —
for the *difference* between two proportions computed on the **same** paired sample
(baseline accuracy − comparison accuracy). An ordinary two-sample interval assumes
independence; these two arms share every target, so their outcomes are correlated and an
unpaired interval would overstate the uncertainty. Newcombe combines each arm's own
Wilson interval with the observed correlation *φ* across the 2×2 table:

```
p1 = (a+b)/n,  p2 = (a+c)/n,  diff = p1 - p2
φ  = (ad - bc) / √((a+b)(c+d)(a+c)(b+d))
[l1,u1] = Wilson(a+b, n),  [l2,u2] = Wilson(a+c, n)
lower = diff - √((p1-l1)² - 2φ(p1-l1)(u2-p2) + (u2-p2)²)
upper = diff + √((u1-p1)² - 2φ(u1-p1)(p2-l2) + (p2-l2)²)
```

### 1.7 Conditional odds ratio

`analysis.stats.conditional_odds_ratio` reports the size of an effect,
since a
p-value alone says only that one exists:

```
OR = b / c
```

with an exact interval obtained by treating *b* as Binomial(*n*, *p*), taking the
Clopper–Pearson interval for *p* via the Beta distribution, and transforming through
`OR = p/(1-p)`. `OR = 2` means a target was twice as likely to break as to recover.
`c = 0` gives `OR = ∞`, which is the correct value, not an error — the informative part
of that result is the interval's finite *lower* bound.

### 1.8 The cluster permutation test

`analysis.stats.cluster_permutation_test` is the primary grounding test in
mode 1 (and, once tree data exists, mode 2). It pools every model's paired outcome for a
given profile into one test.

**Statistic.** For each target (a `(screen, target_text)` cluster), sum
`baseline_score − comparison_score` across every model that produced a `co_present` pair
for that target. Sum those cluster totals into `T`.

**Null distribution.** Under H0 the baseline/comparison label is exchangeable *per
target*. Build the null by, 20,000 times (`DEFAULT_PERMUTATIONS`), independently flipping
the sign of each cluster's contribution and recomputing `T`. The reported p-value is

```
p = (#{|T_null| ≥ |T_observed|} + 1) / (n_permutations + 1)
```

— the `+1` in both numerator and denominator accounts for the observed labelling being
itself one of the equally likely permutations, so p can never be exactly 0.

**Why clustering, not per-model independence.** The same ~13 targets per screen are
reused across every model, so a target's outcome under model A and under model B are
correlated — an intrinsically hard target is hard for everyone. Flipping *whole target
clusters* (every model's outcome for that target, together) preserves that correlation.
Pooling naively into one large McNemar table would instead treat 7 correlated
observations as 7 independent ones and manufacture confidence that isn't there.

**Why pooling is necessary, not optional.** Per §1.4, an exact-binomial test needs ≥ 11
one-directional discordant pairs to clear a Holm threshold across ~28 tests. Several
per-model, per-profile cells have far fewer — one has `b=0, c=0`. Those comparisons
cannot reach significance *by construction*, regardless of what the model does. Pooling
supplies enough discordant observations for the question to be answerable at all.

**Estimand, precisely.** This tests whether a profile degrades grounding *averaged over
the models evaluated*. It is not a claim about any individual model — that is §1.4's job,
run per model by `analysis.reports.grounding.report_per_model`.

### 1.9 Floor and ceiling power flags

`analysis.reports.grounding.power_flag` marks a per-model comparison as uninformative
in either direction:

- **`floor`** — baseline accuracy < 50% (`FLOOR_ACC_THRESHOLD`). Most targets already
  fail before any profile is applied, so only `a+b` of them could ever register as
  "broken" — the test is starved of material to detect degradation in.
- **`ceiling`** — baseline accuracy > 95% (`CEILING_ACC_THRESHOLD`). Almost nothing is
  left to break, so a null result means *underpowered*, not *resilient*. This mirrors the
  floor flag at the opposite end of the accuracy scale.

A flagged comparison's p-value is real, but its non-significance must not be reported as
evidence of anything.

---

## 2. Mode 1 — Vision-only

**Trigger:** `USE_A11Y_TREE=false` (the default). Evaluated via
`agb evaluate` → `evaluation.runner.evaluate_screen` with
`use_a11y_tree=False`,
prompting with `PROMPT_TEMPLATE` (image only). Results land in
`dataset/evaluation_results_{model}.csv`. Analysed with `agb analyze`.

**Estimand:** does an accessibility profile change a vision-only VLM's grounding
accuracy, relative to that same model's baseline?

**`PROMPT_TEMPLATE_WITH_TREE`'s wording was harmonized to `PROMPT_TEMPLATE` on
2026-07-29**, as part of the tree-mode remediation. It used to read "central **(x, y)
pixel** coordinates" against `PROMPT_TEMPLATE`'s "central **pixel (x, y)** coordinates" —
a word-order difference that meant a vision-vs-tree comparison varied two things (tree
presence *and* wording) instead of one. Both templates now share the identical sentence
(`evaluation.grounding.task_prompting`). This is **mode 1's** `PROMPT_TEMPLATE`, unchanged by the
fix — the vision-only wording used for `dataset/experiment_2/` is byte-identical to what
mode 1 sends today, so that archive stays comparable. It matters only for mode 2, noted
in §3.

**Unit of analysis:** one paired observation is `(screen, target_text, model)` → a
`co_present` (baseline_score, profile_score) pair. Reachability (§1.9-adjacent, really
its own metric) is computed once per profile from a single model's label files, since it
depends only on the capture, not on any model's answer.

**Formulas applied — all of them.** This is the mode the analysis pipeline was built for.

| Analysis report section | What it reports |
|---|---|
| §1 Reachability | Wilson interval on targets-present / targets-total |
| §2 Pooled permutation (**primary**) | §1.8 above, per profile |
| §3 Per-model McNemar (secondary) | §1.4 + §1.5 + §1.6 + §1.7 + §1.9, per model × profile |
| §4 Sign test (descriptive) | direction consistency across models — see below |

**The sign test** (`analysis.stats.sign_test`) counts, per profile, how many
models' per-model McNemar favoured degradation (`b > c`) versus improvement (`c > b`),
and runs an exact binomial on that count. It is explicitly **descriptive, not
inferential**: the 7 evaluated models are not a random sample of "all VLMs," so this
cannot license a population-level claim. Its purpose is narrower — showing that a pooled
effect is not one model dragging the average.

### Worked example (regenerated from `dataset/experiment_2/`)

**Reachability**, `elder_text_heavy`: 146/165 targets present, 88.5% [82.7%, 92.5%].

**Pooled permutation (primary)**, `elder_text_heavy`, pooling all 7 models:

```
146 target clusters, 1022 total co-present observations
b = 61 (degraded), c = 13 (improved)
T = 48,  p = 0.00005,  Holm threshold at this rank = 0.01250
-> SIGNIFICANT (degradation)
```

The other three profiles are not significant after correction — `elder_zoom_heavy`
(b=37, c=54, p=0.172, trending *toward improvement*), `elder_combo_max` (b=44, c=33,
p=0.313), `colorblind_deuteranomaly` (b=22, c=29, p=0.395).

**Per-model McNemar (secondary)**, `9router_cx_gpt-5.4-mini` / `elder_text_heavy` —
the only per-model cell that survives Holm correction across the 28-test family:

```
a=38  b=14  c=1  d=93   n=146   n_discordant=15
Baseline acc 35.6%   Experimental acc 26.7%
Test: Exact Binomial (n=15)   p = 0.000977
Holm threshold (rank 1 of 28) = 0.001786   -> SIGNIFICANT
Risk difference: 0.0890  [0.0390, 0.1395]      (Newcombe)
Odds ratio:      14.000  [2.130, 591.968]      (b/c, exact interval)
Power flag: floor (baseline 35.6% < 50%)
```

Read together: `gpt-5.4-mini` is the only model whose *individual* result clears
correction — but it is also flagged `floor`, so its baseline was already failing most
targets before any distortion. Every strong model in this dataset is flagged `ceiling`
instead: `gpt-5.5` and `9router/cx/gpt-5.6-sol` sit at 97–99% baseline on co-present
targets, where per-model McNemar has almost nothing left to detect. The pooled test in
§1.8 exists precisely because those per-model cells cannot answer the question alone.

### What mode 1 cannot tell you

- Nothing about whether an accessibility tree would help — that requires mode 2 or 3.
- A per-model verdict of "ns" or a `ceiling`/`floor` flag is not evidence that model is
  resilient or broken; it states the comparison lacked material to detect an effect.
- The pooled test's estimand is an average over the 7 evaluated models. It does not
  license a claim about any specific model, or about VLMs in general beyond this sample.
- Profiles cannot be ranked against one another by p-value or effect size. Each is
  estimated on its own surviving target set (§1.2.1), and the harsher the profile the
  easier that set becomes. Reachability and grounding must be read together, never as
  independent verdicts on the same profile.

---

## 3. Mode 2 — Tree-injected

**Trigger:** `USE_A11Y_TREE=true`. Same runner, `use_a11y_tree=True`. For hosted
(vision-API) models, prompting with `PROMPT_TEMPLATE_WITH_TREE`, which appends a partial
accessibility tree (`evaluation.grounding.task_prompting.build_tree_text`) to the
prompt: each visible element's best label
and pixel bounds, `[x1,y1][x2,y2]`, absolute screenshot pixels. Results land in
`dataset/evaluation_results_{model}_with_tree.csv`
(`evaluation.config.get_results_csv`). Analysed by pointing
`agb analyze` at the `_with_tree` files — either explicitly
via `--csv`, or via `--mode tree` when discovering from `--data-dir` (see "Analysis file
discovery" below).

**Estimand:** the same question as mode 1 — does the profile change grounding accuracy —
for a model that additionally receives a partial accessibility tree. Mode 2 alone does
**not** test whether the tree *helps*; that comparison is mode 3's job.

**Unit of analysis:** identical to mode 1 — `(screen, target_text, model)` pairs,
`co_present` only.

**Formulas applied:** identical machinery to mode 1 — §1's reachability, pooled
permutation, per-model McNemar, and sign test all apply unchanged, run against the
`_with_tree` CSVs.

### Analysis file discovery: vision and tree results are never pooled automatically

`analysis.data.results.discover_result_csvs` globs
`evaluation_results_*.csv` under `--data-dir` and
**excludes** anything ending in `_with_tree` unless `--mode tree` is passed. Before this
was added, the glob matched both suffixes, and `model_name_from_path` turned
`evaluation_results_local_ferret-ui-llama8b_with_tree.csv` into a distinct model id
(`local_ferret-ui-llama8b_with_tree`) rather than recognising it as the same model's
second arm. A default run after any tree collection would have fed both arms of the same
model into §2's pooled cluster permutation test and §1.5's Holm family as if they were
two independent models — but vision and tree rows for the same model, same targets, are
maximally correlated, not independent measurements. Concretely: the sign test's "7/7
models down" (§2 worked example) would silently become "14/14" with zero new evidence,
and the per-model Holm family would grow from 28 tests to 56, both without a single new
observation. Every CSV row now also carries its own `prompt_mode` column
(`vision`/`tree`; `evaluation.storage.results`) as a second line of defence, and
`analysis.data.results.load_results` defaults it to `vision` for archived CSVs that
predate the column, so `dataset/experiment_2/`'s regression reproduction (CLAUDE.md §9)
is unaffected.

This does not remove the ability to compare arms — `run_cross_comparison` (mode 3, §4
below) takes explicit file paths and is unaffected by the default glob; it remains the
intended way to compare a model's vision-only CSV against its `_with_tree` counterpart.

### The target must be withheld from its own tree entry

`evaluation.grounding.task_prompting.build_tree_text(profile_labels,
exclude_text=target_text)` removes the target's own row
from the injected tree before the prompt is built, so the model cannot simply read the
answer's coordinates off the tree — it must still locate the element from the image, using
the tree only as spatial context for neighbouring elements.

**A leak existed in this exclusion and has been fixed.** The tree renders each element's
label via a fallback chain (`text` → `content_desc` → `resource_id` → `class`), but the
exclusion previously checked only `text`. A node with empty `text` and
`content_desc == target_text` still rendered the target's name — with its bounding box —
because the fallback wasn't consulted for the exclusion check, only for the label itself.
Measured on `dataset/experiment_2/labels`: **22 of 168 targets (13.1%)** leaked this way,
typically a parent tab container whose bounds enclose the ground-truth box closely enough
to score a hit under the ±30 px tolerance:

```
clock / 'World Clock'   leaked node  [216,2051][432,2219]  centre (324, 2135)
                         true target [221,2162][426,2202]  centre (324, 2182)
                         -> within tolerance: a hit sourced from the tree, not the image
```

The fix computes the rendered label first and excludes on *that*, matching what is
actually printed. Re-measured with the same method after the fix: **0/168 (0.0%)**.
Regression-tested by the runner cases
`test_excludes_target_reached_only_via_content_desc_fallback` and
`test_excludes_target_reached_only_via_resource_id_fallback`). No tree-mode data existed
before this fix landed, so nothing collected so far is contaminated by it.

### Reachability is not an independent finding in this mode

`off_screen` status is decided by `find_element_in_profile` against the profile's label
file, **before** `build_tree_text` or any prompt is constructed. The tree cannot change
whether a target's node exists in a given profile's XML. Consequently mode 2's
reachability table will be numerically identical to mode 1's for the same profile set —
report it once, not as corroborating evidence from a second, independent measurement.

### Per-model tree rendering: Ferret-UI required a native format, not the vision-model one

`local/ferret-ui-llama8b` does not receive `PROMPT_TEMPLATE_WITH_TREE`'s rendered string.
The provider facade delegates this model to
`evaluation.providers.ferret.call_ferret`, which renders its native
prompt regardless of mode (see mode 1 for why — Ferret is fine-tuned on a fixed
single-line grounding instruction, and the generic zero-shot prompt causes it to just
repeat the target text back). Until 2026-07-29
this rewrite **replaced the prompt outright**: the regex anchor it matched on
(`click on the text element:`) also appears inside `PROMPT_TEMPLATE_WITH_TREE`, so the
substitution fired in tree mode too, discarding the entire injected tree. Vision mode and
tree mode sent **byte-identical input** to Ferret, while still being written to two
differently-named CSVs and treated as separate experimental conditions. No tree-mode data
was ever collected before this was caught, so nothing is contaminated by it — but the bug
would have been invisible in the results themselves (both arms would simply show
whatever vision-only grounding looked like) rather than raising an error.

The fix (`evaluation.providers.ferret.build_ferret_prompt`) augments
instead of replacing, and renders
the tree in Ferret's own input convention rather than the hosted-model one:

- **Scale:** Ferret-UI's `model_UI.py` box-coordinate conversion reads an input box after multiplying by
  `VOCAB_IMAGE_W / image_w` (`VOCAB_IMAGE_W = VOCAB_IMAGE_H = 1000`;
  `ferret_ui/model_UI.py`), and the `ferret_llama_3` system prompt in
  `ferret_ui/conversation.py` tells the model "Image size: 1000x1000"
  unconditionally. A tree rendered in absolute screenshot pixels — what
  `PROMPT_TEMPLATE_WITH_TREE` sends hosted models — is out of distribution for Ferret:
  e.g. a pixel y of 2000 on a 2274px screenshot would be read as roughly twice the image
  height. `build_ferret_prompt` scales every box the same way Ferret's own code does
  (`int()`-truncated, not rounded, matching `model_UI.py`'s conversion exactly).
- **Format:** single bracket, comma-space (`[x1, y1, x2, y2]`), matching
  `model_UI.py`'s own formatting — not the hosted-model tree's `[x1,y1][x2,y2]`
  double-bracket-pair shape.
- **Order:** tree block first, the unchanged fine-tuned grounding line
  (`Provide the bounding box of the text '{target}'.`) always last, since Ferret's
  fine-tuning expects the instruction to be the final thing it reads.
- **No "image is W×H pixels" sentence** for Ferret — it would contradict the system
  prompt's fixed "Image size: 1000x1000".

**Token budget.** Ferret is Llama-3-8B, `max_position_embeddings=8192`
(`ferret_ui/config.json`). The image alone costs 2,304 tokens for every capture in this
dataset (CLIP-ViT-L/14-336 `anyres`, base tile + a 1×3 grid — every screenshot's aspect
ratio selects the same pinpoint, so this is constant across profiles). Measured against
the real Llama-3 tokenizer over all 77 archived label files, the worst-case tree
(gmail, 100 rows) is 2,299 tokens; worst-case total is 5,744 of 8,192 — 30% headroom.
`ferret_server.py`'s `check_token_budget` enforces this server-side (where the tokenizer
already lives; `transformers` is intentionally not installed in the main `.venv` per §
"Ferret-UI needs a different prompt" in `CLAUDE.md`) and **raises rather than truncates**
if a future capture would overflow it — truncating the tree would change the
experimental condition being measured, which is worse than failing loudly. Accessibility
profiles generally *shrink* trees (fewer elements fit at larger font/density — gmail's
`elder_combo_max` tree is 924 tokens, 60% below its own baseline), so re-collection is
expected to stay well inside budget; a screen would need to roughly double its element
count to breach it.

The leak-fix exclusion (`evaluation.grounding.task_prompting.collect_tree_rows`,
formerly folded into `build_tree_text`) is
shared by both renderings: the hosted-model pixel format and Ferret's 0-1000 format are
built from the same excluded row list, so the fix documented above holds for Ferret's
prompt too, not just the hosted-model one. The provider regression case
`test_build_ferret_prompt_excludes_target_row` covers this, since the tree runner tests
mock `call_vlm` at the runner boundary and therefore
never observed what the wire format actually was for Ferret — the gap that let the
discard bug go unnoticed for as long as it did.

### Illustrative worked example

No tree-mode evaluation has been run yet — `dataset/` contains no `*_with_tree.csv`
files. The numbers below are a small **synthetic illustration** of the pooled-permutation
mechanics (§1.8), clearly not benchmark data, to show the shape of a mode-2 report before
real data exists:

```
Illustrative only -- 3 targets, 2 models, elder_text_heavy
cluster A: model1 (1,0) model2 (1,0)     both models degrade on A
cluster B: model1 (1,1) model2 (1,1)     both models hold on B
cluster C: model1 (0,1) model2 (0,0)     mixed outcome on C

cluster_permutation_test({...}, n_permutations=2000, seed=0) ->
  statistic=1.0  b=2  c=1  n_clusters=3  n_observations=6  p_value=1.0
```

This block exists only to mark the report shape; it is deliberately not styled as a
result and must not be cited as one.

### What mode 2 cannot tell you

- **Whether the tree helps.** A significant degradation under mode 2 does not mean the
  tree failed to help — without a comparison against mode 1 on the same targets, there is
  no baseline for "how bad would this have been without the tree." That comparison is
  mode 3.
- Anything about reachability beyond what mode 1 already reports (see above).
- Whether format compliance (the tree changes the expected reply format) rather than
  grounding difficulty drives any observed difference from mode 1 — the two are
  confounded unless tested via the per-target change scores described in §4.

---

## 4. Mode 3 — Cross-file comparison

**Trigger:** `agb analyze --compare-a <fileA> --compare-b <fileB>`, which calls
`analysis.reports.comparison.run_cross_comparison`. Designed for, but not limited
to, comparing a mode-1 CSV against a mode-2 CSV for the same model.

**Estimand, as currently implemented:** for a **given profile**, and for targets present
and `co_present` in both files, is file B's score different from file A's score? This is
answered independently per profile with a plain McNemar test — it is *not* a comparison
against baseline within this mode, and it is *not* a test of whether B protects against a
profile's degradation (see below).

**Unit of analysis:** one paired observation is a `(screen, target_text)` key that is
`co_present` in *both* files for the *same* profile. File A's score and file B's score for
that key form the pair — contrast this with modes 1–2, where the pair is
(baseline, profile) *within* one file.

```
a = both files hit        b = A hit, B missed ("B hurt")
c = A missed, B hit ("B helped")     d = both files missed
```

**Formulas applied — a strict subset of §1.** Only `mcnemar_test` (§1.4) with a flat
`α = 0.05`. Cross-file mode does **not** apply Holm correction across its profile family,
does not compute floor/ceiling flags, and does not compute risk difference or odds ratio.
Output columns (`Tree_Hurt_b`, `Tree_Helped_c` in the CSV header) presume a
vision-vs-tree use case even though the function accepts any two files.

**`baseline` is never compared.** `main()` builds the profile list from
`EXPERIMENTAL_PROFILES`, which excludes `"baseline"`
(`analysis.workflow.EXPERIMENTAL_PROFILES`), and passes that same list into
`run_cross_comparison`. Consequently "does file B differ from file A on the *undistorted*
screen" is never tested by this mode as it stands — only the five experimental profiles
are compared.

### Illustrative worked example

No `_with_tree` file exists yet, so cross-file mode has never been run against real data.
A small **synthetic illustration** of the mechanics:

```
Illustrative only -- elder_text_heavy, file A (vision) vs file B (tree), 20 co-present pairs
a=14 (both hit)  b=2 (A hit, B missed)  c=3 (A missed, B hit)  d=1 (both missed)
mcnemar_test(b=2, c=3) -> Exact Binomial (n=5), p = 1.0  -> ns
```

This illustrates the *shape* of a cross-file report only; it is not a claim about any
real model.

### What mode 3 cannot tell you — and the test it is missing

The question that motivates comparing vision-only against tree-injected results is
usually: **"does the tree protect against a profile's degradation?"** That is an
**interaction** — whether the size of the baseline→profile drop *differs* between the two
conditions (a difference-in-differences design) — and mode 3 as implemented does not test
it.

Running mode 1's McNemar separately on file A and file B, then comparing which came out
significant, is the classic *"the difference between significant and not-significant is
not itself significant"* error: a comparison that is significant in one file and not in
the other has not been shown to differ from that comparison in the other file — the two
p-values were never compared to each other.

**The test this requires** (not implemented — recommended future work): for each target
present and `co_present` under `baseline` and under the profile, in *both* files, form a
per-target vision *and* tree change score,

```
Δ_vision(target) = baseline_score_A - profile_score_A     (mode 1's per-cluster term, §1.8)
Δ_tree(target)   = baseline_score_B - profile_score_B
```

then run the §1.8 cluster permutation machinery on the paired difference
`Δ_vision(target) − Δ_tree(target)` directly, rather than on either arm alone. A nonzero
result there — not a difference between two separately-reported p-values — is what would
license the claim "the tree changes how much this profile degrades grounding." The
existing `cluster_permutation_test` function (§1.8) needs no modification to run this;
only the input construction differs — a straightforward addition once mode 2 has real
data.

---

## 5. Mode comparison at a glance

| | Mode 1: vision-only | Mode 2: tree-injected | Mode 3: cross-file |
|---|---|---|---|
| Pairs | baseline vs. profile, same model | baseline vs. profile, same model, tree given | file A vs. file B, same profile |
| Primary test | pooled cluster permutation | pooled cluster permutation (unrun) | plain McNemar |
| Multiple-comparison correction | Holm, 28-test family | Holm, 28-test family (unrun) | **none** |
| Floor/ceiling flags | yes | yes (unrun) | **no** |
| Effect sizes (risk diff, OR) | yes | yes (unrun) | **no** |
| Reachability | computed | identical to mode 1 — do not double-count | not applicable |
| Tests "does context help"? | no | no | **no — see §4's missing interaction test** |
| Data currently on disk | `dataset/experiment_2/` (archived) | none | none |

---

## 6. File reference

| File | Written by | Contents |
|---|---|---|
| `dataset/evaluation_results_{model}.csv` | mode 1 | raw per-query rows, `status` column |
| `dataset/evaluation_results_{model}_with_tree.csv` | mode 2 | same schema, tree-injected |
| `dataset/reachability_results.csv` | §1 (either mode) | Profile, Present, Total, Reachability, CI |
| `dataset/pooled_permutation_results.csv` | §1.8 (either mode) | Profile, clusters, b, c, p, Holm threshold |
| `dataset/mcnemar_results_per_model.csv` | §1.4+§1.5+§1.6+§1.7+§1.9 | one row per model × profile |
| `dataset/direction_consistency.csv` | sign test | Profile, down, up, tied, p |
| `dataset/mcnemar_compare_{model}.csv` | mode 3 | one row per profile compared |
