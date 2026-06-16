"""Navigation and flagging state for mobile eval review."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from co_pymol.constants import STRUCTURE_EXTENSIONS
from co_pymol.core.metrics import StructureRecord, extract_record


def plddt_label(mean_plddt: float | None) -> str:
    """Short 'pLDDT=NN.N' label, or 'no pLDDT' when unscored."""
    return f"pLDDT={mean_plddt:.1f}" if mean_plddt is not None else "no pLDDT"


@dataclass
class TriageState:
    files: list[Path] = field(default_factory=list)
    records: dict[str, StructureRecord] = field(default_factory=dict)
    index: int = 0
    flags: list[dict] = field(default_factory=list)
    filter_indices: list[int] | None = field(default=None, repr=False)

    @property
    def active_indices(self) -> list[int]:
        if self.filter_indices is not None:
            return self.filter_indices
        return list(range(len(self.files)))

    def record_for_obj(self, obj_name: str) -> StructureRecord | None:
        """Look up a record by PyMOL object name (file stem) or filename."""
        rec = self.records.get(obj_name)
        if rec is not None:
            return rec
        for fname, candidate in self.records.items():
            if candidate.name == obj_name or fname == obj_name:
                return candidate
        return None

    @property
    def count(self) -> int:
        return len(self.active_indices)

    def load_directory(self, path: str | Path) -> str:
        """Scan directory for structure files and extract metrics.

        Raises NotADirectoryError / FileNotFoundError on bad input.
        """
        path = Path(path)
        if not path.is_dir():
            raise NotADirectoryError(f"{path} is not a directory")

        found = sorted(
            f
            for f in path.iterdir()
            if f.suffix.lower() in STRUCTURE_EXTENSIONS and f.is_file()
        )

        if not found:
            raise FileNotFoundError(f"No structure files found in {path}")

        self.records = {}
        self.index = 0
        self.flags = []
        self.filter_indices = None

        # One unparseable file shouldn't abort the batch — skip it but report why.
        loaded: list[Path] = []
        failed: list[tuple[Path, str]] = []
        for f in found:
            try:
                self.records[f.name] = extract_record(f)
                loaded.append(f)
            except (RuntimeError, ValueError) as e:
                failed.append((f, str(e)))
        self.files = loaded

        sorted_records = sorted(
            self.records.values(), key=StructureRecord.sort_key, reverse=True
        )

        lines = [f"Loaded {len(loaded)} structures from {path.name}/"]
        for r in sorted_records[:10]:
            plddt_str = plddt_label(r.mean_plddt)
            iptm_str = f", ipTM={r.iptm:.3f}" if r.iptm is not None else ""
            lines.append(f"  {r.name}: {plddt_str}{iptm_str}")
        if len(loaded) > 10:
            lines.append(f"  ... and {len(loaded) - 10} more")

        if failed:
            lines.append(f"Skipped {len(failed)} unreadable file(s):")
            for f, err in failed:
                lines.append(f"  {f.name}: {err}")

        return "\n".join(lines)

    def current_path(self) -> Path | None:
        """Get path of current file."""
        if not self.files or not self.active_indices:
            return None
        idx = self.active_indices[self.index]
        return self.files[idx]

    def current_record(self) -> StructureRecord | None:
        """Get the record for the current file."""
        f = self.current_path()
        return self.records.get(f.name) if f is not None else None

    def next(self) -> Path | None:
        """Advance to next structure, return its path."""
        if not self.active_indices:
            return None
        self.index = min(self.index + 1, self.count - 1)
        return self.current_path()

    def prev(self) -> Path | None:
        """Go back one structure, return its path."""
        if not self.active_indices:
            return None
        self.index = max(self.index - 1, 0)
        return self.current_path()

    def go_to(self, n: int) -> Path | None:
        """Jump to Nth structure (1-indexed)."""
        if not self.active_indices:
            return None
        self.index = max(0, min(n - 1, self.count - 1))
        return self.current_path()

    def flag(self, note: str = "") -> str:
        """Flag current structure."""
        record = self.current_record()
        if record is None:
            return "Error: No structure loaded"

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
            plddt_str = plddt_label(f["mean_plddt"])
            note_str = f" — {f['note']}" if f["note"] else ""
            lines.append(f"  {i}. {f['name']} ({plddt_str}){note_str}")
        return "\n".join(lines)

    def export_flags(self) -> str:
        """Export flags as JSON."""
        return json.dumps(self.flags, indent=2)

    def filter(
        self, min_plddt: float, max_plddt: float, include_unscored: bool = False
    ) -> str:
        """Filter structures by pLDDT range.

        Unscored records are excluded unless include_unscored=True.
        """
        matching = []
        for i, f in enumerate(self.files):
            record = self.records.get(f.name)
            if record is None or record.mean_plddt is None:
                if include_unscored:
                    matching.append(i)
                continue
            if min_plddt <= record.mean_plddt <= max_plddt:
                matching.append(i)

        self.filter_indices = matching if len(matching) < len(self.files) else None
        self.index = 0
        n, total = len(matching), len(self.files)
        return (
            f"Filter: {n}/{total} structures with pLDDT in [{min_plddt}, {max_plddt}]"
        )
