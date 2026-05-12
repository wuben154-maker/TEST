"""Intent Understanding Configuration Loader.

Loads configuration from YAML file with environment variable override support.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
import structlog

logger = structlog.get_logger()


@dataclass
class FileProcessingConfig:
    """File processing configuration."""
    
    small_file_threshold: int = 1048576  # 1 MB
    medium_file_threshold: int = 10485760  # 10 MB
    large_file_threshold: int = 104857600  # 100 MB
    head_lines: int = 500
    tail_lines: int = 500
    middle_sample_size: int = 200
    max_content_length: int = 1000000


@dataclass
class FuzzyMatchingConfig:
    """Fuzzy matching configuration."""
    
    enabled: bool = True
    min_similarity: float = 0.3


@dataclass
class ContextSummaryConfig:
    """Context summary generation configuration."""
    
    # Extraction limits (Stage 1 Enhancement)
    max_entities: int = 20  # Increased from 10
    max_files: int = 10  # Increased from 5
    max_summaries: int = 10  # Increased from 5
    summary_length: int = 200  # Increased from 80-100
    
    # Long-term memory integration (Stage 1 Enhancement)
    include_long_term: bool = True
    long_term_limit: int = 10
    
    # Fallback summary length
    fallback_summary_length: int = 250  # Increased from 100


@dataclass
class ContextConfig:
    """Context retrieval configuration."""
    
    long_term_limit: int = 10
    fuzzy_matching: FuzzyMatchingConfig = field(default_factory=FuzzyMatchingConfig)
    vector_similarity_threshold: float = 0.8  # For future pgvector support
    summary_max_tokens: int = 500
    summary: ContextSummaryConfig = field(default_factory=ContextSummaryConfig)


@dataclass
class LLMConfig:
    """LLM configuration."""
    
    model: str = "gpt-4o-mini"
    temperature: float = 0.1
    max_tokens: int = 1000


@dataclass
class MonitoringConfig:
    """Performance monitoring configuration."""
    
    enabled: bool = True
    slow_operation_threshold: float = 2.0


@dataclass
class IntentConfig:
    """Intent understanding module configuration."""
    
    confidence_threshold: float = 0.7
    max_enrichment_queries: int = 5
    short_term_limit: int = 20
    file_processing: FileProcessingConfig = field(default_factory=FileProcessingConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "IntentConfig":
        """Load configuration from YAML file with environment variable override.
        
        Args:
            config_path: Path to config file. If None, uses default location.
        
        Returns:
            IntentConfig instance
        """
        if config_path is None:
            # Default to config/intent_config.yaml relative to project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "intent_config.yaml"
        
        config_path = Path(config_path)
        
        # Load from YAML if file exists
        config_dict: dict[str, Any] = {}
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_dict = yaml.safe_load(f) or {}
                logger.info("Loaded intent config from file", path=str(config_path))
            except Exception as e:
                logger.warning("Failed to load config file", path=str(config_path), error=str(e))
        
        # Override with environment variables
        config_dict = cls._apply_env_overrides(config_dict)
        
        # Build config object
        return cls._from_dict(config_dict)
    
    @classmethod
    def _apply_env_overrides(cls, config_dict: dict[str, Any]) -> dict[str, Any]:
        """Apply environment variable overrides.
        
        Environment variables use prefix INTENT_ and dot notation:
        - INTENT_CONFIDENCE_THRESHOLD -> confidence_threshold
        - INTENT_FILE_PROCESSING_SMALL_FILE_THRESHOLD -> file_processing.small_file_threshold
        """
        env_prefix = "INTENT_"
        
        for key, value in os.environ.items():
            if not key.startswith(env_prefix):
                continue
            
            # Convert INTENT_CONFIDENCE_THRESHOLD -> confidence_threshold
            config_key = key[len(env_prefix):].lower()
            
            # Handle nested keys (e.g., FILE_PROCESSING_SMALL_FILE_THRESHOLD)
            if "_" in config_key:
                parts = config_key.split("_")
                # Try to find matching nested structure
                current = config_dict
                for i, part in enumerate(parts[:-1]):
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                final_key = parts[-1]
                current[final_key] = cls._parse_env_value(value)
            else:
                config_dict[config_key] = cls._parse_env_value(value)
        
        return config_dict
    
    @staticmethod
    def _parse_env_value(value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Try boolean
        if value.lower() in ("true", "1", "yes", "on"):
            return True
        if value.lower() in ("false", "0", "no", "off"):
            return False
        
        # Try integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
        
        # Return as string
        return value
    
    @classmethod
    def _from_dict(cls, config_dict: dict[str, Any]) -> "IntentConfig":
        """Create IntentConfig from dictionary."""
        # Extract nested configs
        file_processing_dict = config_dict.pop("file_processing", {})
        context_dict = config_dict.pop("context", {})
        llm_dict = config_dict.pop("llm", {})
        monitoring_dict = config_dict.pop("monitoring", {})
        
        # Extract fuzzy_matching and summary from context_dict
        fuzzy_matching_dict = context_dict.pop("fuzzy_matching", {})
        summary_dict = context_dict.pop("summary", {})
        
        # Create nested config objects
        file_processing = FileProcessingConfig(**file_processing_dict)
        fuzzy_matching = FuzzyMatchingConfig(**fuzzy_matching_dict)
        summary = ContextSummaryConfig(**summary_dict)
        context = ContextConfig(**context_dict, fuzzy_matching=fuzzy_matching, summary=summary)
        llm = LLMConfig(**llm_dict)
        monitoring = MonitoringConfig(**monitoring_dict)
        
        # Create main config
        return cls(
            **config_dict,
            file_processing=file_processing,
            context=context,
            llm=llm,
            monitoring=monitoring,
        )


# Global config instance (lazy loaded)
_config: IntentConfig | None = None


def get_config() -> IntentConfig:
    """Get global intent config instance (singleton)."""
    global _config
    if _config is None:
        _config = IntentConfig.load()
    return _config


def reload_config() -> IntentConfig:
    """Reload configuration from file."""
    global _config
    _config = IntentConfig.load()
    return _config
