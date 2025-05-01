"""
Tests for API key backup and restoration.
This test backs up any existing API key, runs tests with a temporary key,
and then restores the original key.

This test interacts with the actual global config file, not a mock.
"""

import os
import unittest
import time
from pathlib import Path

from rich.console import Console

from np.config import ConfigManager, API_KEY_ENV_VAR, GLOBAL_CONFIG_DIR_NAME
import toml
import appdirs


class TestApiKeyBackupRestore(unittest.TestCase):
    """Test suite for API key backup and restoration."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment - runs once before all tests."""
        cls.console = Console()
        cls.config_manager = ConfigManager(Path.cwd(), cls.console)
        
        # Get the actual path to the global config
        cls.global_config_dir = Path(appdirs.user_config_dir(GLOBAL_CONFIG_DIR_NAME))
        cls.global_config_path = cls.global_config_dir / "settings.toml"
        
        # Backup any existing API key from environment
        cls.original_env_key = os.environ.get(API_KEY_ENV_VAR)
        
        # Backup any existing API key from global config
        cls.original_config_key = None
        cls.original_config_existed = cls.global_config_path.exists()
        
        if cls.original_config_existed:
            try:
                with open(cls.global_config_path, "r", encoding="utf-8") as f:
                    data = toml.load(f)
                cls.original_config_key = data.get("settings", {}).get(API_KEY_ENV_VAR)
            except Exception as e:
                cls.console.print(f"Warning: Could not read original config file: {e}")
        
        # Test information
        cls.test_key = "sk-or-TESTKEY9876543210-DO-NOT-USE"
        
        # Print information about backup
        cls.console.print("[yellow]====== BACKING UP EXISTING API KEY ======[/yellow]")
        if cls.original_env_key:
            masked_env = f"{cls.original_env_key[:8]}...{cls.original_env_key[-4:]}" if len(cls.original_env_key) > 12 else "***"
            cls.console.print(f"Backing up environment key: {masked_env}")
        else:
            cls.console.print("No environment key found")
            
        if cls.original_config_key:
            masked_config = f"{cls.original_config_key[:8]}...{cls.original_config_key[-4:]}" if len(cls.original_config_key) > 12 else "***"
            cls.console.print(f"Backing up config key: {masked_config}")
            cls.console.print(f"Config path: {cls.global_config_path}")
        else:
            cls.console.print(f"No existing key in config: {cls.global_config_path}")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests - runs once after all tests."""
        cls.console.print("[yellow]====== RESTORING ORIGINAL API KEY ======[/yellow]")
        
        # Clear test key from environment if set during tests
        if API_KEY_ENV_VAR in os.environ and os.environ[API_KEY_ENV_VAR] == cls.test_key:
            os.environ.pop(API_KEY_ENV_VAR)
        
        # Restore original environment variable if it existed
        if cls.original_env_key:
            masked_env = f"{cls.original_env_key[:8]}...{cls.original_env_key[-4:]}" if len(cls.original_env_key) > 12 else "***"
            cls.console.print(f"Restoring environment key: {masked_env}")
            os.environ[API_KEY_ENV_VAR] = cls.original_env_key
        
        # Restore original config file and key
        if cls.original_config_key:
            masked_config = f"{cls.original_config_key[:8]}...{cls.original_config_key[-4:]}" if len(cls.original_config_key) > 12 else "***"
            cls.console.print(f"Restoring config key: {masked_config}")
            
            try:
                # Ensure directory exists
                cls.global_config_dir.mkdir(parents=True, exist_ok=True)
                
                # Write original key back to config file
                data = {"settings": {API_KEY_ENV_VAR: cls.original_config_key}}
                with open(cls.global_config_path, "w", encoding="utf-8") as f:
                    toml.dump(data, f)
                cls.console.print("[green]Original key restored successfully[/green]")
            except Exception as e:
                cls.console.print(f"[red]Error restoring original key: {e}[/red]")
        elif not cls.original_config_existed:
            # If there was no config file originally, remove the test one
            try:
                if cls.global_config_path.exists():
                    cls.global_config_path.unlink()
                    cls.console.print(f"[green]Removed test config file: {cls.global_config_path}[/green]")
            except Exception as e:
                cls.console.print(f"[red]Error removing test config file: {e}[/red]")
        else:
            cls.console.print("No original key to restore")
    
    def setUp(self):
        """Set up before each test."""
        # Remove environment key temporarily for tests
        if self.original_env_key and API_KEY_ENV_VAR in os.environ:
            os.environ.pop(API_KEY_ENV_VAR)
    
    def tearDown(self):
        """Clean up after each test."""
        pass  # Individual test cleanup if needed
    
    def test_save_load_with_real_config(self):
        """Test save and load with the real config file."""
        
        # Save the test key
        success = self.config_manager.save_api_key(self.test_key)
        self.assertTrue(success, "API key should be saved successfully")
        self.assertTrue(self.global_config_path.exists(), "Config file should exist")
        
        # Load the key and verify it matches
        loaded_key = self.config_manager.load_api_key()
        self.assertEqual(loaded_key, self.test_key, 
                         "Loaded key should match the saved test key")
        
        # Verify key is properly stored in file
        try:
            with open(self.global_config_path, "r", encoding="utf-8") as f:
                data = toml.load(f)
            stored_key = data.get("settings", {}).get(API_KEY_ENV_VAR)
            self.assertEqual(stored_key, self.test_key, 
                            "Key should be correctly stored in config file")
        except Exception as e:
            self.fail(f"Failed to read config file: {e}")
    
    def test_environment_variable_precedence(self):
        """Test that environment variable takes precedence over config file."""
        # First save to config
        self.config_manager.save_api_key(self.test_key)
        
        # Set a different key in environment
        env_test_key = "sk-or-ENV-TEST-KEY-123456789"
        os.environ[API_KEY_ENV_VAR] = env_test_key
        
        # Load key and verify environment takes precedence
        loaded_key = self.config_manager.load_api_key()
        self.assertEqual(loaded_key, env_test_key, 
                        "Environment variable should take precedence over config file")
        
        # Clean up
        os.environ.pop(API_KEY_ENV_VAR)


if __name__ == '__main__':
    unittest.main() 