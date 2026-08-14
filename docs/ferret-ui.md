# Local Ferret-UI

Ferret-UI is an optional local VLM for UI grounding. It uses a separate Python
environment because its dependencies conflict with the main project.

## Install and start

```bash
cd ferret_ui
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python download_scripts.py     # fetches the upstream model code -- required
```

`download_scripts.py` downloads seven modules (`builder.py`, `conversation.py`,
`inference.py`, `model_UI.py`, `mm_utils.py`, `clip_encoder.py`, `constants.py`)
from the `jadechoghari/Ferret-UI-Llama8b` repository on Hugging Face into
`ferret_ui/`. They are third-party code and are deliberately **not** committed
here — see [Licensing](#licensing) — so this step is not optional. Without it
`ferret_server.py` fails at import.

Start the HTTP server from the same `ferret_ui` directory:

```bash
start_server.bat                # Windows
python ferret_server.py         # any platform
```

The server listens at `http://localhost:8000/` by default. Leave it running and
wait for `Model loaded successfully!` before starting `agb evaluate`. To choose
a different Hugging Face model, pass `--model_path` when starting the server;
the model is loaded during startup. The default is
`jadechoghari/Ferret-UI-Llama8b`.

Ferret requests use a 1,800-second timeout by default. The evaluator does not
retry a read timeout because the server may still be generating the same reply.
Set `VLM_REQUEST_TIMEOUT_SECONDS` only when you need a different client timeout.

In the main project `.env`, select the local provider:

```dotenv
VLM_MODEL=local/ferret-ui-llama8b
```

## Licensing

Ferret-UI is optional and is governed by terms that are **not** this project's MIT
licence. You accept them directly with the upstream providers when you download.

**Research use only.** This is the operative restriction, and it is inherited rather
than chosen:

| Layer | Terms |
|---|---|
| `jadechoghari/Ferret-UI-Llama8b` (the weights this server loads) | **No licence declared** — the repository states no licence tag, ships no LICENSE file, and sets no license field |
| Apple `ml-ferret` (upstream Ferret) | **CC BY-NC 4.0**, stated as *"intended and licensed for research use only"*, adding that *"models trained using the dataset should not be used outside of research purposes"* |
| Base weights | **Meta Llama 3 Community License** |

Read that first row carefully: the Hugging Face repository grants nothing explicitly,
and silence is not permission. The upstream terms therefore continue to govern, and the
most restrictive of them — CC BY-NC 4.0, research-only — is the one that binds. That
repository is also a community redistribution, not an official Apple release.

Practical consequences:

- **Benchmark and academic research use is within scope.** Running AccessGroundBench and
  publishing the resulting numbers is research use; that is what the restriction permits.
- **Commercial use is not**, at any point in the chain. Do not build a product on this.
- **Attribution is required** by CC BY-NC 4.0. Cite Ferret-UI (arXiv:2404.05719) in any
  work reporting its results.
- The Meta Llama 3 Community License adds its own acceptable-use policy, a "Built with
  Meta Llama 3" attribution requirement, and a 700-million-monthly-active-user threshold
  above which a separate licence must be obtained from Meta.

None of this touches the rest of the benchmark: every other model runs over a hosted API
and carries no such restriction. Ferret-UI is the only component that constrains how
results may be used, which is worth remembering if a venue asks.

See [`THIRD-PARTY-NOTICES.md`](../THIRD-PARTY-NOTICES.md) §4.

## Hardware

CUDA is the practical path. CPU fallback is supported but much slower. About
10 GB of VRAM is an estimate rather than a guarantee; image, tree, and
generation settings affect memory use, and an undersized GPU may raise CUDA OOM.

## Viewing evaluation reports

Once an evaluation or analysis has produced results, the local Web UI presents
the Compare, Results, and Analyze feature views alongside the Ferret run status.
Charts are rendered as SVG on fixed dark data panels while the surrounding
application stays light.
Long model/profile lists remain readable in a scrollable chart viewport, and
the chart's table and direct labels provide the values behind confidence
intervals, paired deltas, discordant counts, and direction segments. Chart
motion follows the browser's `prefers-reduced-motion` setting.

Use a chart's **Export** control to download a PNG of that chart. The control
targets the chart by its explicit view ID and exports the complete SVG at 2×
resolution; if a chart is moved or renamed during frontend work, preserve that
target ID so the downloaded image continues to match the visible chart.
