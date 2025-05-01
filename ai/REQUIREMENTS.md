**Project: `nerd-prompt` (`np`) - Context Assembler & LLM Interaction CLI**

**Version:** 1.0
**Document Status:** **FINAL TECHNICAL REQUIREMENTS**
**Date:** 2025-05-01

**Target Audience:** Senior Python Developer

---

**Table of Contents:**

- [1. Overview \& Core Philosophy](#1-overview--core-philosophy)
- [2. Target Environment \& Dependencies](#2-target-environment--dependencies)
- [3. Installation](#3-installation)
- [4. Invocation Modes \& Entry Point (`__main__.py`)](#4-invocation-modes--entry-point-__main__py)
  - [4.1 Interactive Mode (`np`)](#41-interactive-mode-np)
  - [4.2 Non-Interactive Mode (`np [options]`)](#42-non-interactive-mode-np-options)
- [5. Code Structure (Multi-File)](#5-code-structure-multi-file)
  - [5.1 `np/__main__.py`](#51-np__main__py)
  - [5.2 `np/cli.py`](#52-npclipy)
  - [5.3 `np/interactive.py`](#53-npinteractivepy)
  - [5.4 `np/core.py`](#54-npcorepy)
  - [5.5 `np/config.py`](#55-npconfigpy)
  - [5.6 `np/git_handler.py`](#56-npgit_handlerpy)
  - [5.7 `np/llm_api.py`](#57-npllm_apipy)
  - [5.8 `np/output_builder.py`](#58-npoutput_builderpy)
  - [5.9 `np/utils.py`](#59-nputilspy)
- [6. Configuration \& State Management (`config.py`)](#6-configuration--state-management-configpy)
  - [6.1 Project Configuration (`.npconfig.toml`)](#61-project-configuration-npconfigtoml)
  - [6.2 Global Configuration (API Key)](#62-global-configuration-api-key)
  - [6.3 Configuration Loading \& Precedence](#63-configuration-loading--precedence)
- [7. Non-Interactive Mode Arguments (`cli.py` \& `Typer`)](#7-non-interactive-mode-arguments-clipy--typer)
- [8. Core Workflow: Interactive Mode Details (`interactive.py`)](#8-core-workflow-interactive-mode-details-interactivepy)
  - [8.1 Initialization \& Welcome](#81-initialization--welcome)
  - [8.2 Step 1: Source Selection (Include/Exclude/Git)](#82-step-1-source-selection-includeexcludegit)
  - [8.3 Step 2: LLM Selection](#83-step-2-llm-selection)
  - [8.4 Step 3: Task Naming](#84-step-3-task-naming)
  - [8.5 Step 4: Task Definition](#85-step-4-task-definition)
  - [8.6 Step 5: Advanced Settings (Optional)](#86-step-5-advanced-settings-optional)
  - [8.7 Configuration Saving (`config.py` interaction)](#87-configuration-saving-configpy-interaction)
  - [8.8 Final Confirmation](#88-final-confirmation)
- [9. Core Workflow: Processing Logic (`core.py`)](#9-core-workflow-processing-logic-corepy)
  - [9.1 Orchestration](#91-orchestration)
  - [9.2 Git Repository Processing Trigger](#92-git-repository-processing-trigger)
  - [9.3 File Discovery \& Filtering](#93-file-discovery--filtering)
  - [9.4 Token Estimation \& Reporting](#94-token-estimation--reporting)
  - [9.5 Merged Prompt Assembly](#95-merged-prompt-assembly)
  - [9.6 Clipboard Integration](#96-clipboard-integration)
  - [9.7 Output Generation Trigger](#97-output-generation-trigger)
  - [9.8 LLM Interaction Trigger](#98-llm-interaction-trigger)
- [10. Git Repository Handling (`git_handler.py`)](#10-git-repository-handling-git_handlerpy)
  - [10.1 Function Signature](#101-function-signature)
  - [10.2 Interaction with `config.py`](#102-interaction-with-configpy)
  - [10.3 Interaction with `output_builder.py`](#103-interaction-with-output_builderpy)
  - [10.4 Pull/Clone Logic](#104-pullclone-logic)
  - [10.5 Commit Hash Recording](#105-commit-hash-recording)
  - [10.6 Error Handling \& Logging](#106-error-handling--logging)
  - [10.7 Return Value](#107-return-value)
- [11. Output Structure \& Generation (`output_builder.py`)](#11-output-structure--generation-output_builderpy)
  - [11.1 Centralized Numbering \& Renaming](#111-centralized-numbering--renaming)
  - [11.2 Task Output Folder Creation](#112-task-output-folder-creation)
  - [11.3 `_task.md` Generation](#113-_taskmd-generation)
  - [11.4 Model Response File Creation](#114-model-response-file-creation)
- [12. OpenRouter Integration (`llm_api.py`)](#12-openrouter-integration-llm_apipy)
  - [12.1 API Key Management (via `config.py`)](#121-api-key-management-via-configpy)
  - [12.2 Identifying OpenRouter Models](#122-identifying-openrouter-models)
  - [12.3 Parallel Request Execution (`concurrent.futures`)](#123-parallel-request-execution-concurrentfutures)
  - [12.4 Request Construction](#124-request-construction)
  - [12.5 Real-time CLI Feedback (`rich`)](#125-real-time-cli-feedback-rich)
  - [12.6 Response/Error Handling \& Cost Calculation](#126-responseerror-handling--cost-calculation)
  - [12.7 Writing Results/Errors to Files](#127-writing-resultserrors-to-files)
  - [12.8 Final Cost Reporting (Conditional)](#128-final-cost-reporting-conditional)
- [13. CLI User Experience \& Visuals](#13-cli-user-experience--visuals)
- [14. Code Quality \& Standards](#14-code-quality--standards)
- [15. Testing (`pytest`)](#15-testing-pytest)
- [16. Error Handling (General)](#16-error-handling-general)
- [17. Documentation (README.md)](#17-documentation-readmemd)

---

## 1. Overview & Core Philosophy

`nerd-prompt` (`np`) is a Python CLI tool designed for developers to efficiently assemble contextual information from local files, directories, and Git repositories, define specific tasks, optionally interact with LLMs (primarily via OpenRouter, supporting parallel calls), and organize the inputs and outputs systematically within the project structure.

**Core Philosophy:**

*   **Elegance & Simplicity:** The tool must feel intuitive and powerful, minimizing friction for the user. Both interactive and non-interactive modes must be polished.
*   **Developer Experience (DX):** Prioritize clear communication, feedback (using `rich`), and ease of use across all platforms (macOS, Linux, Windows).
*   **Exemplary Code Quality:** The Python codebase must be exceptionally clean, readable, maintainable, robust, fully type-hinted (passing `mypy --strict`), well-documented, and adhere to modern best practices (PEP 8, etc.). It should serve as a model implementation.
*   **Flexibility:** Allow easy mixing of local and remote (Git) sources, target multiple LLMs (OpenRouter auto-processed, others manual placeholders), and customize parameters.
*   **Statefulness:** Persist project-specific preferences (`.npconfig.toml`) to streamline repeated use within the same project directory.
*   **Reproducibility:** Ensure that the exact inputs used for a task, including the specific state of any Git repositories, are clearly documented.

## 2. Target Environment & Dependencies

*   **Python:** Version 3.9 or higher.
*   **Package Manager:** `pip`.
*   **Build System:** Standard `pyproject.toml` (e.g., using `hatch`, `flit`, or `setuptools` with PEP 621 metadata).
*   **Core Runtime Dependencies:**
    *   `rich`: For all styled terminal output (required).
    *   `questionary`: For interactive prompts (required for interactive mode).
    *   `pyperclip`: For cross-platform clipboard access (required).
    *   `requests`: For synchronous HTTP requests to OpenRouter (required).
    *   `python-dotenv`: For loading `.env` files (useful for environment-specific API keys, though global config is primary).
    *   `appdirs`: For locating the platform-specific user configuration directory (required).
    *   `toml` (or `tomli`/`tomli_w` based on Python version): For parsing/writing `.npconfig.toml` (required).
    *   `Typer[all]`: Recommended for parsing non-interactive arguments and generating shell completions (required for non-interactive mode). Alternatives like `argparse` or `Click` are acceptable if strongly preferred, but `Typer` integrates well with `rich`.
*   **Implicit Dependencies:** Standard library modules (`pathlib`, `subprocess`, `os`, `sys`, `datetime`, `fnmatch`, `concurrent.futures`, `re`, `logging`, `shutil`, `threading`).

## 3. Installation

*   The tool must be installable using standard Python practices:
    *   From source: `pip install .` within the project directory containing `pyproject.toml`.
    *   Potentially from PyPI: `pip install nerd-prompt` (requires PyPI release setup).
*   Installation should create an executable script named `np` accessible in the user's PATH.

## 4. Invocation Modes & Entry Point (`__main__.py`)

The tool supports two primary modes of operation, determined at launch based on the presence of command-line arguments.

### 4.1 Interactive Mode (`np`)

*   **Trigger:** Executing `np` with *no command-line arguments*.
*   **Behavior:** Initiates a guided, step-by-step configuration process using `questionary` prompts. Loads defaults from `.npconfig.toml` and prompts the user to confirm or modify settings. Saves the final confirmed preferences (excluding task name/definition) back to `.npconfig.toml`.

### 4.2 Non-Interactive Mode (`np [options]`)

*   **Trigger:** Executing `np` with *one or more command-line arguments*.
*   **Behavior:** Parses arguments using `Typer` (or chosen library). Configuration settings are derived from arguments, falling back to `.npconfig.toml` for unspecified options, and then to built-in defaults. **Does not modify** `.npconfig.toml`. Designed for scripting and direct command execution.

## 5. Code Structure (Multi-File)

The codebase shall be organized into the following modules within the `np` package directory to promote separation of concerns, testability, and maintainability.

### 5.1 `np/__main__.py`

*   **Purpose:** Primary script entry point (allows running via `python -m np`).
*   **Logic:** Imports the main application function (likely from `cli.py` or a shared entry module). Checks `sys.argv` to determine if arguments were passed. Calls the appropriate handler (interactive setup from `interactive.py` or non-interactive setup from `cli.py`). Handles top-level exceptions and sets exit codes.

### 5.2 `np/cli.py`

*   **Purpose:** Defines and handles the non-interactive command-line interface using `Typer`.
*   **Logic:**
    *   Defines the `Typer` application and commands/arguments (see Section 7).
    *   Parses incoming arguments.
    *   Loads configuration defaults from `config.py`.
    *   Merges argument values with defaults according to precedence rules.
    *   Validates argument combinations (e.g., `--task` vs. `--task-file`).
    *   Orchestrates the non-interactive workflow by calling functions in `core.py`, passing the finalized configuration.
    *   Handles the `--set-api-key` flag interaction with `config.py`.
    *   Handles the `-y` (yes) flag to skip confirmation in `core.py`.

### 5.3 `np/interactive.py`

*   **Purpose:** Implements the guided interactive configuration flow using `questionary`.
*   **Logic:**
    *   Defines functions for each interactive step (Sources, LLMs, Name, Task, Advanced).
    *   Uses `questionary` prompt types (`confirm`, `text`, `select`, `path`, `password`).
    *   Loads initial defaults from `config.py`.
    *   Presents current settings and prompts for modifications.
    *   Validates user input during prompts.
    *   Collects user choices into a configuration object.
    *   Handles interaction for API key updates via `config.py`.
    *   Calls `config.py` to save confirmed preferences.
    *   Calls the final confirmation step before handing off to `core.py`.

### 5.4 `np/core.py`

*   **Purpose:** Contains the central processing logic executed *after* the configuration has been determined (by either `cli.py` or `interactive.py`). Orchestrates the main task execution.
*   **Logic:**
    *   Receives the final, validated run configuration (includes, excludes, llms, task name, task def, overrides, etc.).
    *   Calls `git_handler.process_git_repos()` to clone/update specified Git repositories, obtaining the list of local Git source paths.
    *   Performs file discovery using `pathlib`, walking the project root and returned Git paths, applying all include/exclude filters.
    *   Calculates character counts and estimates token count. Reports using `rich`.
    *   Assembles the final merged prompt string (sources + task + suffix).
    *   Copies the merged prompt to the clipboard using `pyperclip`. Reports success.
    *   Calls `output_builder.create_task_output()` to set up the numbered task directory, `_task.md`, and empty response files. Passes necessary metadata (task name, included sources including Git details with commit hashes, token estimate, etc.).
    *   Determines if OpenRouter calls are needed. If so, calls `llm_api.process_llms()`, passing the merged prompt, API key, LLM list, and overrides.
    *   Handles the overall flow and provides high-level progress feedback using `rich`.

### 5.5 `np/config.py`

*   **Purpose:** Manages all configuration persistence and loading.
*   **Logic:**
    *   Defines default values for includes, excludes, LLMs.
    *   Defines the path to `.npconfig.toml` (relative to project root).
    *   Provides functions to `load_project_config()` (reads TOML, handles missing file/errors, returns config object/dict).
    *   Provides functions to `save_project_config()` (writes config object/dict to TOML, **including the `[git_repo_map]` section**). Called only by `interactive.py`.
    *   Manages the global API key:
        *   Uses `appdirs` to find the user config directory path.
        *   Defines the global settings file path (e.g., `settings.toml`).
        *   Provides `load_api_key()` (checks ENV `OPENROUTER_API_KEY` first, then global file).
        *   Provides `save_api_key()` (writes key to the global file, ensuring directory exists and setting permissions if possible).
    *   Provides functions to manage the `git_repo_map` within the project config (e.g., `get_repo_mapping`, `update_repo_mapping`). Called by `git_handler.py`.

### 5.6 `np/git_handler.py`

*   **Purpose:** Isolates all logic related to cloning and updating Git repositories into the `np_output` structure.
*   **Logic:** (See Section 10 for detailed steps)
    *   Takes the list of Git URLs to process.
    *   Interacts with `config.py` to read/update the `git_repo_map`.
    *   Interacts with `output_builder.py` to get the next available folder number for *new* repositories.
    *   Uses `subprocess.run()` to execute `git` commands (pull, clone, rev-parse). Handles command execution errors.
    *   Provides clear logging via `rich` for clone/pull attempts and failures.
    *   Returns the list of local paths to the successfully processed Git repo folders within `np_output` and the corresponding commit hashes.

### 5.7 `np/llm_api.py`

*   **Purpose:** Handles all communication with the OpenRouter API.
*   **Logic:** (See Section 12 for detailed steps)
    *   Takes the final prompt, API key, list of LLMs, and parameter overrides.
    *   Identifies which LLMs are OpenRouter models.
    *   Uses `concurrent.futures.ThreadPoolExecutor` for parallel API requests.
    *   Uses `rich.live` or `Progress` to display real-time status updates for each model (OpenRouter and Manual).
    *   Builds JSON request payloads using `requests`.
    *   Handles responses (parsing content, extracting cost) and errors (network, timeouts, API errors).
    *   Writes successful responses or error details to the appropriate files via `output_builder.py` or by returning results.
    *   Calculates total cost and reports it conditionally.

### 5.8 `np/output_builder.py`

*   **Purpose:** Manages the creation and structure of the `np_output` directory and its contents. Centralizes numbering logic.
*   **Logic:** (See Section 11 for detailed steps)
    *   Provides `get_next_folder_number()`: Scans `np_output`, finds max prefix, determines padding, renames incorrect folders, returns the next available padded number string.
    *   Provides `create_task_output()`: Called by `core.py`. Uses `get_next_folder_number()` to create the numbered task directory (e.g., `np_output/005-my-task/`). Generates `_task.md` with all metadata (including detailed Git source info). Creates empty `.md` files for each target LLM.
    *   Provides helper functions if needed by `llm_api.py` to write content/errors to specific response files.

### 5.9 `np/utils.py`

*   **Purpose:** Contains small, stateless utility functions used across multiple modules.
*   **Logic:** Functions for sanitizing filenames/directory names, validating input formats, common path operations, perhaps simple text processing helpers.

## 6. Configuration & State Management (`config.py`)

### 6.1 Project Configuration (`.npconfig.toml`)

*   **Format:** TOML, allowing comments.
*   **Location:** Project root.
*   **Contents:**
    *   User Preferences (`include`, `exclude`, `llms`, `model_overrides`). These serve as defaults and are updated *only* by interactive mode confirmations.
    *   Internal State (`[git_repo_map]`). This map (`{ "git_url#branch": "NNN-repo-name", ... }`) is updated automatically by `git_handler.py` via `config.py` whenever a new Git repo is processed and assigned a numbered folder. This ensures persistence across runs.
*   **Management:** `config.py` provides load/save functions. Must handle TOML parsing/writing robustly.

### 6.2 Global Configuration (API Key)

*   **Format:** Simple TOML or INI file (e.g., `settings.toml`) in user config dir.
*   **Location:** Determined by `appdirs.user_config_dir('nerd-prompt', 'YourAppNameOrOrg')`.
*   **Contents:** Primarily `OPENROUTER_API_KEY = "sk-or-..."`.
*   **Management:** `config.py` provides load/save functions, prioritizing environment variables (`OPENROUTER_API_KEY`), then the global file. File/directory creation and permissions should be handled carefully.

### 6.3 Configuration Loading & Precedence

*   **Order:** CLI Argument > Interactive Input (Saved to Config) > `.npconfig.toml` Value > Built-in Default.
*   **Implementation:** The functions in `cli.py` and `interactive.py` are responsible for collecting inputs and merging them with defaults loaded from `config.py` to produce the final configuration object passed to `core.py`.

## 7. Non-Interactive Mode Arguments (`cli.py` & `Typer`)

Define using `Typer` for rich help messages and auto-completion support.

*   `--include`: `typer.Option(None, help="Path/glob/URL to include. Repeatable.", show_default=False)` - List[str]
*   `--exclude`: `typer.Option(None, help="Path/glob to exclude (adds to defaults). Repeatable.", show_default=False)` - List[str]
*   `--llm`: `typer.Option(None, help="LLM name (OpenRouter or manual). Repeatable.", show_default=False)` - List[str]
*   `--name`: `typer.Option(..., help="Short name for the task (required).")` - str (Ellipsis `...` makes it required)
*   `--task`: `typer.Option(None, help="Task definition text.")` - str
*   `--task-file`: `typer.Option(None, help="Path to file with task definition.", exists=True, file_okay=True, dir_okay=False, readable=True)` - Path
    *   *Validation:* Add callback to ensure only one of `--task` or `--task-file` is provided.
*   `--param`: `typer.Option(None, help="Override OpenRouter param: MODEL KEY VALUE. Repeatable.", nargs=3)` - List[Tuple[str, str, str]]
*   `--set-api-key`: `typer.Option(False, "--set-api-key", help="Force prompt to enter/update OpenRouter API key.")` - bool
*   `--yes`, `-y`: `typer.Option(False, "-y", "--yes", help="Skip final confirmation prompt.")` - bool

## 8. Core Workflow: Interactive Mode Details (`interactive.py`)

Implement using `questionary` prompts, driven by functions for each logical step.

### 8.1 Initialization & Welcome

Display `rich` header. Load initial config/state from `config.py`.

### 8.2 Step 1: Source Selection (Include/Exclude/Git)

Display current includes/excludes (mentioning `.gitignore`). Prompt `Modify sources?`. If yes, use `questionary.text` (with defaults editable) for includes and excludes. Explain Git URL handling.

### 8.3 Step 2: LLM Selection

Display current LLMs. Prompt `Enter LLM names (space-separated):` using `questionary.text` with current list as default. Explain OpenRouter vs. Manual.

### 8.4 Step 3: Task Naming

Prompt `Enter task name:` using `questionary.text`. No default. Sanitize input.

### 8.5 Step 4: Task Definition

Prompt `Define the task:` using `questionary.select` ("Enter directly" / "Path to file"). Get content via `questionary.text` (editor mode) or `questionary.path`.

### 8.6 Step 5: Advanced Settings (Optional)

Prompt `Configure advanced?`. If yes, offer `Manage API Key?` (`questionary.select`) and `Set custom params?` (`questionary.confirm`). Guide through sub-prompts if needed.

### 8.7 Configuration Saving (`config.py` interaction)

After user confirms settings through the steps, call `config.save_project_config()` to write `include`, `exclude`, `llms`, `model_overrides` (but *not* task name/def) back to `.npconfig.toml`. **Do not** save the `git_repo_map` here; it's managed by `git_handler`.

### 8.8 Final Confirmation

Display a summary table/panel using `rich` showing all configured settings (Sources, Excludes, LLMs, Task Name, Task Def Preview, API Status, Params). Prompt `Proceed?` using `questionary.confirm`. Exit gracefully if 'No', confirming config was saved.

## 9. Core Workflow: Processing Logic (`core.py`)

### 9.1 Orchestration

`core.py` acts as the main conductor after configuration is set.

### 9.2 Git Repository Processing Trigger

Call `git_handler.process_git_repos(git_urls_from_config)` early in the process. Receive back the list of local, numbered Git repo paths and associated commit hashes.

### 9.3 File Discovery & Filtering

Combine project root, specific local includes, and the returned Git repo paths. Walk these paths using `pathlib`. Apply all filters (`.gitignore`, `--exclude`/config `exclude`, `--include`/config `include`). Generate the sorted list of file paths relative to the project root.

### 9.4 Token Estimation & Reporting

Iterate through discovered files, count total characters, estimate tokens (`~NNN tokens`) using a fixed ratio (e.g., 4.0 chars/token), report summary using `rich`.

### 9.5 Merged Prompt Assembly

Construct the final prompt string: `## Source:` headers, file content, `---` separators, Task section, static Output Format suffix.

### 9.6 Clipboard Integration

Use `pyperclip.copy()`. Report success using `rich`, including the estimated token count.

### 9.7 Output Generation Trigger

Call `output_builder.create_task_output()`, passing task name, the list of discovered local file paths, the list of processed Git repo details (URL, branch, commit hash, local path), estimated tokens, and target LLMs.

### 9.8 LLM Interaction Trigger

Check if any OpenRouter models are targeted. If yes, call `llm_api.process_llms()`, passing the merged prompt, API key, LLM list, overrides, and potentially the path to the task output directory for writing results.

## 10. Git Repository Handling (`git_handler.py`)

### 10.1 Function Signature

E.g., `process_git_repos(git_urls: List[str], config_manager: ConfigManager, output_builder: OutputBuilder) -> List[Tuple[str, str, str, Path]]` (returns list of tuples: url, branch, commit_hash, local_path)

### 10.2 Interaction with `config.py`

Requires access to `config.py` functions to:
*   Read the `[git_repo_map]` from `.npconfig.toml`.
*   Update and save the `[git_repo_map]` immediately when a new repo is assigned a number/folder.

### 10.3 Interaction with `output_builder.py`

Requires access to `output_builder.get_next_folder_number()` to obtain a unique, padded number for *new* Git repositories before creating their folder in `np_output`.

### 10.4 Pull/Clone Logic

Implement the "try pull, then clone on failure" strategy:
1.  Determine target numbered path (from map or new assignment).
2.  Create directory if it doesn't exist (`pathlib.Path.mkdir(parents=True, exist_ok=True)`).
3.  Use `subprocess.run(['git', '-C', target_path, 'pull', 'origin', branch], ...)` checking `returncode`.
4.  If pull fails (`returncode != 0`), log warning, `shutil.rmtree(target_path)` (handle errors), then `subprocess.run(['git', 'clone', '--depth', '1', '-b', branch, url, target_path], ...)` checking `returncode`.
5.  Handle authentication implicitly (relies on user's system git config/SSH keys). Do not handle credentials directly.

### 10.5 Commit Hash Recording

After a successful pull or clone, execute `subprocess.run(['git', '-C', target_path, 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True)` to get the exact commit hash. Store this hash alongside the repo details.

### 10.6 Error Handling & Logging

Catch `subprocess.CalledProcessError`, `FileNotFoundError` (if git not found), etc. Log informative messages using `rich` (`[blue]ℹ️`, `[yellow]⚠️`, `[red]❌`). If a repo fails entirely, log the error and skip it, allowing the process to continue with other sources.

### 10.7 Return Value

Return a list containing details for *successfully* processed repos, including the URL, branch, final commit hash, and the absolute/relative path to its numbered folder in `np_output`. This data is needed by `core.py` for file discovery and by `output_builder.py` for `_task.md`.

## 11. Output Structure & Generation (`output_builder.py`)

### 11.1 Centralized Numbering & Renaming

Implement `get_next_folder_number()` robustly. It must scan `np_output`, find the highest existing `NNN-` prefix, determine correct padding (2 or 3 digits), rename any non-conforming folders first (using next available numbers), and then return the next available padded number string. This needs careful handling of potential race conditions if threading were involved, but V1 is likely single-threaded here.

### 11.2 Task Output Folder Creation

Function `create_task_output()` takes the task number (from `get_next_folder_number()`) and sanitized name to create the directory (e.g., `np_output/005-my-task/`).

### 11.3 `_task.md` Generation

Generate `_task.md` within the task folder. Ensure the "Included Context Sources" list accurately reflects:
*   Local files/globs relative to project root.
*   Git repositories: `(git) {URL}#{branch} (Commit: {commit_hash}) -> {relative_path_to_numbered_git_folder}`

### 11.4 Model Response File Creation

Create empty `.md` files (e.g., `google-gemini-pro.md`, `manual-chatgpt.md`) for all LLMs specified for the task.

## 12. OpenRouter Integration (`llm_api.py`)

### 12.1 API Key Management (via `config.py`)

Obtain the API key by calling `config.load_api_key()`.

### 12.2 Identifying OpenRouter Models

Use simple `/` check in name heuristic for V1. Log the assumption.

### 12.3 Parallel Request Execution (`concurrent.futures`)

Use `ThreadPoolExecutor` to submit requests for all identified OpenRouter models concurrently. Max workers can be configurable or default to a reasonable number (e.g., 5-10).

### 12.4 Request Construction

Build the POST request to `https://openrouter.ai/api/v1/chat/completions`. Include `Authorization` header, JSON body with `model`, `messages` (containing the merged prompt), and any default or user-specified overrides (`temperature`, `max_tokens`, etc.) from the configuration. Use `requests.post` with a timeout (e.g., 90-120 seconds).

### 12.5 Real-time CLI Feedback (`rich`)

Implement using `rich.live` context manager or `rich.progress.Progress`:
*   Create a task description for each LLM (e.g., `"[blue]🔄 model-name.md[/] Waiting..."`).
*   Update the description based on status: `"[blue]🔄 model-name.md[/] Sending..."`, `"[green]✅ model-name.md[/] Done"`, `"[red]❌ model-name.md[/] Error"`.
*   For manual models, show static status: `"[yellow]✏️ manual-model.md[/] Pending manual input"`.

### 12.6 Response/Error Handling & Cost Calculation

In the thread processing the response:
*   Check HTTP status code.
*   On 2xx: Parse JSON, extract `choices[0].message.content`. Check for cost information (e.g., in `usage` object or headers - **verify OpenRouter API docs**). Store content and cost.
*   On non-2xx or exception: Log error, extract details if possible, store error message, store cost as 0.

### 12.7 Writing Results/Errors to Files

After a thread finishes, write the obtained LLM content or the formatted error message to the corresponding `.md` file in the task output directory created by `output_builder.py`.

### 12.8 Final Cost Reporting (Conditional)

After all threads complete, sum the costs. If `total_cost > 0`, print the formatted summary using `rich`. Otherwise, print nothing about cost.

## 13. CLI User Experience & Visuals

*   **Mandatory `rich`:** Use for *all* output - headers, prompts, tables, lists, progress bars, spinners, live status updates, error messages, final confirmations. Ensure consistent styling.
*   **Mandatory `questionary`:** Use for *all* interactive prompts. Ensure clear wording and intuitive controls.
*   **Feedback:** Provide constant, unambiguous feedback about what the tool is doing (cloning, pulling, filtering files, estimating tokens, sending requests, writing files).

## 14. Code Quality & Standards

*   **Non-Negotiable:** Code must be of exemplary quality.
*   **Typing:** 100% type hints, validated with `mypy --strict`.
*   **Formatting:** `black`.
*   **Linting:** `ruff` (configure appropriately).
*   **Style:** PEP 8, clear naming, short functions/methods, logical grouping.
*   **Documentation:** Docstrings (Google or reST) for all modules, classes, functions. Comments explain *why*, not *what*.
*   **Readability & Maintainability:** Paramount.

## 15. Testing (`pytest`)

*   **Mandatory:** Comprehensive unit and integration tests using `pytest`.
*   **Coverage:** Test all modules and critical paths:
    *   Argument parsing (`cli.py`).
    *   Interactive flow logic (`interactive.py`, mock `questionary`).
    *   Config loading/saving/precedence (`config.py`).
    *   Git command execution, map handling, commit parsing (`git_handler.py`, mock `subprocess`, `config`, `output_builder`).
    *   Output numbering, renaming, `_task.md` generation (`output_builder.py`).
    *   API request building, parallel execution, response/error parsing, cost extraction (`llm_api.py`, mock `requests`, `ThreadPoolExecutor`).
    *   Core orchestration logic (`core.py`).
*   **CI:** Tests must pass cleanly (no failures or warnings) in a CI environment (e.g., GitHub Actions). Aim for >90% code coverage.

## 16. Error Handling (General)

*   Implement robust `try...except` blocks around I/O operations (file access, network requests, subprocess calls).
*   Catch specific exceptions (`FileNotFoundError`, `PermissionError`, `requests.RequestException`, `subprocess.CalledProcessError`, `toml.TOMLDecodeError`, etc.).
*   Report errors clearly to the user using `rich` formatting (`[red]ERROR:[/]` prefix).
*   Allow the program to continue where feasible (e.g., skip a failing Git repo, skip a failing LLM request) but report all failures.
*   Provide informative exit codes on fatal errors.

## 17. Documentation (README.md)

*   **Mandatory:** Create a comprehensive `README.md`.
*   **Contents:**
    *   Project overview and goals.
    *   Installation instructions.
    *   Detailed usage for **both** interactive (`np`) and non-interactive (`np [args]`) modes.
    *   Complete list and explanation of all non-interactive arguments.
    *   Explanation of the configuration system (`.npconfig.toml` structure including `git_repo_map`, global API key).
    *   **Detailed explanation of the Git repository handling workflow** (cloning/pulling into numbered `np_output` folders, `git_repo_map` persistence, commit hash tracking in `_task.md`).
    *   Description of the `np_output` directory structure and the contents of `_task.md`.
    *   Explanation of OpenRouter integration, parallel calls, and manual placeholders.
    *   Token estimation methodology.
    *   Clear examples of usage.
    *   Contributing guidelines (if applicable).
    *   License information.

---
This document outlines the complete requirements for V1.0 of `nerd-prompt`. The developer should adhere strictly to these specifications, focusing on code quality, robustness, and user experience.