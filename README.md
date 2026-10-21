# AI Auto-Router

**One task → right model.** A small router that classifies an incoming task as *coding*, *research*, or *writing* and dispatches it to the specialist model best suited for it.

```
INCOMING TASK ──▶ classifier ──▶ AI ROUTER ──▶ Model A (code generation)
                                            ├─▶ Model B (information retrieval)
                                            └─▶ Model C (creative writing)
```

## Features
- LLM-based classification (fast, cheap model) with automatic keyword-heuristic fallback
- Confidence threshold: low-confidence tasks fall back to a safe default route
- Configurable routing table (`config.json`)
- `--dry` mode to inspect routing decisions without calling the specialist model
- JSONL audit log of every decision (`router_log.jsonl`)
- Offline tests (no API key needed)

## Quickstart
```bash
git clone <your-repo-url> && cd ai-auto-router
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here

python router.py "Write a Python function to dedupe a list"
python router.py --dry "Compare recent papers on regime switching"
python router.py            # interactive mode
```

## Configuration
Edit `config.json` to change the model per category, the classifier model, the default route and the confidence threshold. Any model can also be overridden with an environment variable (`ROUTER_MODEL_CODING`, `ROUTER_MODEL_RESEARCH`, `ROUTER_MODEL_WRITING`, `ROUTER_CLASSIFIER_MODEL`). System prompts live in `PROMPTS` in `router.py`. Check your API provider's docs for current model names.

## Dashboard
A zero-dependency visual layer (standard library only):
```bash
python dashboard.py --demo      # seed the log with 14 sample tasks (route-only, no API cost)
python dashboard.py             # live dashboard at http://127.0.0.1:8000
python dashboard.py --report    # write a shareable, self-contained report.html
```
The live page lets you type a task and see its route, with KPIs, a route-distribution chart and a recent-decisions table. `docs/sample_report.html` is an example static report (generated from the 14 sample tasks) you can open anywhere or commit to the repo.

## Tests
```bash
pytest                # offline, no key needed
python smoke_test.py  # one live check with your API key
```

## Roadmap
- Escalate to a stronger model on low confidence or failed validation
- Per-route cost and latency tracking
- Labeled eval set to measure routing accuracy
- Add more categories (data analysis, math, etc.)

## License
MIT
