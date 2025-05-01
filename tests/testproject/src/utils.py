"""Utility functions for the sample project."""

import json
import os
from pathlib import Path
from typing import Dict, Any


def read_config() -> Dict[str, Any]:
    """
    Read configuration from default location.
    
    Returns:
        Dict with configuration values
    """
    # Just a sample config
    return {
        "version": "1.0.0",
        "debug": True,
        "paths": {
            "data": "data/",
            "output": "output/"
        }
    }


def write_output(data: Dict[str, Any], output_file: str) -> None:
    """
    Write data to output file in JSON format.
    
    Args:
        data: Dict with data to write
        output_file: Path to output file
    """
    # Create directory if doesn't exist
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
        
    print(f"Data written to {output_file}")


def format_path(path: str) -> str:
    """
    Format a path according to project standards.
    
    Args:
        path: Path to format
        
    Returns:
        Formatted path
    """
    return str(Path(path).resolve()) 