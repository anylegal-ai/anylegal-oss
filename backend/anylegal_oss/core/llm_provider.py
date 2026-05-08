"""
LLM Provider Configuration for AnyLegal

Handles provider-specific configurations and client initialization for different LLM providers.
Supports DeepInfra and OpenRouter with model-specific optimizations and provider selection.
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple, List
from openai import OpenAI, AsyncOpenAI
import httpx

logger = logging.getLogger(__name__)

class LLMProviderConfig:
    """Centralized LLM provider configuration and client management."""

    def __init__(self):

        self.provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.deepinfra_token = os.getenv("DEEPINFRA_TOKEN")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        self.openrouter_provider_order_raw = os.getenv("OPENROUTER_PROVIDER_ORDER", "")
        self.openrouter_provider_order_chat_raw = os.getenv("OPENROUTER_PROVIDER_ORDER_CHAT", "")
        self.openrouter_provider_order_planner_raw = os.getenv("OPENROUTER_PROVIDER_ORDER_PLANNER", "")

        self.openrouter_require_no_logs = os.getenv("OPENROUTER_REQUIRE_NO_LOGS", "false").lower() == "true"
        self.openrouter_ignore_raw = os.getenv("OPENROUTER_IGNORE_PROVIDERS", "")
        self.openrouter_primary_provider = os.getenv("OPENROUTER_PRIMARY_PROVIDER", "Fireworks")
        self.openrouter_secondary_provider = os.getenv("OPENROUTER_SECONDARY_PROVIDER", "DeepInfra")
        self.openrouter_allow_fallbacks = os.getenv("OPENROUTER_ALLOW_FALLBACKS", "true").lower() == "true"

        self.chat_model = os.getenv("CHAT_MODEL")
        self.planner_llm = os.getenv("PLANNER_LLM")
        self.classifier_model = os.getenv("CLASSIFIER_MODEL")
        self.formatting_model = os.getenv("FORMATTING_MODEL")

        self.deepinfra_chat_model = os.getenv("DEEPINFRA_CHAT_MODEL", "deepseek-ai/DeepSeek-V3.1")
        self.deepinfra_planner_llm = os.getenv("DEEPINFRA_PLANNER_LLM", "deepseek-ai/DeepSeek-V3.1")

        self.deepseek_v31_reasoning_effort = os.getenv("DEEPSEEK_V31_REASONING_EFFORT", "medium").lower()
        self.deepseek_v31_planner_reasoning_effort = os.getenv("DEEPSEEK_V31_PLANNER_REASONING_EFFORT", "none").lower()

        logger.info(f"🔧 LLM Provider Configuration:")
        logger.info(f"  - Provider: {self.provider}")
        logger.info(f"  - Chat Model: {self.chat_model}")
        logger.info(f"  - Planner LLM: {self.planner_llm}")
        logger.info(f"  - Classifier Model: {self.classifier_model}")
        logger.info(f"  - Reasoning Effort (Chat): {self.deepseek_v31_reasoning_effort}")
        logger.info(f"  - Reasoning Effort (Planner): {self.deepseek_v31_planner_reasoning_effort}")

        if self.provider == "openrouter":
            provider_order_dbg = self._parse_csv_env(self.openrouter_provider_order_raw)
            chat_order_dbg = self._parse_csv_env(self.openrouter_provider_order_chat_raw)
            planner_order_dbg = self._parse_csv_env(self.openrouter_provider_order_planner_raw)
            ignore_dbg = self._parse_csv_env(self.openrouter_ignore_raw)
            logger.info(f"  - OpenRouter Provider Order (global): {provider_order_dbg if provider_order_dbg else '[not set]'}")
            logger.info(f"  - OpenRouter Provider Order (chat): {chat_order_dbg if chat_order_dbg else '[not set]'}")
            logger.info(f"  - OpenRouter Provider Order (planner): {planner_order_dbg if planner_order_dbg else '[not set]'}")
            logger.info(f"  - OpenRouter Allow Fallbacks: {self.openrouter_allow_fallbacks}")
            logger.info(f"  - OpenRouter Ignore Providers: {ignore_dbg if ignore_dbg else '[]'}")

        self._validate_config()

    def _validate_config(self):
        """Validate provider configuration and API keys."""
        if self.provider == "openrouter":
            if not self.openrouter_api_key:
                logger.error("OpenRouter API key is required when LLM_PROVIDER=openrouter")
                raise ValueError("OPENROUTER_API_KEY environment variable is required for OpenRouter provider")
        elif self.provider == "deepinfra":
            if not self.deepinfra_token:
                logger.error("DeepInfra token is required when LLM_PROVIDER=deepinfra")
                raise ValueError("DEEPINFRA_TOKEN environment variable is required for DeepInfra provider")
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}. Supported providers: deepinfra, openrouter")

        if not self.openai_api_key:
            logger.warning("OpenAI API key not found - embeddings may not work if using OpenAI models")

    def get_provider_config(self, model_type: str = "chat") -> Dict[str, Any]:
        """
        Get provider-specific configuration for client initialization.

        Args:
            model_type: Type of model ("chat", "planner", "classifier", "formatting")

        Returns:
            Dictionary with base_url, api_key, and other provider-specific config
        """
        if self.provider == "openrouter":

            default_headers: Dict[str, str] = {
                "HTTP-Referer": "https://anylegal.ai",
                "X-Title": "AnyLegal.ai",
            }

            provider_order_csv = ""
            if model_type == "planner":
                provider_order_csv = self.openrouter_provider_order_planner_raw or ""
            elif model_type == "chat":
                provider_order_csv = self.openrouter_provider_order_chat_raw or ""

            if not provider_order_csv.strip():
                provider_order_csv = self.openrouter_provider_order_raw or ""
            if provider_order_csv.strip():
                default_headers["X-OpenRouter-Provider-Order"] = provider_order_csv.strip()

            return {
                "api_key": self.openrouter_api_key,
                "base_url": "https://openrouter.ai/api/v1",
                "default_headers": default_headers,
            }
        elif self.provider == "deepinfra":
            return {
                "api_key": self.deepinfra_token,
                "base_url": "https://api.deepinfra.com/v1/openai"
            }
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def get_openrouter_provider_preferences(self, model_type: str = "chat") -> Optional[Dict[str, Any]]:
        """
        Get OpenRouter provider preferences for request body.

        Args:
            model_type: Type of model ("chat", "planner") - uses per-model provider order if configured

        Returns:
            Provider preferences dict for OpenRouter requests, or None if not OpenRouter
        """
        if self.provider != "openrouter":
            return None

        if model_type == "chat" and self.openrouter_provider_order_chat_raw:
            provider_order = self._parse_csv_env(self.openrouter_provider_order_chat_raw)
            logger.debug(f"Using CHAT provider order: {provider_order}")
        elif model_type == "planner" and self.openrouter_provider_order_planner_raw:
            provider_order = self._parse_csv_env(self.openrouter_provider_order_planner_raw)
            logger.debug(f"Using PLANNER provider order: {provider_order}")
        else:
            provider_order = self._parse_csv_env(self.openrouter_provider_order_raw)
            logger.debug(f"Using GLOBAL provider order: {provider_order}")

        if not provider_order:
            logger.debug("No provider order configured - OpenRouter will auto-route")
            return None

        provider_block: Dict[str, Any] = {
            "order": provider_order,
            "allow_fallbacks": self.openrouter_allow_fallbacks
        }

        ignore_list = self._parse_csv_env(self.openrouter_ignore_raw)
        if ignore_list:
            provider_block["ignore"] = ignore_list
            logger.debug(f"Ignoring providers: {ignore_list}")

        if self.openrouter_require_no_logs:
            provider_block["data_collection"] = "deny"
            logger.info("OpenRouter: Requiring no-logs providers (data_collection=deny)")

        logger.info(f"OpenRouter provider preferences ({model_type}): order={provider_order}")
        return provider_block

    def _parse_csv_env(self, raw: str) -> List[str]:
        if not raw:
            return []

        items = [item.strip() for item in raw.split(',')]
        return [i for i in items if i]

    def get_model_name(self, model_type: str = "chat") -> str:
        """
        Get the model name for the specified model type and current provider.

        Args:
            model_type: Type of model ("chat", "planner", "classifier", "formatting")

        Returns:
            Model name string for the current provider
        """
        if model_type == "chat":
            return self.chat_model if self.provider == "openrouter" else self.deepinfra_chat_model
        elif model_type == "planner":
            return self.planner_llm if self.provider == "openrouter" else self.deepinfra_planner_llm
        elif model_type == "classifier":
            return self.classifier_model
        elif model_type == "formatting":
            return self.formatting_model
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

    def is_deepseek_v31_model(self, model_name: str) -> bool:
        """Check if the model is a DeepSeek V3.1 model (works for both providers)."""
        if not model_name:
            return False
        model_lower = model_name.lower()
        return ("deepseek" in model_lower and 
                ("v3.1" in model_lower or "chat-v3.1" in model_lower or "deepseek-v3.1" in model_lower))

    def is_deepseek_r1_model(self, model_name: str) -> bool:
        """Check if the model is a DeepSeek R1 model."""
        if not model_name:
            return False
        model_lower = model_name.lower()
        return ("deepseek" in model_lower and "r1" in model_lower)

    def supports_reasoning(self, model_name: str) -> bool:
        """Check if the model supports reasoning tokens."""
        return (self.is_deepseek_v31_model(model_name) or self.is_deepseek_r1_model(model_name)) and self.provider == "openrouter"

    def get_reasoning_config(self, model_name: str, is_planner: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get OpenRouter reasoning configuration for the specified model.

        Args:
            model_name: Name of the model
            is_planner: Whether this is being used for planning

        Returns:
            Reasoning configuration dict for OpenRouter API, or None if not applicable
        """
        if not self.supports_reasoning(model_name):
            return None

        effort = self.deepseek_v31_planner_reasoning_effort if is_planner else self.deepseek_v31_reasoning_effort

        if effort == "none":
            return {"enabled": False}

        return {
            "effort": effort,
            "exclude": False                                                   
        }

    def create_sync_client(self, model_type: str = "chat", timeout: float = 300.0) -> OpenAI:
        """
        Create a synchronous OpenAI client for the current provider.

        Args:
            model_type: Type of model this client will be used for
            timeout: Request timeout in seconds

        Returns:
            Configured OpenAI client
        """
        config = self.get_provider_config(model_type)

        http_client = httpx.Client(timeout=timeout)

        client_kwargs = {
            "api_key": config["api_key"],
            "base_url": config["base_url"],
            "http_client": http_client,
            "max_retries": 2
        }

        if "default_headers" in config:
            client_kwargs["default_headers"] = config["default_headers"]

        return OpenAI(**client_kwargs)

    def create_async_client(self, model_type: str = "chat", timeout: float = 300.0) -> AsyncOpenAI:
        """
        Create an asynchronous OpenAI client for the current provider.

        Args:
            model_type: Type of model this client will be used for
            timeout: Request timeout in seconds

        Returns:
            Configured AsyncOpenAI client
        """
        config = self.get_provider_config(model_type)

        async_http_client = httpx.AsyncClient(timeout=timeout)

        client_kwargs = {
            "api_key": config["api_key"],
            "base_url": config["base_url"],
            "http_client": async_http_client,
            "max_retries": 2
        }

        if "default_headers" in config:
            client_kwargs["default_headers"] = config["default_headers"]

        return AsyncOpenAI(**client_kwargs)

    def get_completion_params(self, model_name: str, is_planner: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Get completion parameters optimized for the current provider and model.

        Args:
            model_name: Name of the model
            is_planner: Whether this is being used for planning
            **kwargs: Additional parameters that override defaults

        Returns:
            Dictionary of optimized parameters
        """
        params = {}

        if self.provider == "openrouter":
            provider_prefs: Optional[Dict[str, Any]] = None
            try:

                if is_planner:
                    planner_order = self._parse_csv_env(self.openrouter_provider_order_planner_raw)
                    if planner_order:
                        provider_prefs = {
                            "order": planner_order,
                            "allow_fallbacks": self.openrouter_allow_fallbacks,
                        }
                else:
                    chat_order = self._parse_csv_env(self.openrouter_provider_order_chat_raw)
                    if chat_order:
                        provider_prefs = {
                            "order": chat_order,
                            "allow_fallbacks": self.openrouter_allow_fallbacks,
                        }

                if not provider_prefs:
                    provider_prefs = self.get_openrouter_provider_preferences()

                if provider_prefs:
                    ignore_list = self._parse_csv_env(self.openrouter_ignore_raw)
                    if ignore_list:
                        provider_prefs = {**provider_prefs, "ignore": ignore_list}
            except Exception:
                provider_prefs = self.get_openrouter_provider_preferences()

            if provider_prefs:
                params["provider"] = provider_prefs
                logger.info(f"🎯 OpenRouter provider preferences for {model_name} (is_planner={is_planner}): {provider_prefs}")
            else:
                logger.info(f"🎯 No OpenRouter provider preferences set for {model_name} (is_planner={is_planner})")

        if self.provider == "openrouter" and (self.is_deepseek_v31_model(model_name) or self.is_deepseek_r1_model(model_name)):
            reasoning_config = self.get_reasoning_config(model_name, is_planner)
            if reasoning_config:
                params["reasoning"] = reasoning_config
                logger.debug(f"Added OpenRouter reasoning config for {model_name}: {reasoning_config}")

        params.update({
            "temperature": kwargs.get("temperature", 0.1),
            "top_p": kwargs.get("top_p", 1.0)
        })

        params.update(kwargs)

        params = {k: v for k, v in params.items() if v is not None}

        return params

class _LLMProviderProxy:
    """Proxy class for lazy-loading LLM provider configuration."""

    def __init__(self):
        self._instance: Optional[LLMProviderConfig] = None

    def _get_instance(self) -> LLMProviderConfig:
        if self._instance is None:
            self._instance = LLMProviderConfig()
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_instance(), name)

llm_provider = _LLMProviderProxy()