"""One-shot live check. Run once with your key.
    export ANTHROPIC_API_KEY=your_key
    python smoke_test.py
Makes 3 classifier calls + 3 specialist calls (small max_tokens use, a few cents at most).
"""
import os, sys
from router import Router

if not os.getenv("ANTHROPIC_API_KEY"):
    sys.exit("Set ANTHROPIC_API_KEY first.")

CASES = {
    "Write a Python function that merges two sorted lists": "coding",
    "Compare recent approaches to regime detection in markets": "research",
    "Write a short, warm email declining a meeting": "writing",
}

r = Router()
ok = True
for task, expected in CASES.items():
    res = r.run(task)
    good = res["category"] == expected and res["response"]
    ok &= bool(good)
    print(f"{'PASS' if good else 'FAIL'} | expected {expected:8} got {res['category']:8} "
          f"via {res['classifier']:10} model={res['model']} route {res['classify_ms']}ms, model {res['model_ms']}ms")
    if not res["response"]:
        print("   no response returned (check model names in ROUTES)")
sys.exit(0 if ok else 1)
