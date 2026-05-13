# Crystal — AI Gateway Frontend

A branded **Databricks App** that gives Crystal employees a single chat interface in front of the AI Gateway endpoints (`gpt`, `claude`, or any others you register). Each user gets their own conversation history, can swap between endpoints from a menu, and can attach PDFs, Word documents, text files, or images for the model to analyze.

Built on **Streamlit** + the OpenAI-compatible Databricks AI Gateway API. Cloneable, parameterized, and deploys with one CLI command.

---

## Features

| | |
|---|---|
| Endpoint picker | Sidebar dropdown of every endpoint listed in `app.yaml` (no code changes to add new ones) |
| File attachments | PDF, Word (`.docx`), text/CSV/Markdown, and images (PNG/JPG/WebP/GIF). Text is inlined; images go to vision-capable models via the OpenAI multimodal schema |
| Per-user chat history | Stored in SQLite keyed by the user's email (`X-Forwarded-Email`). Each user can start, rename, switch between, and delete multiple conversations |
| Crystal branding | Logo, color palette (black + red), and the *“Tejemos vida para nuestro planeta”* tagline |
| Streaming responses | Tokens stream live into the chat panel |
| Fully parameterized | Base URL, endpoint list, max tokens, and history path all come from environment variables in `app.yaml` |

---

## Repository layout

```
crystal_app/
├── app.py                  ← Streamlit entry point
├── app.yaml                ← Databricks Apps config (env vars live here)
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── .streamlit/
│   └── config.toml         ← Streamlit theme
├── static/
│   ├── logo.png            ← Crystal logo (drop-in replacement OK)
│   └── styles.css          ← Brand CSS
└── utils/
    ├── auth.py             ← Reads the authenticated user from Databricks headers
    ├── chat_history.py     ← SQLite-backed conversation store
    ├── config.py           ← Env-var driven configuration
    └── file_handler.py     ← PDF / Word / text / image extraction
```

---

## Deploy in your own Databricks workspace

### 1. Clone the repo

```bash
git clone https://github.com/davcas777/crystal_app.git
cd crystal_app
```

### 2. Edit `app.yaml` with your own AI Gateway

Open `app.yaml` and update the two fields that point at your workspace:

```yaml
env:
  - name: AI_GATEWAY_BASE_URL
    value: "https://<YOUR-WORKSPACE>.azuredatabricks.net/ai-gateway/mlflow/v1"

  - name: AI_GATEWAY_ENDPOINTS
    value: '[{"name":"gpt","label":"OpenAI GPT"},{"name":"claude","label":"Anthropic Claude"}]'
```

You can pass endpoints two ways:

- **Short form** — just names: `gpt,claude,llama-3`
- **Full form** — JSON array with display labels (recommended for end users):
  ```json
  [
    {"name": "gpt",    "label": "OpenAI GPT"},
    {"name": "claude", "label": "Anthropic Claude"}
  ]
  ```

The `name` must match the endpoint name registered in your AI Gateway exactly.

### 3. (Optional) Replace the logo

Drop your own `static/logo.png` in (any reasonable size; the sidebar renders it at 160 px wide).

### 4. Create and deploy the app via the Databricks CLI

Install / authenticate the CLI once:

```bash
pip install databricks-cli
databricks auth login --host https://<YOUR-WORKSPACE>.azuredatabricks.net
```

Sync the code to a workspace folder and create + deploy the app:

```bash
# 1. Sync source to your workspace
databricks workspace import-dir . /Workspace/Users/<you@crystal.com.co>/crystal_app --overwrite

# 2. Create the app (once)
databricks apps create crystal-ai-assistant \
  --description "Crystal AI Assistant — front-end for the AI Gateway"

# 3. Deploy the synced code
databricks apps deploy crystal-ai-assistant \
  --source-code-path /Workspace/Users/<you@crystal.com.co>/crystal_app
```

The CLI returns the live URL once the build finishes (typically 2–4 minutes).

### 5. Grant the app permission to call the AI Gateway

The app runs as a **service principal** automatically created when you provision it. That principal needs `CAN_QUERY` on each serving endpoint exposed through the gateway:

- Workspace UI → **Serving** → select endpoint → **Permissions** → add the app's service principal with **Can Query**.

The app reads the principal's bearer token from the `DATABRICKS_CLIENT_TOKEN` env var Databricks Apps injects at runtime — no PAT required in production.

---

## Run locally (development)

```bash
# 1. Create a venv and install deps
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Copy the env template and fill in your PAT
cp .env.example .env
# edit .env

# 3. Export and run
set -a; source .env; set +a
streamlit run app.py
```

For local dev the app authenticates with your personal access token (`DATABRICKS_TOKEN`) and uses `LOCAL_USER_EMAIL` as the simulated identity.

---

## Configuration reference

All settings are environment variables (set in `app.yaml` for the deployed app, or in `.env` locally).

| Variable | Required | Default | Description |
|---|---|---|---|
| `AI_GATEWAY_BASE_URL` | yes | — | OpenAI-compatible base URL, ending at `/ai-gateway/mlflow/v1` |
| `AI_GATEWAY_ENDPOINTS` | yes | `gpt,claude` | Comma-separated names or JSON array of `{name, label}` |
| `AI_GATEWAY_MAX_TOKENS` | no | `1024` | Per-completion token cap |
| `CHAT_HISTORY_DB_PATH` | no | `/tmp/crystal_chat_history.db` | SQLite file for chat history |
| `DATABRICKS_TOKEN` | local only | — | PAT for local dev |
| `LOCAL_USER_EMAIL` | local only | `anonymous@local` | Simulated user identity for local dev |

### Persisting chat history across restarts

`/tmp` is wiped when the Databricks App pod restarts. For longer retention:

1. **Quick:** point `CHAT_HISTORY_DB_PATH` at a mounted Databricks Volume (`/Volumes/<catalog>/<schema>/<volume>/chat.db`).
2. **Production:** swap the SQLite store in `utils/chat_history.py` for a Delta table read/written via Databricks SQL. The store's public surface (`create_conversation`, `add_message`, `list_messages`, etc.) is small — a Delta-backed implementation is a drop-in replacement.

---

## Adding a new endpoint

1. Provision the endpoint in your AI Gateway (any model behind any provider — OpenAI, Anthropic, Bedrock, OSS).
2. Grant the app's service principal `CAN_QUERY`.
3. Add it to `AI_GATEWAY_ENDPOINTS` in `app.yaml`.
4. `databricks apps deploy …` again.

That's it — the sidebar picker picks it up automatically.

---

## How the AI Gateway call is made

The app uses the OpenAI Python SDK pointed at the Databricks AI Gateway. Equivalent of:

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url="https://<workspace>.azuredatabricks.net/ai-gateway/mlflow/v1",
)

resp = client.chat.completions.create(
    model="claude",                # or "gpt", or whatever you registered
    messages=[{"role": "user", "content": "Hola Crystal"}],
    max_tokens=1024,
    stream=True,
)
```

For multimodal turns (image attachments), the user message becomes a content array:

```python
{
  "role": "user",
  "content": [
    {"type": "text",      "text": "¿Qué ves en esta imagen?"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
  ]
}
```

---

## Support

Internal owner: **David Cascante Espinoza** — `david.cascante@databricks.com`
