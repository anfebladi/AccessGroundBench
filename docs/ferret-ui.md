# Local Ferret-UI

Ferret-UI is an optional local VLM for UI grounding. It uses a separate Python
environment because its dependencies conflict with the main project.

## Install and start

```bash
cd ferret_ui
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

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
