# Deployment — IAA

## ADK Web UI (Primary Interface)

```bash
adk web
# Opens at http://localhost:8000
```

Entry point: `agent/main.py` — ADK discovers `root_agent` at module level.
Model: `ADK_MODEL` env var (default `gemini-2.5-flash-lite`).
Session storage: SQLite in `.adk/` directory (gitignored, kept via `.adk/.gitkeep`).

Try: "What should happen next for a claim in documentation_incomplete stage,
medium risk, with a missing_attachment flag?"
The agent must call `predict_next_action` — not answer from memory.

## CLI Demo

```bash
python iaa_demo.py --list                    # list all synthetic cases
python iaa_demo.py --case SYNTH-CLA-0174     # run single case
python iaa_demo.py --risk high               # find + run a high-risk case
python iaa_demo.py --workflow                # 4-agent orchestrator pipeline
```

Demo reads from `data/synthetic_cases.json`. Bootstrap corpus first if empty.

## Docker Compose

```bash
cp .env.docker.template .env   # fill in GOOGLE_API_KEY
docker compose up --build
```

Services:
- `amp_qdrant` — Qdrant vector DB, ports 6333/6334, volume `./qdrant_store`
- `amp_iaa` — IAA app, runs `adk web --host 0.0.0.0 --port 8000`

Ports exposed:
- `http://localhost:8000` — ADK Web UI
- `http://localhost:6333/dashboard` — Qdrant dashboard

To run uvicorn (REST API) instead, change `command:` in `docker-compose.yml`:
```yaml
command: ["uvicorn", "agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

## REST API (FastAPI)

```bash
uvicorn agent.api:app --reload --port 8000
# Swagger UI at http://localhost:8000/docs
```

| Method | Path | Description |
|---|---|---|
| POST | `/predict` | Run IAA on a ProcessState or raw events |
| POST | `/ingest` | Add documents to corpus at runtime |
| POST | `/workflow` | Run 4-agent orchestrator pipeline |
| GET | `/health` | Liveness check |
| GET | `/corpus` | Corpus statistics |
| GET | `/demo` | Run demo case |

## Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GOOGLE_API_KEY` | — | Required for Gemini |
| `ADK_MODEL` | `gemini-2.5-flash-lite` | ADK agent model |
| `QDRANT_PATH` | `./qdrant_store` | Local file store path |
| `QDRANT_HOST` | unset | Set to `qdrant` in Docker |
| `LOG_FILE` | `./data/predictions.jsonl` | Audit log path |

## Known Issues

**Qdrant shutdown warning** — On process exit, embedded Qdrant may print:
> "Qdrant storage was not properly closed"
This is cosmetic. Data is not lost. Caused by the singleton not calling `.close()`.

**First cold start is slow** — sentence-transformers downloads `all-MiniLM-L6-v2`
on first use (~80 MB). Subsequent starts use the cache.

**ADK session DB** — `.adk/*.db` files grow unboundedly in dev. Safe to delete.
They hold conversation history only, not corpus data.
