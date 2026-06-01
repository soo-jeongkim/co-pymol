"""Tests for structure metrics (gemmi only — no PyMOL).

Unit tests for the parsing functions in ``pylot.core.metrics``: that each one
returns the right values for AF2/AF3/plain fixtures and degrades gracefully on
bad input. These exercise the functions in isolation — they are not an
end-to-end test of the metric-extraction workflow.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pylot.core.metrics import (
    StructureRecord,
    extract_record,
    find_low_confidence,
    find_sibling_json,
    metrics_from_cif,
)

FIXTURES = Path(__file__).parent / "fixtures"
PLAIN_PDB = FIXTURES / "plain" / "structure.pdb"
AF2_CIF = FIXTURES / "af2" / "prediction.cif"
AF3_CIF = FIXTURES / "af3" / "run_model_0.cif"


class TestMetricsFromCif:
    def test_non_cif_returns_empty(self, tmp_path: Path) -> None:
        pdb = tmp_path / "x.pdb"
        pdb.write_text("HEADER\nEND\n")
        assert metrics_from_cif(pdb) == {}

    def test_invalid_cif_returns_empty(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.cif"
        bad.write_text("not valid mmcif {")
        assert metrics_from_cif(bad) == {}

    def test_af3_embedded_metrics(self) -> None:
        m = metrics_from_cif(AF3_CIF)
        assert m["ptm"] == pytest.approx(0.88)
        assert m["iptm"] == pytest.approx(0.72)
        assert m["ranking_score"] == pytest.approx(0.87)
        assert m["pae"].shape == (2, 2)
        assert m["pae"][0, 0] == pytest.approx(0.0)  # PAE diagonal is 0
        assert m["pae"][0, 1] == pytest.approx(2.5)

    def test_af2_cif_has_no_ma_qa_metrics(self) -> None:
        assert metrics_from_cif(AF2_CIF) == {}


class TestFindSiblingJson:
    def test_af2_pae_from_stem_sibling_bare_ranking_ignored(self) -> None:
        # PAE comes from the stem-specific `prediction_pae.json`. The ipTM/pTM
        # live in a bare-named `ranking_debug.json` (no stem), which is
        # intentionally NOT loaded — a bare file can't be tied to one structure,
        # so in a flat batch it would leak onto unrelated predictions.
        extra = find_sibling_json(AF2_CIF)
        assert extra["pae"].shape == (4, 4)
        assert extra["pae"][0, 0] == pytest.approx(0.0)  # PAE diagonal is 0
        assert extra["pae"][0, 1] == pytest.approx(3.0)  # off-diagonal: orientation
        assert "iptm" not in extra
        assert "ptm" not in extra
        assert "ranking_score" not in extra

    def test_af3_server_naming(self) -> None:
        extra = find_sibling_json(AF3_CIF)
        assert extra["pae"].shape == (2, 2)
        assert extra["pae"][0, 0] == pytest.approx(0.0)  # PAE diagonal is 0
        assert extra["pae"][0, 1] == pytest.approx(8.0)  # off-diagonal: orientation
        assert extra["ptm"] == pytest.approx(0.5)
        assert extra["ranking_score"] == pytest.approx(0.4)
        assert "iptm" not in extra  # null in summary JSON

    def test_plain_pdb_has_no_siblings(self) -> None:
        assert find_sibling_json(PLAIN_PDB) == {}

    def test_invalid_pae_json_skips_pae_but_loads_confidence(
        self, tmp_path: Path
    ) -> None:
        stem = tmp_path / "model_0.cif"
        stem.write_text("data_x\n")
        (tmp_path / "model_0_pae.json").write_text("{not json")
        (tmp_path / "model_0_summary_confidences.json").write_text('{"ptm": 0.99}')
        extra = find_sibling_json(stem)
        assert "pae" not in extra
        assert extra["ptm"] == pytest.approx(0.99)


class TestExtractRecord:
    def test_plain_pdb_no_plddt_or_metrics(self) -> None:
        rec = extract_record(PLAIN_PDB)
        assert rec.name == "structure"
        assert rec.chains == ["A"]
        assert rec.n_residues == 3
        assert rec.plddt is None
        assert rec.pae is None
        assert rec.ptm is None
        assert rec.iptm is None
        assert rec.sort_key() == float("-inf")

    def test_af2_from_cif_and_json(self) -> None:
        rec = extract_record(AF2_CIF)
        assert rec.chains == ["A"]
        assert rec.n_residues == 4
        assert rec.plddt is not None
        np.testing.assert_allclose(rec.plddt, [40, 55, 85, 92])
        assert rec.mean_plddt == pytest.approx(68.0)
        # ipTM/pTM come only from the bare `ranking_debug.json`, which is no
        # longer auto-loaded (see test_af2_pae_from_stem_sibling_bare_ranking_ignored).
        assert rec.ptm is None
        assert rec.iptm is None
        assert rec.ranking_score is None
        assert rec.pae.shape == (4, 4)

    def test_af3_cif_overrides_sibling_json(self) -> None:
        rec = extract_record(AF3_CIF)
        assert rec.n_residues == 2
        assert rec.ptm == pytest.approx(0.88)
        assert rec.iptm == pytest.approx(0.72)
        assert rec.ranking_score == pytest.approx(0.87)
        # cif's embedded PAE (off-diagonal 2.5) wins over the sibling JSON's 8.0.
        assert rec.pae[0, 1] == pytest.approx(2.5)

    def test_custom_name(self) -> None:
        rec = extract_record(PLAIN_PDB, name="custom")
        assert rec.name == "custom"

    def test_unreadable_cif_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "nope.cif"
        bad.write_text("not mmcif")
        with pytest.raises((RuntimeError, ValueError)):
            extract_record(bad)


class TestFindLowConfidence:
    def test_no_plddt(self) -> None:
        rec = extract_record(PLAIN_PDB)
        assert find_low_confidence(rec) == "structure: no pLDDT data available"

    def test_af2_regions_below_70(self) -> None:
        rec = extract_record(AF2_CIF)
        report = find_low_confidence(rec, threshold=70)
        assert "1 low-confidence regions" in report
        assert "residues 1-2 (2 residues, mean pLDDT=47.5)" in report

    def test_af3_single_residue_region(self) -> None:
        rec = extract_record(AF3_CIF)
        report = find_low_confidence(rec, threshold=70)
        assert "1 low-confidence regions" in report
        assert "residues 2-2 (1 residues, mean pLDDT=45.0)" in report

    def test_all_confident(self) -> None:
        rec = StructureRecord(
            name="high",
            path=AF2_CIF,
            chains=["A"],
            n_residues=2,
            plddt=np.array([90.0, 95.0]),
        )
        assert find_low_confidence(rec, threshold=70) == (
            "high: no regions below pLDDT 70"
        )
