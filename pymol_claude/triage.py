"""Navigation and flagging state for mobile eval review."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pymol_claude.metrics import StructureRecord, extract_record


@dataclass
class TriageState:
    files: list[Path] = field(default_factory=list)
    records: dict[str, StructureRecord] = field(default_factory=dict)
    index: int = 0
    flags: list[dict] = field(default_factory=list)
    _filter_indices: Optional[list[int]] = field(default=None, repr=False)

    @property
    def active_indices(self) -> list[int]:
        if self._filter_indices is not None:
            return self._filter_indices
        return list(range(len(self.files)))

    @property
    def count(self) -> int:
        return len(self.active_indices)

    def load_directory(self, path: str | Path) -> str:
        """Scan directory for structure files and extract metrics."""
        path = Path(path)
        if not path.is_dir():
            return f"Error: {path} is not a directory"

        extensions = {".cif", ".mmcif", ".pdb", ".ent"}
        found = sorted(
            f for f in path.iterdir()
            if f.suffix.lower() in extensions and f.is_file()
        )

        if not found:
            return f"No structure files found in {path}"

        self.files = found
        self.records = {}
        self.index = 0
        self.flags = []
        self._filter_indices = None

        for f in found:
            record = extract_record(f)
            self.records[f.name] = record

        # Sort by mean pLDDT descending (None values last)
        sorted_records = sorted(
            self.records.values(),
            key=lambda r: r.mean_plddt if r.mean_plddt is not None else -1,
            reverse=True,
        )

        lines = [f"Loaded {len(found)} structures from {path.name}/"]
        for r in sorted_records[:10]:
            plddt_str = f"pLDDT={r.mean_plddt:.1f}" if r.mean_plddt is not None else "no pLDDT"
            iptm_str = f", ipTM={r.iptm:.3f}" if r.iptm is not None else ""
            lines.append(f"  {r.name}: {plddt_str}{iptm_str}")
        if len(found) > 10:
            lines.append(f"  ... and {len(found) - 10} more")

        return "\n".join(lines)

    def current_record(self) -> Optional[StructureRecord]:
        """Get the record for the current file."""
        if not self.files or not self.active_indices:
            return None
        idx = self.active_indices[self.index]
        f = self.files[idx]
        return self.records.get(f.name)

    def current_path(self) -> Optional[Path]:
        """Get path of current file."""
        if not self.files or not self.active_indices:
            return None
        idx = self.active_indices[self.index]
        return self.files[idx]

    def next(self) -> Optional[Path]:
        """Advance to next structure, return its path."""
        if not self.active_indices:
            return None
        self.index = min(self.index + 1, self.count - 1)
        return self.current_path()

    def prev(self) -> Optional[Path]:
        """Go back one structure, return its path."""
        if not self.active_indices:
            return None
        self.index = max(self.index - 1, 0)
        return self.current_path()

    def go_to(self, n: int) -> Optional[Path]:
        """Jump to Nth structure (1-indexed)."""
        if not self.active_indices:
            return None
        self.index = max(0, min(n - 1, self.count - 1))
        return self.current_path()

    def flag(self, note: str = "") -> str:
        """Flag current structure."""
        record = self.current_record()
        if record is None:
            return "No structure loaded"

        entry = {
            "name": record.name,
            "path": str(record.path),
            "index": self.index + 1,
            "note": note,
            "mean_plddt": record.mean_plddt,
            "iptm": record.iptm,
        }
        self.flags.append(entry)
        return f"Flagged: {record.name} ({len(self.flags)} total flags)"

    def show_flags(self) -> str:
        """List all flagged structures."""
        if not self.flags:
            return "No structures flagged"

        lines = [f"{len(self.flags)} flagged structures:"]
        for i, f in enumerate(self.flags, 1):
            plddt_str = f"pLDDT={f['mean_plddt']:.1f}" if f["mean_plddt"] is not None else "no pLDDT"
            note_str = f" — {f['note']}" if f["note"] else ""
            lines.append(f"  {i}. {f['name']} ({plddt_str}){note_str}")
        return "\n".join(lines)

    def export_flags(self) -> str:
        """Export flags as JSON."""
        return json.dumps(self.flags, indent=2)

    def filter(self, min_plddt: float = 0, max_plddt: float = 100) -> str:
        """Filter structures by pLDDT range."""
        matching = []
        for i, f in enumerate(self.files):
            record = self.records.get(f.name)
            if record and record.mean_plddt is not None:
                if min_plddt <= record.mean_plddt <= max_plddt:
                    matching.append(i)
            elif min_plddt == 0:
                # Include structures without pLDDT if min is 0
                matching.append(i)

        self._filter_indices = matching if len(matching) < len(self.files) else None
        self.index = 0
        return f"Filter: {len(matching)}/{len(self.files)} structures with pLDDT in [{min_plddt}, {max_plddt}]"
