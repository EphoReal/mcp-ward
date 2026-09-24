"""MCP tool contract compatibility lens."""
from .diff import DiffReport, Finding, diff_surfaces
from .snapshot import SnapshotError, load_document, normalize_surface, snapshot_bytes

__all__ = [
    "DiffReport",
    "Finding",
    "SnapshotError",
    "diff_surfaces",
    "load_document",
    "normalize_surface",
    "snapshot_bytes",
]
__version__ = "0.1.0"
