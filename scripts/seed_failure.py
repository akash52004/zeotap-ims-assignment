import json
import sys
import time
import urllib.request
from pathlib import Path


API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
ROOT = Path(__file__).resolve().parents[1]
EVENTS = json.loads((ROOT / "sample-data" / "failure_event.json").read_text(encoding="utf-8"))


def post(path: str, payload) -> None:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.status, response.read().decode("utf-8"))


def main() -> None:
    burst = []
    for i in range(100):
        item = dict(EVENTS[0])
        item["message"] = f"{item['message']} #{i + 1}"
        item["payload"] = {**item["payload"], "sample_index": i + 1}
        burst.append(item)
    post("/api/signals/batch", burst)
    time.sleep(1)
    post("/api/signals/batch", EVENTS[1:])
    print("Seeded RDBMS burst plus MCP/cache follow-on signals.")


if __name__ == "__main__":
    main()
