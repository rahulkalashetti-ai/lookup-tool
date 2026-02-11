"""Excel parsing and validation per PRD §3.1, §6."""
from pathlib import Path
import pandas as pd

import config

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names (strip, match required/optional)."""
    df = df.rename(columns=lambda c: str(c).strip())
    return df

def validate_inventory_excel(path: Path) -> tuple[bool, str, pd.DataFrame | None]:
    """
    Validate Infosec inventory file: .xlsx, max 10k rows, required columns.
    Returns (ok, message, dataframe or None).
    """
    if path.suffix.lower() != ".xlsx":
        return False, "File must be .xlsx format", None
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except Exception as e:
        return False, f"Invalid Excel file: {e}", None
    df = normalize_columns(df)
    for col in config.REQUIRED_COLUMNS:
        if col not in df.columns:
            return False, f"Missing required column: {col}", None
    if len(df) > config.MAX_INVENTORY_ROWS:
        return False, f"Maximum {config.MAX_INVENTORY_ROWS} rows allowed", None
    return True, "OK", df

def validate_scan_excel(path: Path) -> tuple[bool, str, pd.DataFrame | None]:
    """Validate user scan file: same template, max 5k rows for scan."""
    if path.suffix.lower() != ".xlsx":
        return False, "File must be .xlsx format", None
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except Exception as e:
        return False, f"Invalid Excel file: {e}", None
    df = normalize_columns(df)
    for col in config.REQUIRED_COLUMNS:
        if col not in df.columns:
            return False, f"Missing required column: {col}. Use the standard template.", None
    if len(df) > config.MAX_SCAN_ROWS:
        return False, f"Maximum {config.MAX_SCAN_ROWS} rows for scan", None
    return True, "OK", df

def load_verified_inventory(stored_path: Path) -> pd.DataFrame | None:
    """Load verified inventory from encrypted storage (used by AI scanner)."""
    from storage import load_encrypted
    import io
    try:
        data = load_encrypted(stored_path)
        return pd.read_excel(io.BytesIO(data), engine="openpyxl")
    except Exception:
        return None
