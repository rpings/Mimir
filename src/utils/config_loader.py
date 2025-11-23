# -*- coding: utf-8 -*-
"""Configuration loading utilities."""

import os
from pathlib import Path
from typing import Any

import yaml


class ConfigLoader:
    """Load and manage configuration files."""

    def __init__(self, config_dir: str | None = None):
        """Initialize config loader.

        Args:
            config_dir: Configuration directory path. Defaults to 'configs'.
        """
        if config_dir is None:
            config_dir = Path(__file__).parent.parent.parent / "configs"
        self.config_dir = Path(config_dir)
        self._config_cache: dict[str, Any] = {}

    def load_yaml(self, filename: str) -> dict[str, Any]:
        """Load YAML configuration file.

        Args:
            filename: Name of the YAML file to load.

        Returns:
            Dictionary containing configuration data.

        Raises:
            FileNotFoundError: If the configuration file doesn't exist.
            yaml.YAMLError: If the YAML file is invalid.
        """
        filepath = self.config_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Configuration file not found: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            # Replace environment variables
            content = self._substitute_env_vars(content)
            config = yaml.safe_load(content)
            return config or {}

    def _substitute_env_vars(self, content: str) -> str:
        """Substitute environment variables in YAML content.

        Replaces ${VAR_NAME} with actual environment variable values.

        Args:
            content: YAML file content as string.

        Returns:
            Content with environment variables substituted.
        """
        import re

        def replace_var(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        pattern = r"\$\{([^}]+)\}"
        return re.sub(pattern, replace_var, content)

    def get_config(self, filename: str = "config.yml") -> dict[str, Any]:
        """Get configuration, with caching.

        Args:
            filename: Configuration file name.

        Returns:
            Configuration dictionary.
        """
        if filename not in self._config_cache:
            self._config_cache[filename] = self.load_yaml(filename)
        return self._config_cache[filename]

    def get_rss_sources(self) -> list[dict[str, str]]:
        """Get RSS feed sources configuration.

        Returns:
            List of RSS feed configurations.
        """
        sources_config = self.load_yaml("sources/rss.yaml")
        return sources_config.get("feeds", [])

    def get_classification_rules(self) -> dict[str, Any]:
        """Get classification rules configuration.

        Returns:
            Dictionary containing topic and priority rules.
        """
        return self.load_yaml("sources/rules.yaml")

    def get_youtube_channels(self) -> list[dict[str, str]]:
        """Get YouTube channel sources configuration.

        Returns:
            List of YouTube channel configurations.
        """
        try:
            channels_config = self.load_yaml("sources/youtube.yaml")
            return channels_config.get("channels", [])
        except FileNotFoundError:
            # YouTube config is optional
            return []


def load_config(config_dir: str | None = None) -> dict[str, Any]:
    """Convenience function to load main configuration.

    Args:
        config_dir: Configuration directory path.

    Returns:
        Main configuration dictionary.
    """
    loader = ConfigLoader(config_dir)
    return loader.get_config()

