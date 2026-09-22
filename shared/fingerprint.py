import hashlib
import json



def fingerprint(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

