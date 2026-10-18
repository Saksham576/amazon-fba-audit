"""
JSON claim batch exporter conforming to standard schema.
"""

import json
from pathlib import Path
from typing import Union

from ..models.claims import AuditResult


def export_claim_batch_json(result: AuditResult, output_path: Union[str, Path]) -> Path:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    data = result.model_dump(mode="json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return p
