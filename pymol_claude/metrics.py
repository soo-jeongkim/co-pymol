"""Structure metadata extraction using biotite (not PyMOL)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class StructureRecord:
    name: str
    path: Path
    kind: str  # af2_single | af3_complex | crystal | unknown
    chains: list[str]
    n_residues: int
    plddt: Optional[np.ndarray] = field(default=None, repr=False)  # per-residue, 0-100
    pae: Optional[np.ndarray] = field(default=None, repr=False)
    iptm: Optional[float] = None
    ptm: Optional[float] = None

    @property
    def mean_plddt(self) -> Optional[float]:
        if self.plddt is not None and len(self.plddt) > 0:
            return float(np.mean(self.plddt))
        return None

    @property
    def plddt_summary(self) -> str:
        if self.plddt is None:
            return "no pLDDT"
        mean = self.mean_plddt
        high = float(np.sum(self.plddt >= 90) / len(self.plddt) * 100)
        low = float(np.sum(self.plddt < 50) / len(self.plddt) * 100)
        return f"mean={mean:.1f}, {high:.0f}% very high (>=90), {low:.0f}% very low (<50)"

    def format_report(self) -> str:
        lines = [
            f"Structure: {self.name}",
            f"  File: {self.path.name}",
            f"  Type: {self.kind}",
            f"  Chains: {', '.join(self.chains)}",
            f"  Residues: {self.n_residues}",
        ]
        if self.plddt is not None:
            lines.append(f"  pLDDT: {self.plddt_summary}")
            lines.append(f"    Interpretation: "
                         f">90 very high confidence, "
                         f"70-90 confident, "
                         f"50-70 low confidence, "
                         f"<50 very low / disordered")
        if self.ptm is not None:
            lines.append(f"  pTM: {self.ptm:.3f}")
        if self.iptm is not None:
            lines.append(f"  ipTM: {self.iptm:.3f}")
            lines.append(f"    Interpretation: "
                         f">0.8 confident interaction, "
                         f"0.6-0.8 possible, "
                         f"<0.6 unlikely")
        if self.pae is not None:
            lines.append(f"  PAE: mean={float(np.mean(self.pae)):.1f} A")
        return "\n".join(lines)


def _detect_kind(path: Path) -> str:
    """Detect structure source from filename markers."""
    stem = path.stem.lower()
    markers = {
        "af3": "af3_complex",
        "alphafold3": "af3_complex",
        "af2": "af2_single",
        "alphafold2": "af2_single",
        "alphafold": "af2_single",
        "af_": "af2_single",
        "colabfold": "af2_single",
        "ranked_": "af2_single",
        "fold_": "unknown",
        "esm": "unknown",
        "boltz": "unknown",
        "chai": "unknown",
        "omegafold": "unknown",
    }
    for marker, kind in markers.items():
        if marker in stem:
            return kind
    return "unknown"


def _find_sibling_json(path: Path) -> dict:
    """Search for PAE/confidence JSON files alongside the structure."""
    parent = path.parent
    stem = path.stem
    extra: dict = {}

    # Patterns for PAE files
    pae_patterns = [
        f"{stem}_pae.json",
        f"pae_{stem}.json",
        f"{stem}_full_data_0.json",
    ]
    for pat in pae_patterns:
        pae_path = parent / pat
        if pae_path.exists():
            try:
                data = json.loads(pae_path.read_text())
                if isinstance(data, list) and len(data) > 0:
                    if "predicted_aligned_error" in data[0]:
                        extra["pae"] = np.array(data[0]["predicted_aligned_error"])
                elif isinstance(data, dict) and "predicted_aligned_error" in data:
                    extra["pae"] = np.array(data["predicted_aligned_error"])
            except (json.JSONDecodeError, KeyError):
                pass
            break

    # Patterns for confidence/ranking files
    conf_patterns = [
        f"{stem}_summary_confidences.json",
        "summary_confidences.json",
        "ranking_debug.json",
        f"{stem}_confidences.json",
    ]
    for pat in conf_patterns:
        conf_path = parent / pat
        if conf_path.exists():
            try:
                data = json.loads(conf_path.read_text())
                if "iptm" in data:
                    extra["iptm"] = float(data["iptm"])
                if "ptm" in data:
                    extra["ptm"] = float(data["ptm"])
                if "iptm+ptm" in data and "iptm" not in data:
                    extra["iptm"] = float(data["iptm+ptm"])
            except (json.JSONDecodeError, KeyError):
                pass
            break

    return extra


def extract_record(path: Path, name: Optional[str] = None) -> StructureRecord:
    """Extract structure metadata using biotite."""
    import biotite.structure.io as io

    path = Path(path)
    if name is None:
        name = path.stem

    kind = _detect_kind(path)

    # Load structure with biotite
    try:
        if path.suffix.lower() in (".cif", ".mmcif"):
            import biotite.structure.io.pdbx as pdbx
            file = pdbx.CIFFile.read(str(path))
            block = list(file.values())[0]
            atoms = pdbx.get_structure(block, model=1)
        else:
            import biotite.structure.io.pdb as pdb_io
            file = pdb_io.PDBFile.read(str(path))
            atoms = pdb_io.get_structure(file, model=1)
    except Exception as e:
        return StructureRecord(
            name=name, path=path, kind=kind,
            chains=[], n_residues=0,
        )

    # Get CA atoms for per-residue analysis
    ca_mask = atoms.atom_name == "CA"
    ca_atoms = atoms[ca_mask]

    chains = list(dict.fromkeys(ca_atoms.chain_id))  # unique, ordered
    n_residues = len(ca_atoms)

    # Check B-factor column for pLDDT
    plddt = None
    if n_residues > 0:
        b_factors = ca_atoms.b_factor
        if len(b_factors) > 0:
            bmin, bmax = float(np.min(b_factors)), float(np.max(b_factors))
            std = float(np.std(b_factors))
            # pLDDT is 0-100 with meaningful variance
            if 0 <= bmin and bmax <= 100 and std > 0.5:
                plddt = b_factors.astype(np.float64)
                if kind == "unknown":
                    kind = "af2_single" if len(chains) == 1 else "af3_complex"

    # Look for sibling JSON files
    sibling = _find_sibling_json(path)

    return StructureRecord(
        name=name,
        path=path,
        kind=kind,
        chains=chains,
        n_residues=n_residues,
        plddt=plddt,
        pae=sibling.get("pae"),
        iptm=sibling.get("iptm"),
        ptm=sibling.get("ptm"),
    )


def find_low_confidence(record: StructureRecord, threshold: int = 70) -> str:
    """Find contiguous regions below pLDDT threshold."""
    if record.plddt is None:
        return f"{record.name}: no pLDDT data available"

    regions = []
    in_region = False
    start = 0

    for i, val in enumerate(record.plddt):
        if val < threshold:
            if not in_region:
                start = i
                in_region = True
        else:
            if in_region:
                regions.append((start, i - 1, float(np.mean(record.plddt[start:i]))))
                in_region = False

    if in_region:
        regions.append((start, len(record.plddt) - 1,
                        float(np.mean(record.plddt[start:]))))

    if not regions:
        return f"{record.name}: no regions below pLDDT {threshold}"

    lines = [f"{record.name}: {len(regions)} low-confidence regions (threshold={threshold}):"]
    for start, end, mean_val in regions:
        length = end - start + 1
        lines.append(f"  residues {start + 1}-{end + 1} ({length} residues, mean pLDDT={mean_val:.1f})")

    return "\n".join(lines)
