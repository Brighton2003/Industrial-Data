"""Tag dictionary models and YAML loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "tags.yaml"


class TagConfigError(ValueError):
    """Raised when the tag dictionary is malformed."""


@dataclass(frozen=True)
class TagConfig:
    name: str
    description: str
    unit: str
    min: float
    max: float
    max_age_seconds: float
    flatline_samples: int = 5
    sample_rate_seconds: Optional[float] = None
    source: str = "SIM_PLANT"
    nominal: Optional[float] = None
    noise: float = 0.0


_REQUIRED = ("description", "unit", "min", "max", "max_age_seconds")


def load_tags(path: Path | str = DEFAULT_CONFIG) -> Dict[str, TagConfig]:
    path = Path(path)
    if not path.exists():
        raise TagConfigError(f"Tag config not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    tags_raw = raw.get("tags")
    if not isinstance(tags_raw, dict) or not tags_raw:
        raise TagConfigError("Config must contain a non-empty 'tags' mapping")

    tags: Dict[str, TagConfig] = {}
    for name, spec in tags_raw.items():
        if not isinstance(spec, dict):
            raise TagConfigError(f"Tag '{name}' must be a mapping")
        missing = [k for k in _REQUIRED if k not in spec]
        if missing:
            raise TagConfigError(f"Tag '{name}' missing fields: {missing}")
        if float(spec["min"]) >= float(spec["max"]):
            raise TagConfigError(f"Tag '{name}': min must be < max")
        tags[name] = TagConfig(
            name=name,
            description=str(spec["description"]),
            unit=str(spec["unit"]),
            min=float(spec["min"]),
            max=float(spec["max"]),
            max_age_seconds=float(spec["max_age_seconds"]),
            flatline_samples=int(spec.get("flatline_samples", 5)),
            sample_rate_seconds=(
                float(spec["sample_rate_seconds"])
                if spec.get("sample_rate_seconds") is not None
                else None
            ),
            source=str(spec.get("source", "SIM_PLANT")),
            nominal=float(spec["nominal"]) if spec.get("nominal") is not None else None,
            noise=float(spec.get("noise", 0.0)),
        )
    return tags
