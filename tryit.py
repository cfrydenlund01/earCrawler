import os
import json
import gzip
import urllib.request

# Resolve subscription key from env or keyring
key = os.getenv("TRADEGOV_API_KEY")
if not key:
    try:
        import keyring

        key = keyring.get_password(
            "EAR_AI", "TRADEGOV_API_KEY"
        ) or keyring.get_password("earCrawler", "TRADEGOV_API_KEY")
    except Exception:
        key = None

if not key:
    raise SystemExit("No Trade.gov subscription key found in env or keyring")

url = "https://data.trade.gov/consolidated_screening_list/v1/sources"
headers = {
    "Cache-Control": "no-cache",
    "subscription-key": key,
    "User-Agent": "python-urllib/ear-ai/0.2.5",
}

req = urllib.request.Request(url, headers=headers, method="GET")

with urllib.request.urlopen(req, timeout=30) as resp:
    print("status:", resp.status)
    print("content-type:", resp.headers.get("Content-Type"))
    raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)

try:
    data = json.loads(raw.decode("utf-8"))
except json.JSONDecodeError as exc:
    print("failed to parse JSON:", exc)
    print("raw snippet:", repr(raw[:200]))
else:
    print("top-level keys:", list(data)[:10])
