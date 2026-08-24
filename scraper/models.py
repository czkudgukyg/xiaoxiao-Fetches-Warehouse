from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Target:
    brand: str
    region: str
    product: str
    variant: str
    url: str
    task_id: str = ""


@dataclass
class Result:
    brand: str = ""
    region: str = ""
    requested_product: str = ""
    requested_variant: str = ""
    input_url: str = ""
    final_url: str = ""
    domain: str = ""
    variant_id: str = ""
    detected_product: str = ""
    detected_variant: str = ""
    current_price: float | None = None
    compare_at_price: float | None = None
    currency: str = ""
    promotion: list[str] = field(default_factory=list)
    stock_status: str = ""
    available: bool | None = None
    http_status: int | None = None
    capture_time_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verification_status: str = "UNVERIFIED"
    verification_reason: str = ""
    data_source: str = ""
    screenshot_path: str = ""
    raw_evidence: list[dict[str, Any]] = field(default_factory=list)

    def dict(self) -> dict[str, Any]:
        return asdict(self)

