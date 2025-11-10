# -*- coding: utf-8 -*-
"""
Type stubs for native_compute module.

This module provides batch numerical operations and hash computation.
"""

from typing import Any, List, Union, Optional

# Availability flags
COMPUTE_AVAILABLE: bool
PREFIX_SUM_AVAILABLE: bool

def batch_compute(
    data: List[Union[int, float]],
    operation: Optional[str] = None,
    operands: Optional[List[Union[int, float]]] = None
) -> List[Union[int, float]]:
    """
    Perform batch numerical operations.

    Args:
        data: List of numbers to operate on
        operation: Optional operation type (default: "add")
        operands: Optional additional operands for operations

    Returns:
        List of computed results
    """
    ...

def batch_hash(
    data: List[str],
    algorithm: Optional[str] = None
) -> List[str]:
    """
    Compute hashes for a batch of strings.

    Args:
        data: List of strings to hash
        algorithm: Hash algorithm to use (default: "md5")

    Returns:
        List of hash strings
    """
    ...

def batch_get_price(
    data: bytes,
    start_pos: int,
    count: int
) -> List[Union[int, float]]:
    """
    Parse price data from binary format for TDX protocol.

    Args:
        data: Binary price data buffer
        start_pos: Starting position in data buffer
        count: Number of price values to extract

    Returns:
        List of parsed price values
    """
    ...

def batch_validate_iso_dates(dates: List[str]) -> List[bool]:
    """
    Validate a batch of ISO date strings.

    Args:
        dates: List of date strings in YYYY-MM-DD format

    Returns:
        List of boolean validation results
    """
    ...

def batch_compare_dates(
    dates: List[str],
    reference_date: str
) -> List[int]:
    """
    Compare a batch of dates against a reference date.

    Args:
        dates: List of ISO date strings (YYYY-MM-DD format)
        reference_date: Reference date string for comparison

    Returns:
        List of comparison results (-1=before, 0=equal, 1=after, -999=invalid)
    """
    ...

def prefix_sum_scale(
    diffs: List[Union[int, float]],
    operation: Optional[str] = None,
    custom_scale: Optional[float] = None
) -> List[Union[int, float]]:
    """
    Compute prefix sums with scaling.

    Args:
        diffs: List of differences/values
        operation: Optional operation type
        custom_scale: Optional custom scaling factor

    Returns:
        List of scaled prefix sums
    """
    ...
