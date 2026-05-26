"""Structure metrics MCP tools (gemmi-backed)."""

from __future__ import annotations

from pathlib import Path

import gemmi
from mcp.server.fastmcp import FastMCP

from pylot.core.metrics import StructureRecord
from pylot.core.metrics import find_low_confidence as find_low
from pylot.core.session import AppSession
from pylot.utils.pymol_helpers import ensure_pymol, pymol_lock


def register_metrics_tools(mcp: FastMCP, session: AppSession) -> None:
    @mcp.tool()
    def get_metrics(name: str = "", path: str = "") -> str:
        """Get detailed structure metrics (pLDDT, ipTM, pTM, PAE).

        For objects loaded via run('cmd.load(...)'), pass `path` to the structure file.
        """
        cmd = ensure_pymol()

        with pymol_lock:
            objects = cmd.get_object_list()
        if not objects:
            return "Error: No objects loaded"
        if name and name not in objects:
            return f"Error: Object '{name}' not found. Loaded: {', '.join(objects)}"

        targets = [name] if name else objects
        results = []
        for obj_name in targets:
            obj_path = path if obj_name == name else ""
            record = session.record_for_obj(obj_name, path=obj_path)
            if record is None:
                hint = " Pass `path` to the structure file." if not path else ""
                results.append(f"{obj_name}: no metrics available.{hint}")
            else:
                results.append(record.format_report())
        return "\n\n".join(results)

    @mcp.tool()
    def find_low_confidence(name: str = "", threshold: int = 70, path: str = "") -> str:
        """Find contiguous low-pLDDT regions in a structure."""
        if name:
            record = session.record_for_obj(name, path=path)
            if record is None:
                hint = " Pass `path` to the structure file." if not path else ""
                return f"Error: No metrics for '{name}'.{hint}"
            return find_low(record, threshold)

        cmd = ensure_pymol()
        with pymol_lock:
            objects = cmd.get_object_list()
        if not objects:
            return "Error: No objects loaded"

        results = []
        for obj in objects:
            record = session.record_for_obj(obj)
            if record is None:
                results.append(f"{obj}: no metrics available")
            else:
                results.append(find_low(record, threshold))
        return "\n\n".join(results)

    @mcp.tool()
    def compare_all() -> str:
        """Compare loaded structures by pLDDT — sorted table."""
        records = session.metrics.all_records()
        if not records and session.triage.records:
            session.sync_metrics_from_triage()
            records = session.metrics.all_records()
        if not records:
            return (
                "Error: No structures with metrics. "
                "Use load_directory or get_metrics with path."
            )

        records = sorted(records, key=StructureRecord.sort_key, reverse=True)

        lines = [
            f"{'Name':<30} {'pLDDT':>8} {'ipTM':>8} {'pTM':>8} {'Chains':>6} {'Res':>6}"
        ]
        lines.append("-" * 70)
        for r in records:
            plddt = f"{r.mean_plddt:.1f}" if r.mean_plddt is not None else "—"
            iptm = f"{r.iptm:.3f}" if r.iptm is not None else "—"
            ptm = f"{r.ptm:.3f}" if r.ptm is not None else "—"
            chains, res = len(r.chains), r.n_residues
            lines.append(
                f"{r.name:<30} {plddt:>8} {iptm:>8} {ptm:>8} {chains:>6} {res:>6}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def cif_grep(tag: str, path: str = ".") -> str:
        """Search CIF files for a tag's value.

        Example tag: '_ma_qa_metric_global.metric_value'.
        path may be a file or a directory (recursed on *.cif).
        """
        p = Path(path).expanduser()
        if p.is_dir():
            targets = sorted(p.rglob("*.cif"))
        elif p.is_file():
            targets = [p]
        else:
            return f"Error: Not found: {p}"
        if not targets:
            return f"Error: No .cif files under {p}"

        if "." in tag:
            category, _, item = tag.rpartition(".")
            category = category + "."
        else:
            category, item = None, tag

        lines = []
        for f in targets:
            try:
                doc = gemmi.cif.read(str(f))
            except (RuntimeError, ValueError) as e:
                lines.append(f"{f.name}: <parse error: {e}>")
                continue
            for block in doc:
                if category is not None:
                    for row in block.find(category, [item]):
                        lines.append(f"{f.name}: {row[0]}")
                else:
                    v = block.find_value(tag)
                    if v is not None:
                        lines.append(f"{f.name}: {v}")
        return "\n".join(lines) or "No matches"
