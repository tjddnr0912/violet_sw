"""
Preference Manager V3 - Persistent User Settings

This module handles loading and saving user preferences for Ver3 GUI,
allowing settings to persist across program restarts.

Features:
- JSON-based persistence
- Automatic file creation
- Validation before save
- Merge with default config
- Backup on save
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import shutil


class PreferenceManagerV3:
    """
    Manager for persistent user preferences.

    Handles:
    - Loading preferences from JSON file
    - Saving preferences with validation
    - Merging user preferences with default config
    - Creating backups before overwriting
    """

    def __init__(self, preference_file: str = 'user_preferences_v3.json'):
        """
        Initialize preference manager.

        Args:
            preference_file: Path to preference file (relative to ver3 directory)
        """
        # Get ver3 directory
        self.ver3_dir = Path(__file__).parent

        # Preference file path
        if os.path.isabs(preference_file):
            self.file_path = Path(preference_file)
        else:
            self.file_path = self.ver3_dir / preference_file

        # Backup directory
        self.backup_dir = self.ver3_dir / 'preference_backups'
        self.backup_dir.mkdir(exist_ok=True)

        # Default preferences structure
        self.default_preferences = {
            'portfolio_config': {
                'max_positions': 2,
                'default_coins': ['BTC', 'ETH', 'XRP']
            },
            'entry_scoring': {
                'min_entry_score': 2,
                'rsi_threshold': 35,
                'stoch_threshold': 20
            },
            'exit_scoring': {
                'chandelier_atr_multiplier': 3.0,
                'tp1_target': 1.5,  # 1.5%
                'tp2_target': 2.5   # 2.5%
            },
            'risk_management': {
                'max_daily_trades': 10,
                'daily_loss_limit_pct': 5.0,
                'max_consecutive_losses': 3,
                'position_amount_krw': 50000
            },
            'last_updated': None
        }

    def load_preferences(self) -> Dict[str, Any]:
        """
        Load preferences from file.

        Returns:
            Preference dictionary. Returns default preferences if file doesn't exist
            or is corrupted.
        """
        if not self.file_path.exists():
            print(f"Preference file not found: {self.file_path}")
            print("Using default preferences.")
            return self.default_preferences.copy()

        try:
            with open(self.file_path, 'r') as f:
                preferences = json.load(f)

            # Validate loaded preferences
            if not self._validate_preferences(preferences):
                print("Loaded preferences failed validation. Using defaults.")
                return self.default_preferences.copy()

            print(f"Loaded preferences from {self.file_path}")
            return preferences

        except json.JSONDecodeError as e:
            print(f"Failed to parse preference file: {e}")
            print("Using default preferences.")
            return self.default_preferences.copy()

        except Exception as e:
            print(f"Error loading preferences: {e}")
            return self.default_preferences.copy()

    def save_preferences(self, preferences: Dict[str, Any]) -> bool:
        """
        Save preferences to file.

        Args:
            preferences: Preference dictionary to save

        Returns:
            True if save successful, False otherwise
        """
        # Validate before saving
        if not self._validate_preferences(preferences):
            print("Preferences failed validation. Not saving.")
            return False

        try:
            # Backup existing file if it exists
            if self.file_path.exists():
                self._create_backup()

            # Add timestamp
            preferences['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Write to file
            with open(self.file_path, 'w') as f:
                json.dump(preferences, f, indent=2)

            print(f"Saved preferences to {self.file_path}")
            return True

        except Exception as e:
            print(f"Failed to save preferences: {e}")
            return False

    def merge_with_config(self, preferences: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge user preferences with default configuration.

        Args:
            preferences: User preferences from file
            config: Default configuration dictionary

        Returns:
            Merged configuration dictionary with user preferences applied
        """
        import copy
        merged_config = copy.deepcopy(config)

        # Merge portfolio config
        if 'portfolio_config' in preferences:
            portfolio_prefs = preferences['portfolio_config']
            if 'max_positions' in portfolio_prefs:
                merged_config['PORTFOLIO_CONFIG']['max_positions'] = portfolio_prefs['max_positions']
            if 'default_coins' in portfolio_prefs:
                merged_config['PORTFOLIO_CONFIG']['default_coins'] = portfolio_prefs['default_coins']

        # Merge entry scoring
        if 'entry_scoring' in preferences:
            entry_prefs = preferences['entry_scoring']
            if 'min_entry_score' in entry_prefs:
                merged_config['ENTRY_SCORING_CONFIG']['min_entry_score'] = entry_prefs['min_entry_score']
            if 'rsi_threshold' in entry_prefs:
                merged_config['INDICATOR_CONFIG']['rsi_oversold'] = entry_prefs['rsi_threshold']
            if 'stoch_threshold' in entry_prefs:
                merged_config['INDICATOR_CONFIG']['stoch_oversold'] = entry_prefs['stoch_threshold']

        # Merge exit scoring
        if 'exit_scoring' in preferences:
            exit_prefs = preferences['exit_scoring']
            if 'chandelier_atr_multiplier' in exit_prefs:
                merged_config['INDICATOR_CONFIG']['chandelier_multiplier'] = exit_prefs['chandelier_atr_multiplier']
            # Note: TP1/TP2 targets are not in the base config structure, handled separately

        # Merge risk management
        if 'risk_management' in preferences:
            risk_prefs = preferences['risk_management']
            if 'max_daily_trades' in risk_prefs:
                merged_config['SAFETY_CONFIG']['max_daily_trades'] = risk_prefs['max_daily_trades']
            if 'daily_loss_limit_pct' in risk_prefs:
                merged_config['RISK_CONFIG']['max_daily_loss_pct'] = risk_prefs['daily_loss_limit_pct']
            if 'max_consecutive_losses' in risk_prefs:
                merged_config['RISK_CONFIG']['max_consecutive_losses'] = risk_prefs['max_consecutive_losses']
            if 'position_amount_krw' in risk_prefs:
                merged_config['POSITION_SIZING_CONFIG']['base_amount_krw'] = risk_prefs['position_amount_krw']

        return merged_config

    def extract_preferences_from_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract user preferences from configuration for saving.

        Args:
            config: Configuration dictionary

        Returns:
            Preference dictionary suitable for saving
        """
        preferences = {
            'portfolio_config': {
                'max_positions': config['PORTFOLIO_CONFIG'].get('max_positions', 2),
                'default_coins': config['PORTFOLIO_CONFIG'].get('default_coins', ['BTC', 'ETH', 'XRP'])
            },
            'entry_scoring': {
                'min_entry_score': config['ENTRY_SCORING_CONFIG'].get('min_entry_score', 2),
                'rsi_threshold': config['INDICATOR_CONFIG'].get('rsi_oversold', 35),
                'stoch_threshold': config['INDICATOR_CONFIG'].get('stoch_oversold', 20)
            },
            'exit_scoring': {
                'chandelier_atr_multiplier': config['INDICATOR_CONFIG'].get('chandelier_multiplier', 3.0),
                'tp1_target': 1.5,  # Default values (not in config)
                'tp2_target': 2.5
            },
            'risk_management': {
                'max_daily_trades': config['SAFETY_CONFIG'].get('max_daily_trades', 10),
                'daily_loss_limit_pct': config['RISK_CONFIG'].get('max_daily_loss_pct', 5.0),
                'max_consecutive_losses': config['RISK_CONFIG'].get('max_consecutive_losses', 3),
                'position_amount_krw': config['POSITION_SIZING_CONFIG'].get('base_amount_krw', 50000)
            },
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        return preferences

    def _validate_preferences(self, preferences: Dict[str, Any]) -> bool:
        """
        Validate preference dictionary structure and values.

        Args:
            preferences: Preference dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        # Check required sections exist
        required_sections = ['portfolio_config', 'entry_scoring', 'exit_scoring', 'risk_management']
        for section in required_sections:
            if section not in preferences:
                print(f"Missing required section: {section}")
                return False

        # Validate portfolio config
        portfolio = preferences['portfolio_config']
        if 'max_positions' in portfolio:
            max_pos = portfolio['max_positions']
            if not isinstance(max_pos, int) or max_pos < 1 or max_pos > 10:
                print(f"Invalid max_positions: {max_pos}")
                return False

        if 'default_coins' in portfolio:
            coins = portfolio['default_coins']
            if not isinstance(coins, list) or len(coins) < 1 or len(coins) > 4:
                print(f"Invalid default_coins: {coins}")
                return False

        # Validate entry scoring
        entry = preferences['entry_scoring']
        if 'min_entry_score' in entry:
            score = entry['min_entry_score']
            if not isinstance(score, int) or score < 1 or score > 4:
                print(f"Invalid min_entry_score: {score}")
                return False

        # Validate exit scoring
        exit_config = preferences['exit_scoring']
        if 'chandelier_atr_multiplier' in exit_config:
            multiplier = exit_config['chandelier_atr_multiplier']
            if not isinstance(multiplier, (int, float)) or multiplier < 1.0 or multiplier > 10.0:
                print(f"Invalid chandelier_atr_multiplier: {multiplier}")
                return False

        # Validate risk management
        risk = preferences['risk_management']
        if 'daily_loss_limit_pct' in risk:
            loss_limit = risk['daily_loss_limit_pct']
            if not isinstance(loss_limit, (int, float)) or loss_limit <= 0 or loss_limit > 50:
                print(f"Invalid daily_loss_limit_pct: {loss_limit}")
                return False

        return True

    def _create_backup(self):
        """Create backup of existing preference file"""
        if not self.file_path.exists():
            return

        try:
            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"user_preferences_v3_backup_{timestamp}.json"
            backup_path = self.backup_dir / backup_filename

            # Copy file
            shutil.copy2(self.file_path, backup_path)
            print(f"Created backup: {backup_path}")

            # Clean old backups (keep last 10)
            self._cleanup_old_backups(keep=10)

        except Exception as e:
            print(f"Failed to create backup: {e}")

    def _cleanup_old_backups(self, keep: int = 10):
        """
        Remove old backup files, keeping only the most recent.

        Args:
            keep: Number of backups to keep
        """
        try:
            # Get all backup files
            backup_files = sorted(
                self.backup_dir.glob('user_preferences_v3_backup_*.json'),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            # Remove old backups
            for backup_file in backup_files[keep:]:
                backup_file.unlink()
                print(f"Removed old backup: {backup_file}")

        except Exception as e:
            print(f"Failed to cleanup old backups: {e}")

    def reset_to_defaults(self) -> bool:
        """
        Reset preferences to default values.

        Returns:
            True if reset successful, False otherwise
        """
        return self.save_preferences(self.default_preferences.copy())

    def get_default_preferences(self) -> Dict[str, Any]:
        """
        Get default preferences.

        Returns:
            Default preference dictionary
        """
        return self.default_preferences.copy()
