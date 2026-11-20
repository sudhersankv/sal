"""Set KEY in ./.env from a secret file without echoing it. Usage: set_env.py KEY <file>"""
import re
import sys
from pathlib import Path

key, src = sys.argv[1], Path(sys.argv[2])
val = src.read_text(encoding="utf-8").strip()
env = Path(__file__).resolve().parents[1] / ".env"
lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
pat = re.compile(rf"^{re.escape(key)}=")
out, done = [], False
for ln in lines:
    if pat.match(ln):
        out.append(f"{key}={val}")
        done = True
    else:
        out.append(ln)
if not done:
    out.append(f"{key}={val}")
env.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"{key} set ({len(val)} chars)")
