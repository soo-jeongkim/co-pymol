"""Shared constants for co-pymol."""

DEFAULT_PORT = 8766
DEFAULT_HOST = "127.0.0.1"

# AlphaFold DB discrete pLDDT bin colors (not a continuous gradient).
PLDDT_PALETTE = {
    "very_high": "0x0053D6",  # >90
    "confident": "0x65CBF3",  # 70–90
    "low": "0xFFDB13",  # 50–70
    "very_low": "0xFF7D45",  # <50
}
STRUCTURE_EXTENSIONS = {".cif", ".mmcif", ".pdb", ".ent"}

RENDER_POLL_ATTEMPTS = 50
RENDER_POLL_INTERVAL_S = 0.1
