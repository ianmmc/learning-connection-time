"""
Instructional Minute Metric
Learning Connection Time Calculator

A toolkit for calculating and analyzing Learning Connection Time (LCT)
across school districts using federal and state education data.
"""

__version__ = "0.1.0"
__author__ = "Ian McCullough"
__project__ = "Reducing the Ratio"

from .calculators.lct_calculator import calculate_lct, LCTCalculator

__all__ = [
    "calculate_lct",
    "LCTCalculator",
]
