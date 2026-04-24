"""JSON export — full data with all computed metrics."""
import json
from app.core.exports.common import compute_export_integrity


def generate_json(data: dict) -> str:
    """Generate comprehensive JSON export from prepared data. Returns JSON string.

    The export includes an ``_integrity`` metadata block containing a SHA-256
    hash of the payload (computed before the block is added), a UTC timestamp,
    and the benchmark run ID.  Recipients can verify authenticity by:

        import json, hashlib
        export = json.loads(open("export.json").read())
        integrity = export.pop("_integrity")
        canonical = json.dumps(export, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert hashlib.sha256(canonical.encode()).hexdigest() == integrity["sha256"]
    """
    run_id = data.get("run", {}).get("id")
    integrity = compute_export_integrity(data, run_id)

    export = dict(data)
    export["_integrity"] = integrity

    return json.dumps(export, indent=2, ensure_ascii=False, default=str)
