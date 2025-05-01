"""Tests for the output builder functionality."""

import pytest
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import MagicMock

from np.output_builder import OutputBuilder


def test_get_output_dir(temp_project_dir, mocker):
    """Test getting the output directory."""
    console = MagicMock()
    builder = OutputBuilder(temp_project_dir, console)
    
    # Test creating output dir
    output_dir = builder.get_output_dir()
    assert output_dir.exists()
    assert output_dir.is_dir()
    assert output_dir.name == "np_output"
    
    # Clean up
    output_dir.rmdir()

def test_prepare_task_dir(temp_project_dir, mocker):
    """Test preparing the task directory."""
    console = MagicMock()
    builder = OutputBuilder(temp_project_dir, console)
    
    # Test with valid task name
    task_name = "test-task"
    task_dir = builder.prepare_task_dir(task_name)
    
    assert task_dir.exists()
    assert task_dir.is_dir()
    assert task_dir.name.endswith("-test-task")
    assert task_dir.name.startswith("00")
    
    # Test with invalid characters in task name
    task_name = "test/task:file"
    task_dir = builder.prepare_task_dir(task_name)
    
    assert task_dir.exists()
    assert task_dir.is_dir()
    assert "test-task-file" in task_dir.name
    assert "/" not in task_dir.name
    assert ":" not in task_dir.name
    
    # Clean up
    shutil.rmtree(temp_project_dir / "np_output")

def test_next_task_number(temp_project_dir, mocker):
    """Test getting the next task number."""
    console = MagicMock()
    builder = OutputBuilder(temp_project_dir, console)
    
    # Create a test output directory structure
    output_dir = temp_project_dir / "np_output"
    output_dir.mkdir(exist_ok=True)
    
    # No numbered directories yet
    assert builder._get_next_task_number() == 1
    
    # Add some numbered dirs
    (output_dir / "001-task1").mkdir()
    (output_dir / "002-task2").mkdir()
    
    assert builder._get_next_task_number() == 3
    
    # Add higher number
    (output_dir / "005-task5").mkdir()
    
    assert builder._get_next_task_number() == 6
    
    # Add non-numbered dir (should be ignored)
    (output_dir / "test-dir").mkdir()
    
    assert builder._get_next_task_number() == 6
    
    # Clean up
    shutil.rmtree(output_dir)

def test_save_task_definition(temp_project_dir, mocker):
    """Test saving the task definition."""
    console = MagicMock()
    builder = OutputBuilder(temp_project_dir, console)
    
    # Create output dir and task dir
    output_dir = temp_project_dir / "np_output"
    output_dir.mkdir(exist_ok=True)
    task_dir = output_dir / "001-test-task"
    task_dir.mkdir()
    
    # Test saving task definition
    task_def = "This is a test task"
    included_files = [Path("file1.py"), Path("file2.py")]
    git_repos = {"repo1": "hash1", "repo2": "hash2"}
    token_estimate = 100
    
    builder.save_task_definition(task_dir, task_def, included_files, git_repos, token_estimate)
    
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
    
    # Test creating LLM output file
    llm_name = "test-llm"
    output_file = builder.create_llm_output_file(task_dir, llm_name)
    
    # Verify file was created
    assert output_file.exists()
    assert output_file.name == "test-llm.md"
    
    # Test with special characters in LLM name
    llm_name = "test/llm:name"
    output_file = builder.create_llm_output_file(task_dir, llm_name)
    
    # Verify file was created with sanitized name
    assert output_file.exists()
    assert "test-llm-name" in output_file.name
    
    # Clean up
    shutil.rmtree(output_dir) 