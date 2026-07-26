# Optional integrations

[Back to README](../README.md)

## 9Router gateway

9Router is an optional local OpenAI-compatible gateway. Use it to route supported models through one local endpoint instead of calling a native provider directly. This project uses the API at `http://localhost:20128/v1` and the dashboard at `http://localhost:20128/dashboard`.

### Install and start 9Router

```bash
npm install -g 9router
9router
```

Leave the `9router` process running and open <http://localhost:20128/dashboard>.

### Configure a provider route

In **Dashboard → Providers**:

1. Open **Providers**.
2. Connect or configure the provider/account.
3. Copy the API key supplied by 9Router.
4. Copy the exact model route shown by 9Router. Do not substitute the native provider model name; the route may include a provider-specific prefix.

Set the endpoint, key, and exact route in `.env`:

```dotenv
VLM_MODEL=9router/<route-from-dashboard>
NINEROUTER_BASE_URL=http://localhost:20128/v1
NINEROUTER_API_KEY=<api-key-from-9router-dashboard>
```

The `9router/` prefix tells LiteLLM to send the request to 9Router; the route after the prefix is passed through unchanged. The base URL may include `/v1` or omit it. One 9Router endpoint is configured per process, while native providers can still be mixed in the comma-separated `VLM_MODEL` list.

Verify that `dataset/labels/` contains baseline labels before evaluation. If it does not, collect the data first:

```bash
uv run python -m collection.orchestrator
```

Then run:

```bash
uv run python -m vlm_eval.cli
```

See the [official 9Router setup guide](https://github.com/decolua/9router/blob/master/README.md) for platform-specific details.

## Local Ferret-UI model

Ferret-UI is a small open-source VLM fine-tuned for mobile UI grounding. It runs locally on a CUDA-capable GPU.

1. Download the model weights, which requires Hugging Face access:

   ```bash
   python ferret_ui/download_scripts.py
   ```

2. Create a separate virtual environment because its dependencies conflict with the main project:

   ```bash
   cd ferret_ui
   python -m venv venv
   venv\Scripts\activate          # Windows
   pip install -r requirements.txt
   ```

3. Start the inference server:

   ```bash
   .\start_server.bat
   ```

   The server runs on `http://localhost:8000` by default. Leave it running in a separate terminal.

4. Add `local/ferret-ui-llama8b` to `VLM_MODEL` in `.env` and run the evaluator normally.

Running Ferret-UI requires a CUDA GPU with at least 10 GB VRAM. Insufficient resources may result in thermal throttling or an out-of-memory error.

