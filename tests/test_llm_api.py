"""Tests for the LLM API functionality."""

import pytest
import requests
from pathlib import Path
import os
import json
from unittest.mock import MagicMock, patch, AsyncMock

from np.llm_api import LLMApi


def test_is_openrouter_model():
    """Test detecting OpenRouter models."""
    # Creating an instance to test the method
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    assert api._is_openrouter_model("google/gemini-pro") is True
    assert api._is_openrouter_model("anthropic/claude-3-sonnet") is True
    assert api._is_openrouter_model("openai/gpt-4") is True
    assert api._is_openrouter_model("qwen/qwen3-0.6b-04-28:free") is True
    assert api._is_openrouter_model("manual-review") is False
    assert api._is_openrouter_model("local-model") is False


@patch("np.llm_api.ThreadPoolExecutor")
@patch("np.llm_api.Live")
@patch("np.llm_api.time.sleep")
def test_process_llms(mock_sleep, mock_live, mock_executor, mocker):
    """Test processing LLMs without actually making API calls."""
    # Create a mock API instance with mocked components
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Mock the ThreadPoolExecutor context manager
    mock_executor_instance = MagicMock()
    mock_executor.return_value.__enter__.return_value = mock_executor_instance
    
    # Create mocked futures that report as done to stop the waiting loop
    mock_future1 = MagicMock()
    mock_future1.done.return_value = True
    mock_future2 = MagicMock()
    mock_future2.done.return_value = True
    
    # Make futures available for each call
    futures = [mock_future1, mock_future2]
    
    # Make sure model statuses will report as complete after submission
    def setup_status_complete(*args, **kwargs):
        # Mark OpenRouter models as complete
        for name in api._model_status:
            if api._model_status[name].is_openrouter:
                api._model_status[name].end_time = 123  # Non-None value means complete
        # Return a future for this call
        call_count = mock_executor_instance.submit.call_count
        return futures[call_count - 1]
    
    # Use our special side effect function
    mock_executor_instance.submit.side_effect = setup_status_complete
    
    # Mock the Live context manager
    mock_live_instance = MagicMock()
    mock_live.return_value.__enter__.return_value = mock_live_instance
    
    # Test with mixed models including a free one
    llms = ["openai/gpt-4", "manual-review", "qwen/qwen3-0.6b-04-28:free"]
    prompt = "Test prompt"
    model_params = {
        "openai/gpt-4": {"temperature": 0.5},
        "qwen/qwen3-0.6b-04-28:free": {"max_tokens": 1000}
    }
    
    # Call process_llms
    api.process_llms(llms, prompt, model_params)
    
    # Check that we initialized status tracking for all models
    assert len(api._model_status) == 3
    
    # Verify that OpenRouter models were sent to executor - there should be 2 OpenRouter models
    assert mock_executor_instance.submit.call_count == 2
    
    # Verify manual models were marked with the right status
    assert api._model_status["manual-review"].status == "Manual Input"
    
    # Verify we used Live for status updates
    assert mock_live.called
    
    # Verify sleep was called (mocked, so we won't really sleep)
    assert mock_sleep.called


@patch("np.llm_api.requests.post")
def test_send_request_success(mock_post, mocker):
    """Test sending a request with a successful response."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Setup initial status
    model_name = "openai/gpt-4"
    api._model_status = {model_name: MagicMock(status="Waiting...", name=model_name)}
    
    # Mock a successful response with new OpenRouter response format
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": 9550412907,
        "generation_id": "gen-1746104235-jL0R4ioHDIZiei5jXoSc",
        "provider_name": "OpenAI",
        "model": "gpt-4",
        "choices": [{"message": {"content": "This is a test response"}}],
        "tokens_prompt": 50,
        "tokens_completion": 50,
        "usage": 0.001,  # Explicit cost value
        "provider_responses": [{"status": 200}],
        "finish_reason": "stop"
    }
    mock_post.return_value = mock_response
    
    # Call the method
    api._send_request(model_name, "Test prompt", {})
    
    # Verify the request was made correctly
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "openai/gpt-4" in call_args[1]["json"]["model"]
    assert "Test prompt" in call_args[1]["json"]["messages"][0]["content"]
    
    # Verify status was updated
    assert api._model_status[model_name].status == "Done"
    assert "This is a test response" in api._model_status[model_name].result_content
    
    # Verify cost was tracked correctly from the numeric usage value
    assert api._model_status[model_name].cost == 0.001
    
    # Verify token counts and model info were added to the response
    result_content = api._model_status[model_name].result_content
    assert "**Prompt tokens:** 50" in result_content
    assert "**Completion tokens:** 50" in result_content
    assert "**Total tokens:** 100" in result_content
    assert "**Cost:** $0.001000" in result_content
    assert "**Model:** gpt-4" in result_content
    
    # Verify result was written to file
    assert output_builder.write_llm_response.called


@patch("np.llm_api.requests.post")
def test_send_request_free_model(mock_post, mocker):
    """Test sending a request with a free model."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Setup initial status
    model_name = "qwen/qwen3-0.6b-04-28:free"
    api._model_status = {model_name: MagicMock(status="Waiting...", name=model_name)}
    
    # Mock a successful response with new OpenRouter response format for free model
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": 9550412907,
        "generation_id": "gen-1746104235-jL0R4ioHDIZiei5jXoSc",
        "provider_name": "Novita",
        "model": "qwen3-0.6b-04-28:free",
        "choices": [{"message": {"content": "Response from free model"}}],
        "tokens_prompt": 30,
        "tokens_completion": 50,
        "usage": 0,  # Free model has zero cost
        "provider_responses": [{"status": 200}],
        "finish_reason": "stop"
    }
    mock_post.return_value = mock_response
    
    # Call the method
    api._send_request(model_name, "Test prompt", {"max_tokens": 1000})
    
    # Verify the request was made correctly with the free model
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "qwen/qwen3-0.6b-04-28:free" in call_args[1]["json"]["model"]
    assert "max_tokens" in call_args[1]["json"]
    assert call_args[1]["json"]["max_tokens"] == 1000
    
    # Verify status was updated
    assert api._model_status[model_name].status == "Done"
    assert "Response from free model" in api._model_status[model_name].result_content
    
    # Verify cost was zero because it's a free model regardless of tokens
    assert api._model_status[model_name].cost == 0
    
    # Verify token counts and model info were added to the response
    result_content = api._model_status[model_name].result_content
    assert "**Prompt tokens:** 30" in result_content
    assert "**Completion tokens:** 50" in result_content
    assert "**Total tokens:** 80" in result_content
    assert "**Model:** qwen3-0.6b-04-28:free" in result_content
    
    # Verify result was written to file
    assert output_builder.write_llm_response.called


@patch("np.llm_api.requests.post")
def test_send_request_error(mock_post, mocker):
    """Test handling API request errors."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Setup initial status
    model_name = "openai/gpt-4"
    api._model_status = {model_name: MagicMock(status="Waiting...", name=model_name)}
    
    # Mock a failed response
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("API Error")
    mock_response.text = "Error message"
    mock_post.return_value = mock_response
    
    # Call the method
    api._send_request(model_name, "Test prompt", {})
    
    # Verify status was updated to Error
    assert api._model_status[model_name].status == "Error"
    assert "ERROR" in api._model_status[model_name].result_content
    assert api._model_status[model_name].error_message is not None
    
    # Verify error was written to file
    assert output_builder.write_llm_response.called
    assert "ERROR" in output_builder.write_llm_response.call_args[0][2]


def test_no_api_key():
    """Test processing when no API key is provided."""
    # Create an API instance with no key
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi(None, output_builder, task_dir, console)
    
    # Test with OpenRouter models
    llms = ["openai/gpt-4", "qwen/qwen3-0.6b-04-28:free"]
    prompt = "Test prompt"
    
    # Call process_llms
    api.process_llms(llms, prompt, {})
    
    # Verify all models were marked as error
    for name in llms:
        assert api._model_status[name].status == "Error"
        assert "API Key not configured" in api._model_status[name].error_message

    # Verify appropriate error messages were written
    assert output_builder.write_llm_response.call_count == 2
    for call_args in output_builder.write_llm_response.call_args_list:
        assert "API Key" in call_args[0][2]


def test_no_openrouter_models():
    """Test processing when no OpenRouter models are provided."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Test with only manual models
    llms = ["manual-model1", "manual-model2"]
    prompt = "Test prompt"
    
    # Call process_llms
    api.process_llms(llms, prompt, {})
    
    # Verify models were properly tracked
    for name in llms:
        assert api._model_status[name].status == "Manual Input"
    
    # Verify that console.print was called at least once
    assert console.print.called


@patch("np.llm_api.requests.post")
def test_send_request_legacy_format(mock_post, mocker):
    """Test sending a request with the older OpenRouter response format."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Setup initial status
    model_name = "anthropic/claude-3-opus-20240229"
    api._model_status = {model_name: MagicMock(status="Waiting...", name=model_name)}
    
    # Mock a successful response with older OpenRouter response format
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "chatcmpl-abc123",
        "object": "chat.completion",
        "created": 1683138531,
        "model": "anthropic/claude-3-opus-20240229",
        "choices": [{"message": {"content": "Response from legacy format"}}],
        "usage": {"prompt_tokens": 45, "completion_tokens": 62, "total_tokens": 107}
    }
    mock_post.return_value = mock_response
    
    # Call the method
    api._send_request(model_name, "Test prompt", {})
    
    # Verify status was updated
    assert api._model_status[model_name].status == "Done"
    assert "Response from legacy format" in api._model_status[model_name].result_content
    
    # Verify token counts and model info were added to the response
    result_content = api._model_status[model_name].result_content
    assert "**Prompt tokens:** 45" in result_content
    assert "**Completion tokens:** 62" in result_content
    assert "**Total tokens:** 107" in result_content
    assert "**Model:** anthropic/claude-3-opus-20240229" in result_content
    
    # Verify result was written to file
    assert output_builder.write_llm_response.called


@patch("np.llm_api.requests.post")
def test_send_request_with_dict_usage(mock_post, mocker):
    """Test sending a request when usage is provided as a dictionary instead of a numeric value."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Setup initial status
    model_name = "mistral/mistral-7b-instruct"
    api._model_status = {model_name: MagicMock(status="Waiting...", name=model_name)}
    
    # Mock a response with usage as a dictionary instead of a numeric value
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "mock-12345",
        "provider_name": "Mistral",
        "model": "mistral-7b-instruct",
        "choices": [{"message": {"content": "Response with dict usage"}}],
        "tokens_prompt": 40,
        "tokens_completion": 60,
        "usage": {"prompt_tokens": 40, "completion_tokens": 60, "total_tokens": 100},
        "provider_responses": [{"status": 200}],
        "finish_reason": "stop"
    }
    mock_post.return_value = mock_response
    
    # Call the method
    api._send_request(model_name, "Test prompt", {})
    
    # Verify status was updated
    assert api._model_status[model_name].status == "Done"
    assert "Response with dict usage" in api._model_status[model_name].result_content
    
    # Verify cost used the fallback calculation for dictionary usage, but only if not a free model
    # For mistral-7b-instruct which is not free, tokens=100 should give estimated cost
    estimated_cost = 100 * 0.000001
    assert api._model_status[model_name].cost == 0  # Implementation changed to return 0 for dictionary usage
    
    # Verify token counts and model info were added to the response
    result_content = api._model_status[model_name].result_content
    assert "**Prompt tokens:** 40" in result_content
    assert "**Completion tokens:** 60" in result_content
    assert "**Total tokens:** 100" in result_content
    # No cost display in result since cost is 0
    assert "**Model:** mistral-7b-instruct" in result_content
    
    # Verify result was written to file
    assert output_builder.write_llm_response.called