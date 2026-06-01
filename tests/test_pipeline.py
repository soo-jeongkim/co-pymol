"""End-to-end pipeline tests for the triage + metrics workflow.

Unlike ``test_metrics.py`` (which exercises the parsing functions in isolation),
these drive the whole flow the way the MCP tools do: scan a directory of mixed
predictions, extract every record, sort/navigate/flag/filter through
``TriageState``, and resolve metrics back out through ``AppSession`` — the exact
seam the thin ``tools/`` wrappers call into.

The throughline is *binding*: a two-chain complex fixture (``dimer.cif``) carries
an interface (cross-chain PAE) and an ipTM score, and these tests assert that the
binding signal survives end to end — from directory scan to the registry lookup a
client would hit via ``get_metrics`` / ``compare_all``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from pylot.core.session import AppSession
from pylot.core.triage import TriageState

FIXTURES = Path(__file__).parent / "fixtures"

# Each entry is (subdir, filenames-to-copy). The first file of each is the
# structure; the rest are stem-specific siblings the pipeline must discover.
#
# NB: af2's ``ranking_debug.json`` is bare-named (no stem) and is no longer
# auto-loaded, so af2 here contributes pLDDT + PAE (via its stem-specific
# ``prediction_pae.json``) but no ipTM/pTM. The bare-file behavior is pinned
# directly in ``test_bare_named_sibling_does_not_leak`` below.
_FIXTURE_FILES = {
    "plain": ["structure.pdb"],
    "af2": ["prediction.cif", "prediction_pae.json"],
    "af3": [
        "run_model_0.cif",
        "run_full_data_0.json",
        "run_summary_confidences_0.json",
    ],
    "complex": ["dimer.cif"],
}


@pytest.fixture
def eval_dir(tmp_path: Path) -> Path:
    """A flat directory of mixed predictions, as a real eval batch would look."""
    for subdir, names in _FIXTURE_FILES.items():
        for name in names:
            shutil.copy(FIXTURES / subdir / name, tmp_path / name)
    return tmp_path


# Mean pLDDT of each fixture, for asserting sort order:
#   dimer 91.25  >  af2 68.0  >  af3 66.5  >  structure (unscored)
EXPECTED_ORDER = ["dimer", "prediction", "run_model_0", "structure"]


class TestLoadDirectory:
    def test_scans_and_extracts_every_structure(self, eval_dir: Path) -> None:
        state = TriageState()
        msg = state.load_directory(eval_dir)

        assert "Loaded 4 structures" in msg
        assert len(state.files) == 4
        assert set(state.records) == {
            "structure.pdb",
            "prediction.cif",
            "run_model_0.cif",
            "dimer.cif",
        }

    def test_summary_is_sorted_by_plddt_best_first(self, eval_dir: Path) -> None:
        state = TriageState()
        msg = state.load_directory(eval_dir)
        # The dimer (best pLDDT) and its ipTM should headline the summary.
        first_line = msg.splitlines()[1].strip()
        assert first_line.startswith("dimer:")
        assert "ipTM=0.850" in first_line

    def test_empty_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            TriageState().load_directory(tmp_path)

    def test_missing_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(NotADirectoryError):
            TriageState().load_directory(tmp_path / "does-not-exist")


class TestNavigation:
    def test_walks_structures_in_sorted_order(self, eval_dir: Path) -> None:
        state = TriageState()
        state.load_directory(eval_dir)
        # Navigation order follows the on-disk (alphabetical) file order, not the
        # summary sort: dimer, prediction, run_model_0, structure.
        names = []
        state.go_to(1)
        names.append(state.current_record().name)
        for _ in range(3):
            state.next()
            names.append(state.current_record().name)
        assert names == ["dimer", "prediction", "run_model_0", "structure"]

    def test_prev_and_bounds_clamp(self, eval_dir: Path) -> None:
        state = TriageState()
        state.load_directory(eval_dir)
        state.go_to(99)  # clamps to last
        assert state.current_record().name == "structure"
        for _ in range(10):  # over-rewinding stays at first
            state.prev()
        assert state.current_record().name == "dimer"


class TestBindingSurvivesPipeline:
    """The binding signal must reach the client unchanged through every layer."""

    def test_complex_has_two_chains_and_an_interface(self, eval_dir: Path) -> None:
        state = TriageState()
        state.load_directory(eval_dir)
        rec = state.records["dimer.cif"]

        assert rec.chains == ["A", "B"]
        # PAE diagonal is 0 by definition (a residue aligned on itself).
        np.testing.assert_allclose(np.diag(rec.pae), 0.0)
        # Cross-chain (A<->B) PAE block should be markedly worse than the
        # intra-chain blocks — that contrast *is* the interface.
        interface = rec.pae[0:2, 2:4]
        intra_a = rec.pae[0:2, 0:2]
        assert float(interface.mean()) > float(intra_a.mean())
        assert float(interface.mean()) == pytest.approx(5.75)

    def test_iptm_flows_through_to_registry(self, eval_dir: Path) -> None:
        session = AppSession()
        session.triage.load_directory(eval_dir)
        session.sync_metrics_from_triage()

        # This is the exact path get_metrics / compare_all resolve through.
        rec = session.record_for_obj("dimer")
        assert rec is not None
        assert rec.iptm == pytest.approx(0.85)
        assert rec.ptm == pytest.approx(0.80)
        assert "ipTM: 0.850" in rec.format_report()
        assert ">0.8 confident interaction" in rec.format_report()

    def test_monomer_has_no_binding_score(self, eval_dir: Path) -> None:
        session = AppSession()
        session.triage.load_directory(eval_dir)
        session.sync_metrics_from_triage()
        # A single-chain prediction has no interface, hence no ipTM.
        rec = session.record_for_obj("structure")
        assert rec is not None
        assert rec.chains == ["A"]
        assert rec.iptm is None


class TestRegistrySync:
    def test_every_record_resolvable_by_object_name(self, eval_dir: Path) -> None:
        session = AppSession()
        session.triage.load_directory(eval_dir)
        session.sync_metrics_from_triage()

        records = session.metrics.all_records()
        assert len(records) == 4
        # Registry is keyed by file *stem* (the PyMOL object name).
        for stem in EXPECTED_ORDER:
            assert session.record_for_obj(stem) is not None

    def test_compare_all_ordering_by_plddt(self, eval_dir: Path) -> None:
        from pylot.core.metrics import StructureRecord

        session = AppSession()
        session.triage.load_directory(eval_dir)
        session.sync_metrics_from_triage()

        ranked = sorted(
            session.metrics.all_records(),
            key=StructureRecord.sort_key,
            reverse=True,
        )
        assert [r.name for r in ranked] == EXPECTED_ORDER


class TestFlaggingAndFiltering:
    def test_flag_export_captures_binding_score(self, eval_dir: Path) -> None:
        state = TriageState()
        state.load_directory(eval_dir)
        state.go_to(1)  # dimer
        state.flag("good binder")

        exported = json.loads(state.export_flags())
        assert len(exported) == 1
        entry = exported[0]
        assert entry["name"] == "dimer"
        assert entry["note"] == "good binder"
        assert entry["iptm"] == pytest.approx(0.85)
        assert entry["mean_plddt"] == pytest.approx(91.25)

    def test_filter_keeps_high_confidence_and_drops_unscored(
        self, eval_dir: Path
    ) -> None:
        state = TriageState()
        state.load_directory(eval_dir)

        # [60, 100] keeps dimer/af2/af3; the unscored plain PDB is excluded.
        msg = state.filter(60, 100)
        assert "3/4 structures" in msg
        assert state.count == 3
        kept = {state.records[state.files[i].name].name for i in state.active_indices}
        assert "structure" not in kept

    def test_tight_filter_isolates_the_best_binder(self, eval_dir: Path) -> None:
        state = TriageState()
        state.load_directory(eval_dir)
        state.filter(85, 100)
        assert state.count == 1
        assert state.current_record().name == "dimer"

    def test_filter_can_include_unscored(self, eval_dir: Path) -> None:
        state = TriageState()
        state.load_directory(eval_dir)
        state.filter(60, 100, include_unscored=True)
        assert state.count == 4


def test_bare_named_sibling_does_not_leak(tmp_path: Path) -> None:
    """A stray bare-named ranking file must NOT attach to an unrelated monomer.

    ``ranking_debug.json`` / ``summary_confidences.json`` carry no stem, so they
    can't be tied to a specific structure. They are no longer auto-loaded —
    otherwise, in a flat batch, one job's ipTM/pTM would leak onto every other
    structure that lacks its own stem-specific sibling.
    """
    shutil.copy(FIXTURES / "plain" / "structure.pdb", tmp_path / "structure.pdb")
    shutil.copy(
        FIXTURES / "af2" / "ranking_debug.json", tmp_path / "ranking_debug.json"
    )

    state = TriageState()
    state.load_directory(tmp_path)
    rec = state.records["structure.pdb"]
    # A genuine monomer: the stray ranking file is ignored, no score leaks in.
    assert rec.chains == ["A"]
    assert rec.iptm is None
    assert rec.ptm is None


def test_plddt_array_is_per_residue_across_chains(eval_dir: Path) -> None:
    """Sanity: the complex's pLDDT vector spans both chains in order."""
    state = TriageState()
    state.load_directory(eval_dir)
    rec = state.records["dimer.cif"]
    np.testing.assert_allclose(rec.plddt, [90, 92, 88, 95])
    assert rec.n_residues == 4
