# 9router

9router is an optional, third-party local LLM gateway. It exposes an
OpenAI-compatible `/v1` endpoint that fans out to many upstream providers, so
a single `NINEROUTER_BASE_URL` can front models you'd otherwise need separate
API keys for. It is not maintained by this project, and using it is entirely
optional — every other provider in this benchmark talks to its native hosted
API directly.

## Install and start

```bash
npm install -g 9router
```

or with Docker:

```bash
docker run -d --name 9router -p 20128:20128 -v 9router-data:/app/data decocua/9router:latest
```

Start it:

```bash
9router
```

It listens on port `20128` by default, and its dashboard opens at
`http://localhost:20128/dashboard`.

## Getting an API key

Set a dashboard password on first launch:

```bash
INITIAL_PASSWORD=your-password 9router
```

(or edit `~/.9router/config.json` under its `auth` section). Log into the
dashboard with that password, add the upstream providers you want routed,
and copy the key it gives you for making requests through the gateway.

## Wiring it into this project

Set both variables in `.env` — the Models tab in the web UI can only ever
set `NINEROUTER_API_KEY` for you as a session key, since `NINEROUTER_BASE_URL`
is a URL rather than a credential and isn't something that mechanism will
write:

```dotenv
NINEROUTER_BASE_URL=http://localhost:20128/v1
NINEROUTER_API_KEY=<key from the 9router dashboard>
```

Then reference routed models with the `9router/` prefix, e.g.:

```dotenv
VLM_MODEL=9router/ag/qwen3-vl-235b-a22b-instruct
```

Results are still named after the underlying model, not the route used to
reach it — see [Adding your own model](../README.md#adding-your-own-model) in
the main README. For connection errors, see
[troubleshooting.md](troubleshooting.md).
