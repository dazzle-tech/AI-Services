"""Time utility functions"""
from datetime import datetime


def is_within_window(timestamp: datetime, window_start: datetime, window_end: datetime) -> bool:
    """Check if timestamp is within the time window"""
    return window_start <= timestamp <= window_end


def validate_timestamps_in_window(entries: list, window_start: datetime, 
                                 window_end: datetime) -> tuple[list, list]:
    """
    Validate timestamps and separate valid from invalid entries.
    
    Returns:
        (valid_entries, warnings) where warnings list contains messages about invalid entries
    """
    valid_entries = []
    warnings = []
    
    for entry in entries:
        if hasattr(entry, 'timestamp'):
            if not is_within_window(entry.timestamp, window_start, window_end):
                warnings.append(
                    f"Entry timestamp {entry.timestamp.isoformat()} outside time window, ignored"
                )
                continue
        valid_entries.append(entry)
    
    return valid_entries, warnings
