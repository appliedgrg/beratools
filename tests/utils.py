"""Helper functions for testing."""

from pathlib import Path


# Define a helper function to check if the output file exists
def check_file_exists(file_path, layer=None):
    """Check if the file exists and is not empty, then check for layer."""
    if not Path(file_path).exists() or Path(file_path).stat().st_size == 0:
        return False

    if layer is None:
        return True
    
    import pyogrio
    layers = pyogrio.list_layers(file_path)
    return layer in layers