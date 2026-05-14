"""FastMCP server exposing PyMOL's cmd module as MCP tools."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP, Image

_pymol_lock = threading.Lock()

# Triage state (module-level singleton)
_triage = None


def _get_triage():
    global _triage
    if _triage is None:
        from pymol_claude.triage import TriageState
        _triage = TriageState()
    return _triage


def _ensure_pymol():
    """Import pymol.cmd, raising a clear error if unavailable."""
    try:
        from pymol import cmd
        return cmd
    except ImportError:
        raise RuntimeError(
            "PyMOL is not installed. Install it with: "
            "uv pip install pymol-open-source"
        )


def _render_image(width: int, height: int, ray: bool = False) -> Image:
    """Render current PyMOL view to an Image. Must be called with _pymol_lock held."""
    cmd = _ensure_pymol()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if ray:
            cmd.ray(width, height)
        else:
            cmd.draw(width, height, antialias=2)
        cmd.png(tmp_path, dpi=150)

        # PyMOL's png command may be async; wait for file
        import time
        for _ in range(50):
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                break
            time.sleep(0.1)

        data = Path(tmp_path).read_bytes()
        return Image(data=data, format="png")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _triage_render(path: Path, width: int = 800, height: int = 600) -> Image:
    """Load a structure for triage and render it. Must be called with _pymol_lock held."""
    cmd = _ensure_pymol()
    cmd.delete("all")
    cmd.load(str(path))
    obj_name = cmd.get_object_list()[0]
    cmd.show("cartoon", "all")
    cmd.hide("lines", "all")
    cmd.spectrum("b", "red_yellow_green_cyan_blue", "all", 0, 100)
    cmd.orient("all")
    cmd.bg_color("white")
    return _render_image(width, height, ray=False)


def create_server() -> FastMCP:
    """Create and configure the FastMCP server with all PyMOL tools."""

    mcp = FastMCP(
        "pymol-claude",
        instructions=(
            "You are a PyMOL assistant. You have direct control of a running PyMOL session "
            "through the tools provided. When the user asks you to do something visual — "
            "color, align, show, hide — DO IT by calling the tool. Don't describe what to do; "
            "execute it.\n\n"
            "Key conventions:\n"
            "- B-factor column on predicted structures is pLDDT (0-100). Call it pLDDT, not B-factor.\n"
            "- When rendering for mobile: always include key metrics (pLDDT, ipTM) in your text "
            "alongside the image.\n"
            "- PyMOL selection syntax: 'chain A', 'resi 45-67', 'chain A and resi 45-67', "
            "'name CA', 'polymer', 'organic', 'all'\n"
            "- PyMOL color names: red, green, blue, yellow, cyan, magenta, orange, salmon, "
            "lime, slate, violet, marine, forest, chocolate, wheat, lightblue, etc.\n"
            "- For anything not covered by specific tools, use the `run` tool.\n"
            "- When triaging structures (next/prev/flag), always render an image and report "
            "mean pLDDT and ipTM."
        ),
    )

    # ── Visualization ──────────────────────────────────────────────────────

    @mcp.tool()
    def load(path: str) -> str:
        """Load a structure file (PDB, CIF, SDF, etc.) into PyMOL."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.load(path)
            objects = cmd.get_object_list()
            return f"Loaded: {objects[-1]} (objects: {', '.join(objects)})"

    @mcp.tool()
    def delete(name: str) -> str:
        """Delete an object or selection from PyMOL. Use 'all' to clear everything."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.delete(name)
            return f"Deleted: {name}"

    @mcp.tool()
    def list_objects() -> str:
        """List all loaded objects with basic info."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            objects = cmd.get_object_list()
            if not objects:
                return "No objects loaded"
            lines = []
            for obj in objects:
                n_atoms = cmd.count_atoms(obj)
                chains = cmd.get_chains(obj)
                lines.append(f"{obj}: {n_atoms} atoms, chains {','.join(chains)}")
            return "\n".join(lines)

    @mcp.tool()
    def show(representation: str, selection: str = "all") -> str:
        """Show a representation. Types: cartoon, sticks, surface, spheres, ribbon, lines, mesh, dots."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.show(representation, selection)
            return f"Showing {representation} for {selection}"

    @mcp.tool()
    def hide(representation: str, selection: str = "all") -> str:
        """Hide a representation."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.hide(representation, selection)
            return f"Hidden {representation} for {selection}"

    @mcp.tool()
    def color(color: str, selection: str = "all") -> str:
        """Color a selection. Use PyMOL color names (red, blue, salmon, etc.) or hex (#FF0000)."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.color(color, selection)
            return f"Colored {selection} {color}"

    @mcp.tool()
    def color_by_plddt(selection: str = "all") -> str:
        """Color by pLDDT (B-factor column). Blue=high confidence, red=low."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.spectrum("b", "red_yellow_green_cyan_blue", selection, 0, 100)
            return f"Colored {selection} by pLDDT"

    @mcp.tool()
    def color_by_chain(selection: str = "all") -> str:
        """Color each chain a different color."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.util.cbc(selection)
            return f"Colored {selection} by chain"

    @mcp.tool()
    def color_by_spectrum(selection: str = "all", palette: str = "rainbow") -> str:
        """Color by spectrum (rainbow, blue_white_red, etc.)."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.spectrum("count", palette, selection)
            return f"Colored {selection} by spectrum ({palette})"

    @mcp.tool()
    def select(name: str, selection: str) -> str:
        """Create a named selection using PyMOL selection syntax."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            n = cmd.select(name, selection)
            return f"Selection '{name}' = {selection} ({n} atoms)"

    @mcp.tool()
    def zoom(selection: str = "all") -> str:
        """Zoom the camera to fit a selection."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.zoom(selection)
            return f"Zoomed to {selection}"

    @mcp.tool()
    def center(selection: str = "all") -> str:
        """Center the camera on a selection."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.center(selection)
            return f"Centered on {selection}"

    @mcp.tool()
    def orient(selection: str = "all") -> str:
        """Orient the view to show a selection optimally."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.orient(selection)
            return f"Oriented to {selection}"

    @mcp.tool()
    def turn(axis: str, angle: float) -> str:
        """Rotate the view. axis: x, y, or z. angle: degrees."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.turn(axis, angle)
            return f"Turned {angle}° around {axis}"

    @mcp.tool()
    def bg_color(color: str = "white") -> str:
        """Set the background color."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.bg_color(color)
            return f"Background set to {color}"

    @mcp.tool()
    def set_setting(name: str, value: str) -> str:
        """Set a PyMOL setting (e.g., 'cartoon_transparency', '0.5')."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            cmd.set(name, value)
            return f"Set {name} = {value}"

    # ── Structural analysis ────────────────────────────────────────────────

    @mcp.tool()
    def align(mobile: str, target: str) -> str:
        """Sequence-based alignment. Returns RMSD and aligned atom count."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            result = cmd.align(mobile, target)
            rmsd = result[0]
            n_atoms = result[1]
            return f"Aligned {mobile} to {target}: RMSD={rmsd:.2f} A, {n_atoms} atoms aligned"

    @mcp.tool()
    def super_align(mobile: str, target: str) -> str:
        """Structure-based superposition (better for low sequence identity)."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            result = cmd.super(mobile, target)
            rmsd = result[0]
            n_atoms = result[1]
            return f"Superposed {mobile} on {target}: RMSD={rmsd:.2f} A, {n_atoms} atoms"

    @mcp.tool()
    def polar_contacts(sel1: str = "", sel2: str = "", cutoff: float = 3.5) -> str:
        """Find polar contacts (H-bonds, salt bridges) between selections."""
        cmd = _ensure_pymol()
        if not sel1:
            sel1 = "all"
        if not sel2:
            sel2 = sel1
        with _pymol_lock:
            n = cmd.distance("contacts", sel1, sel2, cutoff, mode=2)
            return f"Found polar contacts between {sel1} and {sel2} (cutoff={cutoff} A): {n:.0f} contacts"

    @mcp.tool()
    def measure(sel1: str, sel2: str) -> str:
        """Measure distance between two selections (atoms)."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            d = cmd.get_distance(sel1, sel2)
            return f"Distance {sel1} — {sel2}: {d:.2f} A"

    @mcp.tool()
    def get_sequence(selection: str = "all") -> str:
        """Get FASTA sequence for a selection."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            fasta = cmd.get_fastastr(selection)
            return fasta if fasta.strip() else "No sequence found"

    @mcp.tool()
    def get_chains(object: str = "") -> str:
        """Get chain IDs for an object."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            sel = object if object else "all"
            chains = cmd.get_chains(sel)
            return f"Chains: {', '.join(chains)}" if chains else "No chains found"

    @mcp.tool()
    def count_atoms(selection: str = "all") -> str:
        """Count atoms in a selection."""
        cmd = _ensure_pymol()
        with _pymol_lock:
            n = cmd.count_atoms(selection)
            return f"{n} atoms in '{selection}'"

    # ── Rendering ──────────────────────────────────────────────────────────

    @mcp.tool()
    def render(width: int = 800, height: int = 600, ray: bool = True) -> Image:
        """Render current view as an image. ray=True for high quality (slower)."""
        with _pymol_lock:
            return _render_image(width, height, ray=ray)

    @mcp.tool()
    def snapshot(width: int = 800, height: int = 600) -> Image:
        """Quick snapshot without ray tracing. Faster, lower quality."""
        with _pymol_lock:
            return _render_image(width, height, ray=False)

    # ── Metrics (biotite) ──────────────────────────────────────────────────

    @mcp.tool()
    def get_metrics(name: str = "") -> str:
        """Get detailed structure metrics (pLDDT, ipTM, pTM) using biotite."""
        cmd = _ensure_pymol()
        from pymol_claude.metrics import extract_record

        with _pymol_lock:
            objects = cmd.get_object_list()
            if not objects:
                return "No objects loaded"
            if name and name not in objects:
                return f"Object '{name}' not found. Loaded: {', '.join(objects)}"

        targets = [name] if name else objects
        results = []
        for obj_name in targets:
            # Try to find the file path from PyMOL
            # cmd.get() doesn't directly give us the path, so check common patterns
            with _pymol_lock:
                # Use get_object_list and try to find file
                # PyMOL doesn't expose the original path easily, so we check triage state
                pass

            triage = _get_triage()
            record = triage.records.get(obj_name)
            if record is None:
                # Try to find from triage by stem matching
                for fname, rec in triage.records.items():
                    if rec.name == obj_name:
                        record = rec
                        break

            if record is not None:
                results.append(record.format_report())
            else:
                results.append(f"{obj_name}: no metrics available (load via triage or provide file path)")

        return "\n\n".join(results)

    @mcp.tool()
    def find_low_confidence(name: str = "", threshold: int = 70) -> str:
        """Find contiguous low-pLDDT regions in a structure."""
        from pymol_claude.metrics import find_low_confidence as _find_low

        triage = _get_triage()
        if name:
            for fname, rec in triage.records.items():
                if rec.name == name or fname == name:
                    return _find_low(rec, threshold)
            return f"No metrics for '{name}'. Load the structure directory first."

        cmd = _ensure_pymol()
        with _pymol_lock:
            objects = cmd.get_object_list()

        results = []
        for obj in objects:
            for fname, rec in triage.records.items():
                if rec.name == obj:
                    results.append(_find_low(rec, threshold))
                    break
            else:
                results.append(f"{obj}: no metrics available")
        return "\n\n".join(results) if results else "No objects loaded"

    @mcp.tool()
    def compare_all() -> str:
        """Compare all loaded objects by pLDDT — sorted table."""
        triage = _get_triage()
        if not triage.records:
            return "No structures loaded in triage. Use load_directory first."

        records = sorted(
            triage.records.values(),
            key=lambda r: r.mean_plddt if r.mean_plddt is not None else -1,
            reverse=True,
        )

        lines = [f"{'Name':<30} {'pLDDT':>8} {'ipTM':>8} {'pTM':>8} {'Chains':>6} {'Res':>6}"]
        lines.append("-" * 70)
        for r in records:
            plddt = f"{r.mean_plddt:.1f}" if r.mean_plddt is not None else "—"
            iptm = f"{r.iptm:.3f}" if r.iptm is not None else "—"
            ptm = f"{r.ptm:.3f}" if r.ptm is not None else "—"
            lines.append(
                f"{r.name:<30} {plddt:>8} {iptm:>8} {ptm:>8} {len(r.chains):>6} {r.n_residues:>6}"
            )
        return "\n".join(lines)

    # ── Triage ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def load_directory(path: str) -> str:
        """Scan a directory for structure files, extract metrics for all. Sets up triage navigation."""
        triage = _get_triage()
        return triage.load_directory(path)

    @mcp.tool()
    def next_structure() -> Image:
        """Advance to next structure, load it, color by pLDDT, and render."""
        triage = _get_triage()
        p = triage.next()
        if p is None:
            raise ValueError("No structures loaded. Use load_directory first.")
        with _pymol_lock:
            return _triage_render(p)

    @mcp.tool()
    def prev_structure() -> Image:
        """Go back to previous structure, load it, color by pLDDT, and render."""
        triage = _get_triage()
        p = triage.prev()
        if p is None:
            raise ValueError("No structures loaded. Use load_directory first.")
        with _pymol_lock:
            return _triage_render(p)

    @mcp.tool()
    def go_to(number: int) -> Image:
        """Jump to Nth structure (1-indexed), load it, and render."""
        triage = _get_triage()
        p = triage.go_to(number)
        if p is None:
            raise ValueError("No structures loaded. Use load_directory first.")
        with _pymol_lock:
            return _triage_render(p)

    @mcp.tool()
    def current() -> Image:
        """Re-render the current structure without advancing."""
        triage = _get_triage()
        p = triage.current_path()
        if p is None:
            raise ValueError("No structures loaded. Use load_directory first.")
        with _pymol_lock:
            return _triage_render(p)

    @mcp.tool()
    def flag(note: str = "") -> str:
        """Flag the current structure with an optional note."""
        triage = _get_triage()
        return triage.flag(note)

    @mcp.tool()
    def show_flags() -> str:
        """List all flagged structures."""
        triage = _get_triage()
        return triage.show_flags()

    @mcp.tool()
    def export_flags() -> str:
        """Export all flags as JSON (with metrics)."""
        triage = _get_triage()
        return triage.export_flags()

    @mcp.tool()
    def filter(min_plddt: float = 0, max_plddt: float = 100) -> str:
        """Filter triage structures by pLDDT range."""
        triage = _get_triage()
        return triage.filter(min_plddt, max_plddt)

    # ── Escape hatch ───────────────────────────────────────────────────────

    @mcp.tool()
    def run(code: str) -> str:
        """Execute arbitrary PyMOL/Python code. For PyMOL commands, prefix with 'cmd.'.
        For arbitrary Python, just write the code. Output from print() is captured and returned."""
        cmd = _ensure_pymol()
        buf = io.StringIO()
        with _pymol_lock:
            try:
                with redirect_stdout(buf):
                    # Try as PyMOL command first (if it looks like one)
                    if "\n" not in code and not code.strip().startswith(("import", "from", "def", "class")):
                        try:
                            cmd.do(code)
                        except Exception:
                            exec(code, {"cmd": cmd, "__builtins__": __builtins__})
                    else:
                        exec(code, {"cmd": cmd, "__builtins__": __builtins__})
            except Exception as e:
                return f"Error: {e}"

        output = buf.getvalue()
        return output if output.strip() else "OK"

    return mcp
