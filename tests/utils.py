"""Helper functions for testing."""

from pathlib import Path


# Define a helper function to check if the output file exists
def check_file_exists(file_path):
    """Check if the file exists and is not empty."""
    return Path(file_path).exists() and Path(file_path).stat().st_size > 0