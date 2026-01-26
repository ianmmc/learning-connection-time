"""
Grade level utility functions for bell schedule enrichment.
"""

from typing import List


def get_expected_grade_levels(gslo: str, gshi: str) -> List[str]:
    """
    Determine expected grade levels based on NCES grade span codes.

    Args:
        gslo: Grade span low (PK, KG, 01-12)
        gshi: Grade span high (PK, KG, 01-12)

    Returns:
        List of grade levels: subset of ['elementary', 'middle', 'high']
    """
    if not gslo or not gshi:
        return ['elementary', 'middle', 'high']  # Default to all

    # Convert to numeric
    def to_num(grade):
        if grade in ('PK', 'pk'):
            return -1
        if grade in ('KG', 'kg'):
            return 0
        try:
            return int(grade)
        except:
            return 0

    low = to_num(gslo)
    high = to_num(gshi)

    levels = []

    # Elementary: serves any of PK-5
    if low <= 5 and high >= 0:
        levels.append('elementary')

    # Middle: serves any of 6-8
    if low <= 8 and high >= 6:
        levels.append('middle')

    # High: serves any of 9-12
    if high >= 9:
        levels.append('high')

    return levels if levels else ['high']  # Default to high if nothing detected
