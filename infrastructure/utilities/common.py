"""
Utility functions for the Instructional Minute Metric project

Common functions used across data processing scripts.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


# State name to abbreviation mapping
STATE_ABBR_MAP = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
    'wisconsin': 'WI', 'wyoming': 'WY', 'district of columbia': 'DC'
}

# Reverse mapping
ABBR_STATE_MAP = {v: k.title() for k, v in STATE_ABBR_MAP.items()}


def standardize_state(state: str) -> Optional[str]:
    """
    Standardize state name or abbreviation to two-letter code
    
    Args:
        state: State name or abbreviation
    
    Returns:
        Two-letter state code or None if not found
    
    Examples:
        >>> standardize_state('California')
        'CA'
        >>> standardize_state('ca')
        'CA'
        >>> standardize_state('New York')
        'NY'
    """
    if not state or pd.isna(state):
        return None
    
    state_str = str(state).strip()
    
    # Check if already an abbreviation
    if len(state_str) == 2:
        abbr = state_str.upper()
        return abbr if abbr in ABBR_STATE_MAP else None
    
    # Try to match full name
    state_lower = state_str.lower()
    return STATE_ABBR_MAP.get(state_lower)


def get_state_name(abbr: str) -> Optional[str]:
    """
    Get full state name from abbreviation
    
    Args:
        abbr: Two-letter state abbreviation
    
    Returns:
        Full state name or None if not found
    
    Examples:
        >>> get_state_name('CA')
        'California'
        >>> get_state_name('NY')
        'New York'
    """
    if not abbr or pd.isna(abbr):
        return None
    
    abbr_upper = str(abbr).strip().upper()
    return ABBR_STATE_MAP.get(abbr_upper)


def load_yaml_config(config_path: Union[str, Path]) -> dict:
    """
    Load a YAML configuration file
    
    Args:
        config_path: Path to YAML file
    
    Returns:
        Dictionary from YAML file
    
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If file is not valid YAML
    """
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path, 'r') as f:
        try:
            config = yaml.safe_load(f)
            return config if config else {}
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML: {e}")


def save_yaml_config(data: dict, config_path: Union[str, Path]):
    """
    Save a dictionary as a YAML file
    
    Args:
        data: Dictionary to save
        config_path: Where to save the file
    """
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def get_project_root() -> Path:
    """
    Get the project root directory
    
    Returns:
        Path to project root
    """
    # Assumes this file is in infrastructure/utilities/
    return Path(__file__).parent.parent.parent


def setup_logging(
    log_level: str = 'INFO',
    log_file: Optional[Path] = None
) -> logging.Logger:
    """
    Set up logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file to write logs to
    
    Returns:
        Configured logger
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger


def validate_required_columns(
    df: pd.DataFrame,
    required_columns: List[str],
    dataset_name: str = "dataset"
) -> bool:
    """
    Validate that a DataFrame has required columns
    
    Args:
        df: DataFrame to validate
        required_columns: List of required column names
        dataset_name: Name for error messages
    
    Returns:
        True if all columns present, False otherwise
    """
    missing = [col for col in required_columns if col not in df.columns]
    
    if missing:
        logger.error(f"{dataset_name} missing required columns: {', '.join(missing)}")
        logger.info(f"Available columns: {', '.join(df.columns)}")
        return False
    
    return True


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default if division would fail
    
    Args:
        numerator: Top number
        denominator: Bottom number
        default: Value to return if division fails
    
    Returns:
        Result of division or default value
    """
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return default
    
    return numerator / denominator


def format_number(value: Union[int, float], decimals: int = 0) -> str:
    """
    Format a number with thousands separators
    
    Args:
        value: Number to format
        decimals: Number of decimal places
    
    Returns:
        Formatted string
    
    Examples:
        >>> format_number(1234567)
        '1,234,567'
        >>> format_number(1234.567, 2)
        '1,234.57'
    """
    if pd.isna(value):
        return "N/A"
    
    return f"{value:,.{decimals}f}"


def create_data_lineage_file(
    output_path: Path,
    source_files: List[Path],
    processing_steps: List[str],
    additional_info: Optional[Dict] = None
):
    """
    Create a metadata file documenting data lineage
    
    Args:
        output_path: Where the processed data was saved
        source_files: List of source files used
        processing_steps: List of processing steps applied
        additional_info: Additional metadata to include
    """
    lineage_path = output_path.parent / f"{output_path.stem}_lineage.yaml"
    
    lineage = {
        'output_file': str(output_path),
        'created': pd.Timestamp.now().isoformat(),
        'source_files': [str(f) for f in source_files],
        'processing_steps': processing_steps,
    }
    
    if additional_info:
        lineage.update(additional_info)
    
    save_yaml_config(lineage, lineage_path)
    logger.info(f"Data lineage saved: {lineage_path}")


def find_files_by_pattern(
    directory: Path,
    pattern: str = "*.csv",
    recursive: bool = False
) -> List[Path]:
    """
    Find files matching a pattern
    
    Args:
        directory: Directory to search
        pattern: Glob pattern to match
        recursive: Search recursively if True
    
    Returns:
        List of matching file paths
    """
    dir_path = Path(directory)
    
    if not dir_path.exists():
        logger.warning(f"Directory does not exist: {directory}")
        return []
    
    if recursive:
        files = list(dir_path.rglob(pattern))
    else:
        files = list(dir_path.glob(pattern))
    
    return sorted(files)


def get_latest_file(
    directory: Path,
    pattern: str = "*.csv"
) -> Optional[Path]:
    """
    Get the most recently modified file matching a pattern
    
    Args:
        directory: Directory to search
        pattern: Glob pattern to match
    
    Returns:
        Path to most recent file or None if no files found
    """
    files = find_files_by_pattern(directory, pattern)
    
    if not files:
        return None
    
    # Sort by modification time, most recent first
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    return files[0]


class DataProcessor:
    """
    Base class for data processing operations
    
    Provides common functionality for processing pipelines.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize processor
        
        Args:
            config_path: Path to configuration file
        """
        self.config = {}
        if config_path:
            self.config = load_yaml_config(config_path)
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def load_data(self, file_path: Path) -> pd.DataFrame:
        """
        Load data from a file
        
        Args:
            file_path: Path to data file
        
        Returns:
            DataFrame with loaded data
        """
        self.logger.info(f"Loading data from {file_path}")
        
        if file_path.suffix == '.csv':
            df = pd.read_csv(file_path, low_memory=False)
        elif file_path.suffix in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path)
        elif file_path.suffix == '.parquet':
            df = pd.read_parquet(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_path.suffix}")
        
        self.logger.info(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")
        return df
    
    def save_data(self, df: pd.DataFrame, output_path: Path):
        """
        Save data to a file
        
        Args:
            df: DataFrame to save
            output_path: Where to save the file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if output_path.suffix == '.csv':
            df.to_csv(output_path, index=False)
        elif output_path.suffix in ['.xlsx', '.xls']:
            df.to_excel(output_path, index=False)
        elif output_path.suffix == '.parquet':
            df.to_parquet(output_path, index=False)
        else:
            raise ValueError(f"Unsupported file type: {output_path.suffix}")
        
        self.logger.info(f"  Saved {len(df):,} rows to {output_path}")


if __name__ == "__main__":
    # Run some simple tests
    print("Testing utility functions...")
    
    print("\nState standardization:")
    print(f"  'California' -> {standardize_state('California')}")
    print(f"  'ca' -> {standardize_state('ca')}")
    print(f"  'New York' -> {standardize_state('New York')}")
    print(f"  'TX' -> {get_state_name('TX')}")
    
    print("\nNumber formatting:")
    print(f"  1234567 -> {format_number(1234567)}")
    print(f"  1234.567 (2 decimals) -> {format_number(1234.567, 2)}")
    
    print("\nSafe division:")
    print(f"  10 / 2 = {safe_divide(10, 2)}")
    print(f"  10 / 0 = {safe_divide(10, 0, default=999)}")
    
    print("\n✓ Utilities module loaded successfully")
