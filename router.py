"""
Auto-routing: one task -> right model.

Flow (matches the diagram):
  incoming task -> classify (coding / research / writing) -> AI router -> specialist model

Usage:
  pip install anthropic
  export ANTHROPIC_API_KEY=...
  python router.py "Write a Python function to dedupe a list"
  python router.py --dry "Summarise recent papers on regime switching"   # route only, no model call
  python router.py            # interactive mode

With no API key, the router falls back to a keyword classifier (still routes, can't call models).
"""
import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass

# ---- 1. Model registry (loaded from config.json) -------------------------------
@dataclass
class Route:
    label: str
    model: str
    system: str

PROMPTS = {
    "coding": "You are a senior engineer. Return correct, minimal, runnable code with brief notes.",
    "research": "You are a rigorous research analyst. Be precise, state uncertainty, structure findings clearly.",
    "writing": "You are a skilled writer. Match the requested tone and audience; be vivid and concise.",
}

def load_config(path: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")) -> dict:
    with open(path) as f:
        return json.load(f)

CONFIG = load_config()
# Override any model per category with an env var, e.g. ROUTER_MODEL_CODING=<model-id>
ROUTES = {
    cat: Route(r["label"], os.getenv(f"ROUTER_MODEL_{cat.upper()}", r["model"]), PROMPTS[cat])
    for cat, r in CONFIG["routes"].items()
}
DEFAULT = CONFIG["default_category"]
CLASSIFIER_MODEL = os.getenv("ROUTER_CLASSIFIER_MODEL", CONFIG["classifier_model"])

# ---- 2. Classifiers ------------------------------------------------------------
KEYWORDS = {
    "coding": r"\b(code|function|bug|debug|python|javascript|sql|api|script|regex|class|compile|error|refactor|implement|algorithm)\b",
    "research": r"\b(research|find|compare|summari[sz]e|explain|what is|why|how does|analy[sz]e|sources?|papers?|data|study)\b",
    "writing": r"\b(write|draft|essay|story|poem|email|blog|rewrite|tone|caption|speech|cover letter|post)\b",
}

def classify_heuristic(task: str) -> dict:
    scores = {k: len(re.findall(p, task.lower())) for k, p in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return {"category": DEFAULT, "confidence": 0.3, "via": "heuristic-default"}
    total = sum(scores.values())
    return {"category": best, "confidence": round(scores[best] / total, 2), "via": "heuristic"}

def classify_llm(client, task: str) -> dict:
    prompt = (
        "Classify the task into exactly one category: coding, research, or writing.\n"
        'Reply with JSON only: {"category": "...", "confidence": 0-1}\n\nTask: ' + task
    )
    r = client.messages.create(
        model=CLASSIFIER_MODEL, max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )
    data = json.loads(re.search(r"\{.*\}", r.content[0].text, re.S).group())
    if data["category"] not in ROUTES:
        raise ValueError("bad category")
    return {"category": data["category"], "confidence": float(data.get("confidence", 0.5)), "via": "llm"}

# ---- 3. Router -----------------------------------------------------------------
class Router:
    def __init__(self, min_confidence: float = CONFIG["min_confidence"]):
        self.min_confidence = min_confidence
        self.client = None
        if os.getenv("ANTHROPIC_API_KEY"):
            import anthropic
            self.client = anthropic.Anthropic()

    def route(self, task: str) -> tuple[Route, dict]:
        info = None
        if self.client:
            try:
                info = classify_llm(self.client, task)
            except Exception:
                info = None
        if info is None:
            info = classify_heuristic(task)
        if info["confidence"] < self.min_confidence:  # low confidence -> safe default
            info["category"] = DEFAULT
            info["via"] += "+fallback"
        return ROUTES[info["category"]], info

    def run(self, task: str, dry: bool = False) -> dict:
        t0 = time.perf_counter()
        route, info = self.route(task)
        t1 = time.perf_counter()
        out = {"task": task, "category": info["category"], "confidence": info["confidence"],
               "classifier": info["via"], "model": route.model, "label": route.label}
        model_ms = 0.0
        if dry or not self.client:
            out["response"] = None
        else:
            tm = time.perf_counter()
            r = self.client.messages.create(
                model=route.model, max_tokens=1500, system=route.system,
                messages=[{"role": "user", "content": task}],
            )
            out["response"] = r.content[0].text
            model_ms = (time.perf_counter() - tm) * 1000
        out["classify_ms"] = round((t1 - t0) * 1000, 2)  # routing decision only
        out["model_ms"] = round(model_ms, 2)             # specialist call only (0 in route-only mode)
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        with open("router_log.jsonl", "a") as f:  # simple audit trail
            f.write(json.dumps({k: v for k, v in out.items() if k != "response"}) + "\n")
        return out

def show(res: dict):
    print(f"\n[{res['category'].upper()} | conf {res['confidence']} | {res['classifier']}] -> {res['label']} ({res['model']})")
    if res["response"]:
        print("\n" + res["response"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task", nargs="*")
    ap.add_argument("--dry", action="store_true", help="route only, don't call the model")
    a = ap.parse_args()
    router = Router()
    if a.task:
        show(router.run(" ".join(a.task), a.dry))
        return
    print("Auto-router. Type a task (blank to quit).")
    while (t := input("\n> ").strip()):
        show(router.run(t, a.dry))

if __name__ == "__main__":
    sys.exit(main())
