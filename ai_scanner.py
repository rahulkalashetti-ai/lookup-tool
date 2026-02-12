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
    t = fuzz.ratio((tool or "").lower(), (inv_row.get("Name") or "").lower())
    v = fuzz.ratio((vendor or "").lower(), (inv_row.get("Vendor Name") or "").lower())
    return (t + v) / 2

def _best_match(row: dict, inventory: pd.DataFrame) -> tuple[str, float]:
    """Best match status and score for one row."""
    tool = row.get("Name") or ""
    vendor = row.get("Vendor Name") or ""
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
LOOKUP_MIN_SCORE = 75       # minimum to count as "found"
LOOKUP_SUGGEST_THRESHOLD = 50   # below LOOKUP_MIN_SCORE, for "Did you mean?"
LOOKUP_MAX_RESULTS = 15
LOOKUP_MAX_SUGGESTIONS = 5


def _normalize(s: str) -> str:
    """Normalize for matching: strip, lower, collapse spaces."""
    if not s or not isinstance(s, str):
        return ""
    return " ".join(str(s).strip().lower().split())


def _score_query_against_name(query: str, tool_name: str, vendor: str = "") -> float:
    """
    Best similarity score (0-100) of query against inventory row.
    Uses exact match, partial (query in name), and token set (word overlap).
    """
    if not query:
        return 0.0
    q = _normalize(query)
    name = _normalize(tool_name)
    ven = _normalize(vendor)
    if not name and not ven:
        return 0.0
    # Exact match on tool name
    if q == name:
        return 100.0
    # Exact match on vendor (e.g. user typed vendor name)
    if ven and q == ven:
        return 95.0
    # Query contained in tool name (e.g. "Slack" vs "Slack Enterprise")
    partial_name = fuzz.partial_ratio(q, name) if name else 0
    # Full string similarity
    ratio_name = fuzz.ratio(q, name) if name else 0
    # Word-order independent (e.g. "Jira Software" vs "Software Jira")
    token_name = fuzz.token_set_ratio(q, name) if name else 0
    # If user query is short, partial and token_set are more forgiving
    score_name = max(ratio_name, partial_name, token_name)
    # If vendor is given, boost when vendor matches
    score_vendor = fuzz.partial_ratio(q, ven) if ven else 0
    # Best of name match or vendor match (don't average; either can be strong)
    return max(score_name, score_vendor * 0.95)


def lookup_tool(
    tool_name: str,
    verified_stored_path: Path,
    vendor_filter: str = "",
) -> list[dict]:
    """
    Search verified inventory by tool name (and optional vendor).
    Returns list of matching rows with 'match_score' (0-100) and standard fields.
    Uses exact match first, then fuzzy (partial + token set) for valid results.
    """
    query = (tool_name or "").strip()
    if not query:
        return []
    inventory = load_verified_inventory(verified_stored_path)
    if inventory is None or len(inventory) == 0:
        return []
    inventory = normalize_columns(inventory)
    q = _normalize(query)
    vendor_norm = _normalize(vendor_filter)
    candidates = []
    for _, row in inventory.iterrows():
        name = str(row.get("Name") or "")
        ven = str(row.get("Vendor Name") or "")
        score = _score_query_against_name(query, name, ven)
        # If user provided vendor filter, require vendor to match reasonably
        if vendor_norm and ven:
            vendor_score = fuzz.partial_ratio(vendor_norm, _normalize(ven))
            if vendor_score < 60:
                score = min(score, 40)  # demote if vendor doesn't match
        if score >= LOOKUP_MIN_SCORE:
            rec = row.to_dict()
            rec = {k: ("" if pd.isna(v) else str(v)) for k, v in rec.items()}
            if not rec.get("Workflow Status"):
                rec["Workflow Status"] = "Available"
            rec["match_score"] = round(score, 0)
            candidates.append((score, rec))
    candidates.sort(key=lambda x: -x[0])
    # Return top N only
    return [c[1] for c in candidates[:LOOKUP_MAX_RESULTS]]


def lookup_suggestions(
    tool_name: str, verified_stored_path: Path, limit: int = LOOKUP_MAX_SUGGESTIONS
) -> list[dict]:
    """
    Return close-but-below-threshold matches for "Did you mean?" when no results.
    """
    query = (tool_name or "").strip()
    if not query:
        return []
    inventory = load_verified_inventory(verified_stored_path)
    if inventory is None or len(inventory) == 0:
        return []
    inventory = normalize_columns(inventory)
    candidates = []
    for _, row in inventory.iterrows():
        name = str(row.get("Name") or "")
        ven = str(row.get("Vendor Name") or "")
        score = _score_query_against_name(query, name, ven)
        if LOOKUP_SUGGEST_THRESHOLD <= score < LOOKUP_MIN_SCORE:
            rec = row.to_dict()
            rec = {k: ("" if pd.isna(v) else str(v)) for k, v in rec.items()}
            rec["match_score"] = round(score, 0)
            candidates.append((score, rec))
    candidates.sort(key=lambda x: -x[0])
    return [c[1] for c in candidates[:limit]]
