#!/usr/bin/env python3
"""Stand-in for `cursor-agent` and `claude` in tests: records argv and cwd, answers per FAKE_CLI_MODE.

Modes: ok (answer FAKE_CLI_ANSWER), garbage, error, quota, sleep.
"""

import json
import os
import sys
import time
from pathlib import Path

log = Path(os.environ["FAKE_CLI_LOG"])
with log.open("a") as f:
    f.write(json.dumps({"argv": sys.argv, "cwd": os.getcwd(), "files": sorted(os.listdir("."))}) + "\n")

mode = os.environ.get("FAKE_CLI_MODE", "ok")
answer = os.environ.get("FAKE_CLI_ANSWER", "{}")
tool = Path(sys.argv[0]).name
if mode == "garbage":
    print("not json at all")
elif mode == "error":
    print(json.dumps({"type": "result", "is_error": True, "result": "model exploded"}))
elif mode == "quota":
    print("Error: You have hit your usage limit.", file=sys.stderr)
    sys.exit(1)
elif mode == "sleep":
    time.sleep(30)
elif tool == "claude":
    print(json.dumps({"structured_output": json.loads(answer), "usage": {"input_tokens": 11, "output_tokens": 7}}))
else:
    print(
        json.dumps(
            {"type": "result", "result": f"```json\n{answer}\n```", "usage": {"inputTokens": 13, "outputTokens": 5}}
        )
    )
