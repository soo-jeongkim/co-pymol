"""Per-server session state (triage navigation + metrics cache)."""

from __future__ import annotations

from pathlib import Path

from pylot.core.metrics import StructureRecord, extract_record
from pylot.core.triage import TriageState


class MetricsRegistry:
    """Object-name → StructureRecord cache, decoupled from triage navigation."""

    def __init__(self) -> None:
        self._by_obj: dict[str, StructureRecord] = {}

    def clear(self) -> None:
        self._by_obj.clear()

    def register(self, obj_name: str, record: StructureRecord) -> None:
        self._by_obj[obj_name] = record

    def register_from_path(self, obj_name: str, path: Path) -> StructureRecord:
        record = extract_record(path, name=obj_name)
        self._by_obj[obj_name] = record
        return record

    def get(self, obj_name: str, path: str = "") -> StructureRecord | None:
        if obj_name in self._by_obj:
            return self._by_obj[obj_name]
        if path:
            return self.register_from_path(obj_name, Path(path).expanduser())
        return None

    def all_records(self) -> list[StructureRecord]:
        return list(self._by_obj.values())


class AppSession:
    """State for one MCP server instance (one PyMOL session)."""

    def __init__(self) -> None:
        self.triage = TriageState()
        self.metrics = MetricsRegistry()

    def sync_metrics_from_triage(self) -> None:
        """Rebuild metrics cache from the current triage directory load."""
        self.metrics.clear()
        for f in self.triage.files:
            record = self.triage.records.get(f.name)
            if record is not None:
                self.metrics.register(f.stem, record)

    def record_for_obj(self, obj_name: str, path: str = "") -> StructureRecord | None:
        """Resolve metrics for a PyMOL object name, with optional file path fallback."""
        record = self.metrics.get(obj_name, path=path)
        if record is not None:
            return record
        record = self.triage.record_for_obj(obj_name)
        if record is not None:
            self.metrics.register(obj_name, record)
            return record
        return None
