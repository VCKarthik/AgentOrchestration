# Tech Stack — IAA

## LLM Layer

Provider is swapped via `LLM_PROVIDER` env var (`gemini` | `openai`).
Factory lives in `agent/chain.py:37` (`get_llm()`).

| Provider | Model | Use |
|---|---|---|
| `gemini` (default) | gemini-2.5-flash | Dev + production |
| `openai` | gpt-4o-mini | Demo fallback |

Both return a LangChain chat model. The rest of the chain is provider-agnostic.
Temperature is fixed at 0.1 for determinism (`agent/chain.py:37`).

## Embeddings

Model: `all-MiniLM-L6-v2` (sentence-transformers), 384-dim, cosine distance.
Runs **locally** — no embedding API calls, no cost, no rate limits.
Singleton loader at `agent/qdrant_client_singleton.py:52` (`get_embedding_model()`).

Why local embeddings: Gemini embedding API costs money per call and has rate limits.
With ~500 corpus documents and frequent retrieval, local is cheaper and faster.
384-dim is sufficient for process-state similarity — this is not semantic search over prose.

## Vector Store — Qdrant

Collection: `iaa_corpus` (single collection, all domains).
Domain identity stored as payload metadata (`source`, `domain`, `process_type`).
Retrieval scopes to a domain via payload filter — no separate collections needed.

Two connection modes controlled by `QDRANT_HOST` env var:
- `QDRANT_HOST` unset → local file client at `QDRANT_PATH` (default `./qdrant_store`)
- `QDRANT_HOST=qdrant` → network client to Docker service on port 6333

### Why the Singleton

Embedded Qdrant takes an exclusive file lock on `./qdrant_store`.
Two `QdrantClient(path=...)` instances in the same process raise:
> "Storage folder is already accessed by another instance"

The singleton at `agent/qdrant_client_singleton.py:33` (`get_qdrant_client()`)
ensures only one client is created per process. All modules import from it.

## Three-Step LLM Chain

Defined in `agent/chain.py`. Steps fire sequentially, each a separate LLM call:

1. **Contextualize** — summarize the process state into plain English
2. **Anticipate** — predict 1–3 next actions + task_list + workflow_timeline (JSON)
3. **Recommend** — select the single best action with business justification (JSON)

Rule overrides fire after step 3 (`agent/chain.py:apply_overrides`):

| Trigger | Override |
|---|---|
| `risk_severity` is `high` or `critical` | Force escalate to human |
| `risk_flags` contains `missing_*` | Recommend requesting the document |
| Top confidence < 0.45 | Set `escalate_to_human = True` |

Original LLM predictions are always preserved in `predicted_actions` for transparency.

## ADK Integration

Entry point: `agent/main.py`. Two `FunctionTool` wrappers over `run_iaa()` and `IAARetriever`.
ADK model configured via `ADK_MODEL` env var (default `gemini-2.5-flash-lite`).
`root_agent` module-level alias is required by `adk web` discovery.
