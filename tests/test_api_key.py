"""
Tests for API key management functionality.
Backs up any existing key, tests with a test key, and restores the original key.
"""

import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from rich.console import Console

from np.config import ConfigManager, API_KEY_ENV_VAR, GLOBAL_CONFIG_DIR_NAME
from np.cli import set_key, verify_key_storage, check_directory_access
import toml

class TestApiKeyManagement(unittest.TestCase):
    """Test suite for API key management functionality."""
    
    def setUp(self):
        """Set up test environment."""
        # Use a temporary directory for tests to avoid affecting real config
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        
        # Create a console with capture to verify output
        self.console = Console(file=MagicMock(), highlight=False)
        
        # Mock ConfigManager to use temporary directory
        self.mock_config_dir = self.temp_path / "config"
        self.mock_config_dir.mkdir(exist_ok=True)
        self.mock_config_path = self.mock_config_dir / "settings.toml"
        
        # Backup any existing environment variable
        self.original_env_key = os.environ.get(API_KEY_ENV_VAR)
        if self.original_env_key:
            os.environ.pop(API_KEY_ENV_VAR)  # Remove during tests
        
        # Mock config_manager
        self.config_manager = ConfigManager(Path.cwd(), self.console)
        self.config_manager.global_config_dir = self.mock_config_dir
        self.config_manager.global_config_path = self.mock_config_path
    
    def tearDown(self):
        """Clean up after tests."""
        # Restore original environment variable if it existed
        if self.original_env_key:
            os.environ[API_KEY_ENV_VAR] = self.original_env_key
        else:
            # Remove if we set it during tests
            if API_KEY_ENV_VAR in os.environ:
                os.environ.pop(API_KEY_ENV_VAR)
        
        # Clean up temp directory
        self.temp_dir.cleanup()
    
    def test_save_and_load_api_key(self):
        """Test saving and loading API key."""
        test_key = "sk-or-test1234567890abcdefghijklmnopqrstuvwxyz"
        
        # Save the key
        success = self.config_manager.save_api_key(test_key)
        self.assertTrue(success, "API key should be saved successfully")
        self.assertTrue(self.mock_config_path.exists(), "Config file should be created")
        
        # Check file contains the key
        with open(self.mock_config_path, "r") as f:
            data = toml.load(f)
        self.assertEqual(data["settings"][API_KEY_ENV_VAR], test_key, 
                         "API key should be stored correctly in config file")
        
        # Load the key and verify it matches
        loaded_key = self.config_manager.load_api_key()
        self.assertEqual(loaded_key, test_key, "Loaded key should match the saved key")
    
    def test_verify_key_storage(self):
        """Test key verification logic."""
        test_key = "sk-or-verify1234567890abcdefghijklmnopqrstuvwxyz"
        
        # Set up a key in the config file
        self.config_manager.save_api_key(test_key)
        
        # Verify matching key succeeds
        success = verify_key_storage(test_key, self.config_manager, self.console)
        self.assertTrue(success, "Verification should succeed for matching key")
        
        # Verify non-matching key fails
        wrong_key = "sk-or-wrongkey123456"
        success = verify_key_storage(wrong_key, self.config_manager, self.console)
        self.assertFalse(success, "Verification should fail for non-matching key")
    
    def test_directory_access_function(self):
        """Test directory access verification function."""
        # Create a new temporary directory
        test_dir = self.temp_path / "test_dir"
        
        # Test successful directory access
        success = check_directory_access(test_dir, self.console)
        self.assertTrue(success, "Directory access should succeed")
        self.assertTrue(test_dir.exists(), "Directory should be created")
    
    @patch('getpass.getpass')
    @patch('typer.confirm')
    @patch('np.cli.ConfigManager')
    def test_set_key_command(self, mock_config_manager_class, mock_confirm, mock_getpass):
        """Test the set_key command functionality."""
        # Set up mocks
        test_key = "sk-or-testcommand1234567890"
        mock_getpass.return_value = test_key
        mock_confirm.return_value = True
        
        # Setup mock config manager instance that will be returned by the class constructor
        mock_config_manager = MagicMock()
        mock_config_manager.global_config_dir = self.mock_config_dir
        mock_config_manager.global_config_path = self.mock_config_path
        mock_config_manager.load_api_key.return_value = None  # No existing key
        mock_config_manager.set_global_api_key.return_value = True  # Success
        mock_config_manager_class.return_value = mock_config_manager
        
        # Call the command with no key argument to test prompting
        set_key(None, force=True)
        
        # Verify the set_global_api_key was called with the test key
        mock_config_manager.set_global_api_key.assert_called_once_with(test_key)
        
        # Test with direct key argument
        direct_key = "sk-or-directkey1234567890"
        mock_config_manager.reset_mock()
        
        set_key(direct_key, force=True)
        
        # Verify set_global_api_key was called with the direct key
        mock_config_manager.set_global_api_key.assert_called_once_with(direct_key)

    def test_masked_key_display(self):
        """Test that keys are properly masked in output."""
        test_key = "sk-or-masktest1234567890abcdefghijklmnopqrstuvwxyz"
        expected_mask = f"{test_key[:8]}...{test_key[-4:]}"
        
        # Save key to test masking in debug output
        self.config_manager.save_api_key(test_key)
        
        # Use a StringIO to capture console output
        import io
        str_io = io.StringIO()
        console = Console(file=str_io, highlight=False)
        
        # Create a config manager that uses the console we can capture
        config_with_capture = ConfigManager(Path.cwd(), console)
        config_with_capture.global_config_dir = self.mock_config_dir
        config_with_capture.global_config_path = self.mock_config_path
        
        # Debug key should mask the output
        config_with_capture.debug_api_key(verbose=True)
        output = str_io.getvalue()
        
        # Check that masked version appears in output but full key does not
        self.assertIn(expected_mask, output, "Masked key should appear in debug output")
        self.assertNotIn(test_key, output, "Full key should not appear in debug output")
        
        # Check key is loaded successfully but masked
        loaded_key = config_with_capture.load_api_key()
        self.assertEqual(loaded_key, test_key, "Full key should be loaded correctly")


if __name__ == '__main__':
    unittest.main() 