"""Export-format plugin registry.

Each format is a subclass of ExportFormat that knows its metadata (id, label,
file extension, content type) and how to build the file bytes for a given
product list. Formats are auto-registered via the FORMATS dict below.

Adding a new format:
    1. Create a module under backend/services/exports/
    2. Subclass ExportFormat and implement `generate(products)`
    3. Register it in FORMATS below
"""
from typing import Dict, List

from .base import ExportFormat, ProductDict
from .kontur_market import KonturMarketFormat
from .onec_retail import OneCRetailFormat
from .onec_unf import OneCUNFFormat
from .onec_trade import OneCTrade11Format


# Registry: format_id -> ExportFormat instance
FORMATS: Dict[str, ExportFormat] = {
    f.format_id: f
    for f in (
        KonturMarketFormat(),
        OneCRetailFormat(),
        OneCUNFFormat(),
        OneCTrade11Format(),
    )
}


def get_format(format_id: str) -> ExportFormat:
    fmt = FORMATS.get(format_id)
    if fmt is None:
        raise KeyError(f"Unknown export format: {format_id}")
    return fmt


def list_formats() -> List[dict]:
    """Returns a serialisable list of available formats for the API."""
    return [
        {
            "id": f.format_id,
            "label": f.label,
            "description": f.description,
            "extension": f.extension,
            "target": f.target,
        }
        for f in FORMATS.values()
    ]


__all__ = [
    "ExportFormat",
    "ProductDict",
    "FORMATS",
    "get_format",
    "list_formats",
]
