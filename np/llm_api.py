import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path

import requests
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.spinner import Spinner

from .output_builder import OutputBuilder

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 120 # Timeout for the HTTP request itself
DEFAULT_TEMPERATURE = 1.0
DEFAULT_API_TIMEOUT = 60 # Timeout parameter sent *to* OpenRouter
OPENROUTER_GENERATION_URL = "https://openrouter.ai/api/v1/generation" # New endpoint URL

# Structure to hold results/status for each model
class ModelStatus:
    def __init__(self, name: str, is_openrouter: bool):
        self.name = name
        self.is_openrouter = is_openrouter
        self.status = "Waiting..."
        self.result_content: Optional[str] = None
        self.error_message: Optional[str] = None
        self.cost: float = 0.0
        self.future: Optional[Future] = None
        self.start_time = time.monotonic()
        self.end_time: Optional[float] = None
        self.generation_id: Optional[str] = None # Store generation ID

    def get_display(self) -> str:
        elapsed = f" ({time.monotonic() - self.start_time:.1f}s)" if self.status not in ["Done", "Error", "Manual Input"] else ""
        if self.status == "Done":
             return f"[green]✅ {self.name}[/green]{elapsed}"
        elif self.status == "Error":
             return f"[red]❌ {self.name}[/red]{elapsed}"
        elif self.status == "Manual Input":
             return f"[yellow]✏️ {self.name}[/yellow] Pending manual input"
        else:
             spinner = Spinner("dots", text="")
             return f"[blue]{spinner.render(time.time())} {self.name}[/blue] {self.status}{elapsed}"


class LLMApi:
    """ Handles interaction with the OpenRouter API. """
    def __init__(
        self,
        api_key: Optional[str],
        output_builder: OutputBuilder,
        task_dir_path: Path,
        console: Optional[Console] = None,
        max_workers: int = 5,
    ):
        self.api_key = api_key
        self.output_builder = output_builder
        self.task_dir_path = task_dir_path
        self.console = console or Console()
        self.max_workers = max_workers
        self._model_status: Dict[str, ModelStatus] = {}
        self._lock = threading.Lock() # To safely update shared status
        self._generation_details_cache: Dict[str, Dict[str, Any]] = {} # Cache for /generation responses

    def _is_openrouter_model(self, model_name: str) -> bool:
        """ Basic heuristic to identify OpenRouter models. """
        # A more robust check might involve fetching available models from OpenRouter
        # or using a more specific naming convention.
        return '/' in model_name

    def _send_request(self, model_name: str, merged_prompt: str, overrides: Dict[str, Any]) -> None:
        """ Sends a single request to OpenRouter. Runs in a thread. """
        start_time = time.monotonic()
        status_key = model_name # Use original name as key

        if not self.api_key:
            with self._lock:
                 self._model_status[status_key].status = "Error"
                 self._model_status[status_key].error_message = "API Key not configured."
                 self._model_status[status_key].end_time = time.monotonic()
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/klimentij/NerdPrompt", # Optional but good practice
            "X-Title": "nerd-prompt", # Optional
        }
        generation_headers = { # Headers for the GET /generation request
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": merged_prompt}],
            "temperature": overrides.get("temperature", DEFAULT_TEMPERATURE),
            "timeout": overrides.get("timeout", DEFAULT_API_TIMEOUT),
            # Add other overrides dynamically
            **{k: v for k, v in overrides.items() if k not in ["temperature", "timeout"]}
        }

        response_content: Optional[str] = None
        error_msg: Optional[str] = None
        cost: float = 0.0
        generation_id: Optional[str] = None
        generation_details: Optional[Dict[str, Any]] = None

        try:
            with self._lock:
                 self._model_status[status_key].status = "Sending..."
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            # --- Process Success ---
            data = response.json()
            response_content = data.get("choices", [{}])[0].get("message", {}).get("content")
            if not response_content:
                 error_msg = "Error: Received empty content from API."
                 # Still try to get generation ID and cost if possible
            
            # Attempt to get generation ID from the primary response
            # Check common locations for generation ID
            generation_id = data.get("id") # Sometimes it's just 'id'
            if not generation_id and isinstance(data.get("usage"), dict):
                generation_id = data["usage"].get("generation_id") # Check inside usage dict
            # Add other potential locations if needed based on API variations

            # Store generation ID if found
            if generation_id:
                with self._lock:
                    self._model_status[status_key].generation_id = generation_id


            # --- Fetch Generation Details for Cost ---
            if generation_id:
                try:
                    with self._lock:
                        self._model_status[status_key].status = "Fetching cost..."
                    
                    # Check cache first
                    cached_details = self._generation_details_cache.get(generation_id)
                    if cached_details:
                         generation_details = cached_details
                    else:
                        # Allow retries for fetching generation details
                        max_retries = 3
                        retry_delay = 1 # Start with 1 second delay
                        for attempt in range(max_retries):
                            gen_response = requests.get(
                                OPENROUTER_GENERATION_URL,
                                headers=generation_headers,
                                params={"id": generation_id},
                                timeout=REQUEST_TIMEOUT_SECONDS / 2 # Shorter timeout for this call
                            )
                            if gen_response.status_code == 200:
                                generation_details = gen_response.json().get("data")
                                if generation_details:
                                     # Cache the result
                                     self._generation_details_cache[generation_id] = generation_details
                                     break # Success
                                else: 
                                     # Handle case where 'data' key is missing or empty
                                     error_msg = f"Error: Received empty 'data' from /generation endpoint for ID {generation_id}."
                                     break 
                            elif gen_response.status_code == 404 and attempt < max_retries - 1:
                                # Generation might not be ready yet, retry after delay
                                time.sleep(retry_delay)
                                retry_delay *= 2 # Exponential backoff
                                continue
                            else:
                                # Raise error for non-404 or final retry failure
                                gen_response.raise_for_status()
                        
                        if not generation_details and not error_msg:
                            error_msg = f"Error: Failed to retrieve generation details for ID {generation_id} after {max_retries} attempts."


                except requests.exceptions.Timeout:
                    error_msg = f"Error: Timeout fetching cost details for ID {generation_id}."
                except requests.exceptions.RequestException as e:
                     # Append to existing error or set new one
                     gen_error = f"Error fetching cost details for ID {generation_id}: {e}"
                     error_msg = f"{error_msg}\\n{gen_error}" if error_msg else gen_error
                except Exception as e:
                     gen_error = f"Unexpected error fetching cost details for ID {generation_id}: {e}"
                     error_msg = f"{error_msg}\\n{gen_error}" if error_msg else gen_error


            # --- Extract Cost and Usage from Generation Details (if fetched) ---
            tokens_prompt = 0
            total_tokens = 0
            model_info = ""
            provider_name = ""
            generation_time_ms = None
            latency_ms = None
            finish_reason = ""
            native_tokens_prompt = 0
            native_tokens_completion = 0

            if generation_details:
                 cost = float(generation_details.get("usage") or generation_details.get("total_cost", 0.0))
                 tokens_prompt = generation_details.get("tokens_prompt", 0)
                 tokens_completion = generation_details.get("tokens_completion", 0)
                 total_tokens = tokens_prompt + tokens_completion # Recalculate for safety
                 model_info = generation_details.get("model", model_name) # Use model from details if available
                 provider_name = generation_details.get("provider_name", "")
                 generation_time_ms = generation_details.get("generation_time")
                 latency_ms = generation_details.get("latency")
                 finish_reason = generation_details.get("finish_reason", "")
                 native_tokens_prompt = generation_details.get("native_tokens_prompt", 0)
                 native_tokens_completion = generation_details.get("native_tokens_completion", 0)
            else:
                 # Fallback if generation details couldn't be fetched but we have response_content
                 cost = 0.0 # Can't determine cost accurately
                 model_info = model_name # Use the requested model name
                 # Maybe try to extract tokens from the initial response as a last resort?
                 usage_initial = data.get("usage", {})
                 if isinstance(usage_initial, dict):
                     tokens_prompt = usage_initial.get("prompt_tokens", 0)
                     tokens_completion = usage_initial.get("completion_tokens", 0)
                     total_tokens = usage_initial.get("total_tokens", 0) or (tokens_prompt + tokens_completion)



            # Create usage information markdown to append to response
            usage_info = []
            if model_info:
                usage_info.append(f"**Model:** {model_info}")
            if provider_name:
                 usage_info.append(f"**Provider:** {provider_name}")
            if tokens_prompt:
                usage_info.append(f"**Prompt tokens:** {tokens_prompt}")
            if tokens_completion:
                usage_info.append(f"**Completion tokens:** {tokens_completion}")
            if total_tokens:
                usage_info.append(f"**Total tokens:** {total_tokens}")
            if native_tokens_prompt:
                 usage_info.append(f"**Native Prompt Tokens:** {native_tokens_prompt}")
            if native_tokens_completion:
                 usage_info.append(f"**Native Completion Tokens:** {native_tokens_completion}")
            if cost > 0: # Only show cost if it's definitively known and > 0
                usage_info.append(f"**Cost:** ${cost:.6f}")
            elif generation_id and not generation_details and not error_msg:
                usage_info.append(f"**Cost:** [yellow]Unknown (Failed to fetch details)[/yellow]")
            elif not generation_id:
                 usage_info.append(f"**Cost:** [yellow]Unknown (Could not get generation ID)[/yellow]")

            # Add timing and finish reason if available
            if generation_time_ms is not None:
                 usage_info.append(f"**Generation Time:** {generation_time_ms} ms")
            if latency_ms is not None:
                 usage_info.append(f"**Latency (TTFT):** {latency_ms} ms") # TTFT = Time To First Token
            if finish_reason:
                 usage_info.append(f"**Finish Reason:** {finish_reason}")

            # Append usage information to response if we have any
            if usage_info and response_content:
                usage_md = "\n\n---\n" + "\n".join(usage_info)
                response_content += usage_md


        except requests.exceptions.Timeout:
            error_msg = f"Error: Request timed out after {REQUEST_TIMEOUT_SECONDS} seconds."
        except requests.exceptions.RequestException as e:
            error_body = ""
            if hasattr(e.response, 'text'):
                try:
                     error_detail = json.dumps(e.response.json(), indent=2)
                     error_body = f"\n```json\n{error_detail}\n```"
                except (json.JSONDecodeError, AttributeError):
                     error_body = f"\n```\n{e.response.text[:500]}\n```" # Show raw text excerpt
            error_msg = f"Error: API request failed: {e}{error_body}"
        except Exception as e:
            error_msg = f"Error: An unexpected error occurred: {e}"

        # Update status safely
        with self._lock:
            status_obj = self._model_status[status_key]
            status_obj.end_time = time.monotonic()
            status_obj.cost = cost # Store calculated/fetched cost
            if error_msg:
                status_obj.status = "Error"
                status_obj.error_message = error_msg
                status_obj.result_content = f"# ERROR: Failed to get response from {model_name}\n\n**Timestamp:** {datetime.now().isoformat()}\n**Error Details:**\n{error_msg}"
            elif response_content:
                status_obj.status = "Done"
                status_obj.result_content = response_content
            else: # Should not happen if error handling is correct
                status_obj.status = "Error"
                status_obj.error_message = "Unknown error: No content and no specific error."
                status_obj.result_content = f"# ERROR: Unknown failure for {model_name}"

            # Write result/error to file immediately after processing
            if status_obj.result_content:
                 self.output_builder.write_llm_response(
                      self.task_dir_path, status_obj.name, status_obj.result_content
                 )


    def _generate_status_table(self) -> Table:
        """ Creates a Rich Table to display current model statuses. """
        table = Table(show_header=False, box=None, padding=0)
        table.add_column()

        sorted_names = sorted(self._model_status.keys())
        for name in sorted_names:
            status_obj = self._model_status[name]
            table.add_row(status_obj.get_display())
        return table

    def process_llms(
        self,
        llm_names: List[str],
        merged_prompt: str,
        model_overrides: Dict[str, Dict[str, Any]]
    ) -> float:
        """
        Processes the list of LLMs, sending requests to OpenRouter models in parallel.
        Displays live status updates using Rich. Writes results to files.
        Returns the total calculated cost.
        """
        self._model_status.clear()
        futures: Dict[str, Future] = {}
        self._generation_details_cache.clear() # Clear cache for new run

        # Initialize status for each model
        for name in llm_names:
            is_or = self._is_openrouter_model(name)
            self._model_status[name] = ModelStatus(name, is_or)

        # --- Use ThreadPoolExecutor for concurrent requests ---
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for name in llm_names:
                status = self._model_status[name]
                overrides = model_overrides.get(name, {})
                if status.is_openrouter:
                    status.status = "Queued..."
                    # Submit API call task
                    future = executor.submit(self._send_request, name, merged_prompt, overrides)
                    status.future = future
                    futures[name] = future
                else:
                    # Handle non-OpenRouter (manual input) models immediately
                    status.status = "Manual Input"
                    status.end_time = time.monotonic() # Mark as 'finished' for status display
                    # We don't add non-OR models to futures dict

            # --- Live Status Update ---
            table = self._generate_status_table()
            total_llms = len(llm_names)
            completed_llms = total_llms - len(futures) # Start with non-OR models completed

            with Live(table, console=self.console, refresh_per_second=4, vertical_overflow="visible") as live:
                while completed_llms < total_llms:
                    done_count = 0
                    for name, fut in futures.items():
                        if fut.done():
                            done_count +=1
                            # Process result/exception immediately after completion if needed (optional)
                            try:
                                fut.result() # Call result() to raise exceptions if any occurred in the thread
                            except Exception as e:
                                # Error should have been logged within _send_request and status updated
                                # self.console.print(f"Error in future for {name}: {e}") # Optional: re-log
                                pass # Error is handled and stored in ModelStatus

                    newly_completed = done_count - (completed_llms - (total_llms - len(futures)) ) # Calculate newly done futures
                    completed_llms += newly_completed

                    # Update table and refresh live display
                    live.update(self._generate_status_table())
                    time.sleep(0.1) # Short sleep to prevent busy-waiting


        # --- Process and Save Results ---
        total_cost = 0.0
        self.console.print("\nProcessing complete.")
        for name, status in self._model_status.items():
            if status.status == "Done" and status.result_content:
                self.output_builder.write_llm_response(
                     task_dir_path=self.task_dir_path,
                     llm_name=status.name,
                     content=status.result_content
                 )
                total_cost += status.cost
            elif status.status == "Error":
                self.console.print(f"[bold red]Error for {name}:[/] {status.error_message}")
                if status.result_content: # Check if error content was generated
                     self.output_builder.write_llm_response(
                         task_dir_path=self.task_dir_path,
                         llm_name=status.name,
                         content=status.result_content
                     )
            elif status.status == "Manual Input":
                # Manual input handling (if any) would happen elsewhere or be initiated here
                pass


        self.console.print(f"Total estimated cost: ${total_cost:.6f}")
        return total_cost 