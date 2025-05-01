#!/usr/bin/env python3
"""Sample main module for testing nerd-prompt."""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from .utils import read_config, write_output


def process_data(input_file: str, output_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Process data from input file and optionally write to output file.
    
    Args:
        input_file: Path to input file
        output_file: Optional path to output file
        
    Returns:
        Dict with processed data
    """
    config = read_config()
    data = {
        "processed": True,
        "source": input_file,
        "config": config
    }
    
    if output_file:
        write_output(data, output_file)
        
    return data


def main():
    """Main entry point for the sample application."""
    print("Sample application for testing nerd-prompt")
    
    # Sample data processing
    result = process_data("input.txt", "output.json")
    print(f"Processed data: {result}")
    
    return 0


if __name__ == "__main__":
    exit(main()) 