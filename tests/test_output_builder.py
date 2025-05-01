"""Tests for the output builder functionality."""

import pytest
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import MagicMock
import re

from np.output_builder import OutputBuilder


def test_get_output_dir(temp_project_dir, mocker):
    """Test getting the output directory."""
    console = MagicMock()
    builder = OutputBuilder(temp_project_dir, console)
    
    # Test creating output dir
    output_dir = builder.output_dir
    assert output_dir.exists()
    assert output_dir.is_dir()
    assert output_dir.name == "np_output"
    
    # Clean up - use shutil.rmtree instead of rmdir to handle non-empty dirs
    try:
        shutil.rmtree(output_dir)
    except Exception as e:
        pass  # Ignore any issues with cleanup

def test_prepare_task_dir(temp_project_dir, mocker):
    """Test preparing the task directory."""
    console = MagicMock()
    builder = OutputBuilder(temp_project_dir, console)
    
    # Test with valid task name
    task_name = "test-task"
    next_num, num_str = builder.get_next_folder_number()
    task_dir = builder.create_task_output_structure(
        task_number_str=num_str,
        task_name_sanitized=task_name,
        original_task_name=task_name,
        task_definition="Test task definition",
        included_local_files=[],
        processed_git_repos=[],
        estimated_tokens=100,
        llm_names=["test-llm"]
    )
    
    assert task_dir.exists()
    assert task_dir.is_dir()
    assert task_dir.name.endswith("-test-task")
    # Check for a digit prefix without requiring exactly "00"
    assert re.match(r"\d+-test-task", task_dir.name), f"Expected numeric prefix: {task_dir.name}"
    
    # Test with invalid characters in task name
    task_name = "test/task:file"
    next_num, num_str = builder.get_next_folder_number()
    task_dir = builder.create_task_output_structure(
        task_number_str=num_str,
        task_name_sanitized="test-task-file",
        original_task_name=task_name,
        task_definition="Test task definition",
        included_local_files=[],
        processed_git_repos=[],
        estimated_tokens=100,
        llm_names=["test-llm"]
    )
    
    assert task_dir.exists()
    assert task_dir.is_dir()
    assert "test-task-file" in task_dir.name
    assert "/" not in task_dir.name
    assert ":" not in task_dir.name
    
    # Clean up
    try:
        shutil.rmtree(temp_project_dir / "np_output")
    except Exception as e:
        pass  # Ignore cleanup issues

def test_next_task_number(temp_project_dir, mocker):
    """Test getting the next task number."""
    console = MagicMock()
    builder = OutputBuilder(temp_project_dir, console)
    
    # Mock the _scan_and_renumber_folders method to control the test
    # This ensures our test doesn't rely on global state from other tests
    mock_scan = mocker.patch.object(builder, '_scan_and_renumber_folders')
    
    # First call: No folders
    mock_scan.return_value = (1, 2)  # Return (next_num, padding)
    next_num, num_str = builder.get_next_folder_number()
    assert next_num == 1
    assert num_str == "01"  # Should be padded to match the padding returned
    
    # Second call: Some folders exist
    mock_scan.return_value = (3, 2) 
    next_num, num_str = builder.get_next_folder_number()
    assert next_num == 3
    assert num_str == "03"
    
    # Third call: Higher number 
    mock_scan.return_value = (6, 2)
    next_num, num_str = builder.get_next_folder_number()
    assert next_num == 6
    assert num_str == "06"
    
    # Fourth call: With more padding
    mock_scan.return_value = (101, 3)
    next_num, num_str = builder.get_next_folder_number()
    assert next_num == 101
    assert num_str == "101"
    
    # Cleanup not needed since we didn't actually create folders
    # and we're using a mock for the scan operation

def test_save_task_definition(temp_project_dir, mocker):
    """Test saving the task definition."""
    console = MagicMock()
    builder = OutputBuilder(temp_project_dir, console)
    
    # Create output dir and task dir
    output_dir = temp_project_dir / "np_output"
    output_dir.mkdir(exist_ok=True)
    task_dir = output_dir / "001-test-task"
    task_dir.mkdir()
    
    # Test saving task definition by creating a task structure
    task_def = "This is a test task"
    included_files = [Path("file1.py"), Path("file2.py")]
    git_repos = [("repo1", "branch1", "hash1", Path("repo1_path")), ("repo2", "branch2", "hash2", Path("repo2_path"))]
    token_estimate = 100
    
    task_dir = builder.create_task_output_structure(
        task_number_str="001",
        task_name_sanitized="test-task",
        original_task_name="test-task",
        task_definition=task_def,
        included_local_files=included_files,
        processed_git_repos=git_repos,
        estimated_tokens=token_estimate,
        llm_names=["test-llm"]
    )
    
    # Verify task definition file was created
    task_file = task_dir / "_task.md"
    assert task_file.exists()
    
    # Verify content
    content = task_file.read_text()
    assert task_def in content
    assert "file1.py" in content
    assert "file2.py" in content
    assert "repo1" in content
    assert "hash1" in content
    assert "repo2" in content
    assert "hash2" in content
    assert "100" in content
    
    # Clean up
    shutil.rmtree(output_dir)

def test_create_llm_output_file(temp_project_dir, mocker):
    """Test creating the LLM output file."""
    console = MagicMock()
    builder = OutputBuilder(temp_project_dir, console)
    
    # Create output dir and task dir
    output_dir = temp_project_dir / "np_output"
    output_dir.mkdir(exist_ok=True)
    task_dir = output_dir / "001-test-task"
    task_dir.mkdir()
    
    # Test creating LLM output file through task output structure
    llm_name = "test-llm"
    task_dir = builder.create_task_output_structure(
        task_number_str="001",
        task_name_sanitized="test-task",
        original_task_name="test-task",
        task_definition="Test task definition",
        included_local_files=[],
        processed_git_repos=[],
        estimated_tokens=100,
        llm_names=[llm_name]
    )
    
    # Verify file was created
    output_file = task_dir / f"{llm_name}.md"
    assert output_file.exists()
    assert output_file.name == "test-llm.md"
    
    # Test with special characters in LLM name
    llm_name = "test/llm:name"
    builder.write_llm_response(task_dir, llm_name, "Test content")
    
    # Verify file was created with sanitized name
    from np.utils import sanitize_filename
    sanitized_name = sanitize_filename(llm_name)
    output_file = task_dir / f"{sanitized_name}.md"
    assert output_file.exists()
    assert "test-llm-name" in output_file.name
    
    # Clean up
    shutil.rmtree(output_dir) 