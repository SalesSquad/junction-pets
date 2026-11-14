"""Disclosed temporary compiler compatibility overlay; never edit sponsor tests."""
import hashlib
import json
from pathlib import Path

path = Path("global.json")
before = path.read_bytes()
config = json.loads(before)
assert config["sdk"]["version"] == "8.0.402"
assert config["sdk"]["rollForward"] == "patch"
config["sdk"].update(version="9.0.100", rollForward="disable", allowPrerelease=False)
after = (json.dumps(config, indent=2) + "\n").encode()
path.write_bytes(after)
print(json.dumps({"scope": "explicit-compiler-compatibility-overlay",
    "original_sdk": "8.0.402", "experiment_sdk": "9.0.100",
    "original_global_json_sha256": hashlib.sha256(before).hexdigest(),
    "overlay_global_json_sha256": hashlib.sha256(after).hexdigest(),
    "reason": "Pinned SDK compiler4.11 cannot load sponsor source generator requiring4.12",
    "pinned_sdk_qualification": False}, sort_keys=True))
