"""AI-powered tool availability scan (PRD §3.2). Matches against verified inventory."""
from pathlib import Path
import pandas as pd
from rapidfuzz import fuzz

import config
from excel_utils import load_verified_inventory, normalize_columns

STATUS_AVAILABLE = "Available"
STATUS_UNAVAILABLE = "Unavailable"
STATUS_REVIEW = "Requires further review"

def _similarity(tool: str, vendor: str, inv_row: dict) -> float:
    """Return 0-100 similarity between user row and inventory row."""
    t = fuzz.ratio((tool or "").lower(), (inv_row.get("Tool Name") or "").lower())
    v = fuzz.ratio((vendor or "").lower(), (inv_row.get("Vendor") or "").lower())
    return (t + v) / 2

def _best_match(row: dict, inventory: pd.DataFrame) -> tuple[str, float]:
    """Best match status and score for one row."""
    tool = row.get("Tool Name") or ""
    vendor = row.get("Vendor") or ""
    if not tool and not vendor:
        return STATUS_REVIEW, 0.0
    best_score = 0.0
    inv_list = inventory.to_dict("records")
    for inv_row in inv_list:
        s = _similarity(tool, vendor, inv_row)
        if s > best_score:
            best_score = s
    if best_score >= config.MATCH_THRESHOLD_AVAILABLE:
        return STATUS_AVAILABLE, best_score
    if best_score >= config.MATCH_THRESHOLD_REVIEW:
        return STATUS_REVIEW, best_score
    return STATUS_UNAVAILABLE, best_score

def run_scan(user_df: pd.DataFrame, verified_stored_path: Path) -> pd.DataFrame:
    """
    Scan each row of user_df against verified inventory.
    Returns dataframe with extra column 'Availability' and optional 'Match Score'.
    """
    inventory = load_verified_inventory(verified_stored_path)
    if inventory is None or len(inventory) == 0:
        # No verified inventory: mark all as requires review
        result = user_df.copy()
        result["Availability"] = STATUS_REVIEW
        result["Match Score %"] = 0
        return result
    inventory = normalize_columns(inventory)
    result = user_df.copy()
    statuses = []
    scores = []
    for _, row in result.iterrows():
        st, score = _best_match(row.to_dict(), inventory)
        statuses.append(st)
        scores.append(round(score, 1))
    result["Availability"] = statuses
    result["Match Score %"] = scores
    return result


# --- Single tool name lookup (user types tool name → Yes/No + status) ---
LOOKUP_MIN_SCORE = 70  # fuzzy match threshold for "found"

def lookup_tool(tool_name: str, verified_stored_path: Path) -> list[dict]:
    """
    Search verified inventory by tool name (fuzzy).
    Returns list of matching rows as dicts (Tool Name, Vendor, Version, Notes, Status if present).
    Empty list = not found.
    """
    if not (tool_name or "").strip():
        return []
    inventory = load_verified_inventory(verified_stored_path)
    if inventory is None or len(inventory) == 0:
        return []
    inventory = normalize_columns(inventory)
    query = (tool_name or "").strip().lower()
    matches = []
    for _, row in inventory.iterrows():
        name = str(row.get("Tool Name") or "").lower()
        score = fuzz.ratio(query, name)
        if score >= LOOKUP_MIN_SCORE:
            rec = row.to_dict()
            rec = {k: ("" if pd.isna(v) else str(v)) for k, v in rec.items()}
            if not rec.get("Status"):
                rec["Status"] = "Available"
            matches.append((score, rec))
    matches.sort(key=lambda x: -x[0])
    return [m[1] for m in matches]
