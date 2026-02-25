"""Time utility functions."""

from datetime import datetime
from typing import Optional


def parse_iso8601(timestamp: str) -> Optional[datetime]:
    """Parse ISO 8601 timestamp string to datetime."""
    try:
        # Try standard ISO format
        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError:
        try:
            # Try without timezone
            return datetime.fromisoformat(timestamp)
        except ValueError:
            return None


def compare_timestamps(ts1: str, ts2: str) -> int:
    """Compare two ISO 8601 timestamps.
    
    Returns:
        -1 if ts1 < ts2
        0 if ts1 == ts2
        1 if ts1 > ts2
    """
    dt1 = parse_iso8601(ts1)
    dt2 = parse_iso8601(ts2)
    
    if dt1 is None or dt2 is None:
        return 0
    
    if dt1 < dt2:
        return -1
    elif dt1 > dt2:
        return 1
    else:
        return 0

