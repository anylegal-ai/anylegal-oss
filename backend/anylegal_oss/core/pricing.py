"""
Model Registry and Pricing System for AnyLegal

Handles:
- Approved model list (from environment)
- OpenRouter price fetching and caching
- Per-action cost calculation based on actual token usage
- Model tier validation
"""

import os
import logging
import json
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class ModelInfo:
    """Information about an approved model."""
    id: str                                               
    display_name: str                                     
    min_tier: str                                                        
    capabilities: List[str]                                                              
    input_price: float = 0.0                                              
    output_price: float = 0.0                                                  
    context_window: int = 0                            
    is_open_source: bool = False                                
    is_featured: bool = False                                                 
    provider_info: str = ""                                            
    preferred_providers: List[str] = field(default_factory=list)                                   
    supports_vision: bool = False                                 
    last_price_update: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "min_tier": self.min_tier,
            "capabilities": self.capabilities,
            "input_price_per_million": self.input_price,
            "output_price_per_million": self.output_price,
            "context_window": self.context_window,
            "is_open_source": self.is_open_source,
            "is_featured": self.is_featured,
            "provider_info": self.provider_info,
            "estimated_cost_per_action": self.estimate_action_cost(),
        }

    def estimate_action_cost(self, avg_input_tokens: int = 2000, avg_output_tokens: int = 1000) -> float:
        """Estimate typical cost per action based on average token usage."""
        input_cost = (avg_input_tokens / 1_000_000) * self.input_price
        output_cost = (avg_output_tokens / 1_000_000) * self.output_price
        return round(input_cost + output_cost, 4)

OPEN_SOURCE_MODELS = {
    "deepseek/", "moonshotai/kimi", "mistralai/", "meta-llama/",
    "qwen/", "01-ai/", "databricks/", "google/gemma", "z-ai/",
    "minimax/"
}

MODELS_CONFIG_PATH = os.getenv("MODELS_CONFIG_PATH", "./config/models.json")

def is_open_source_model(model_id: str) -> bool:
    """Check if model is open-source based on ID prefix."""
    model_lower = model_id.lower()
    return any(prefix in model_lower for prefix in OPEN_SOURCE_MODELS)

class ModelRegistry:
    """
    Manages approved models and their pricing.

    Loads from APPROVED_MODELS_LIST env var, fetches prices from OpenRouter.
    """

    def __init__(self):
        self.models: Dict[str, ModelInfo] = {}
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.price_sync_interval = int(os.getenv("OPENROUTER_PRICE_SYNC_INTERVAL", "24"))         
        self.last_sync: Optional[datetime] = None
        self.default_model = os.getenv("DEFAULT_USER_MODEL", "moonshotai/kimi-k2-0905")

        self._load_approved_models()

        self._sync_prices_if_needed()

    def _load_approved_models(self):
        """
        Load approved models from config file or environment variable.

        Priority:
        1. JSON config file at MODELS_CONFIG_PATH (volume-mounted, survives docker restart)
        2. APPROVED_MODELS_LIST env var (pipe-delimited, requires container recreate)
        3. Empty list with warning
        """

        if os.path.isfile(MODELS_CONFIG_PATH):
            if self._load_models_from_json(MODELS_CONFIG_PATH):
                return

        models_str = os.getenv("APPROVED_MODELS_LIST", "")
        if models_str:
            self._load_models_from_env(models_str)
            return

        logger.warning(
            "No model configuration found. Set MODELS_CONFIG_PATH to a JSON file "
            "or APPROVED_MODELS_LIST env var."
        )

    def _load_models_from_json(self, path: str) -> bool:
        """Load models from a JSON config file. Returns True on success."""
        try:
            with open(path, 'r') as f:
                config = json.load(f)

            models_list = config.get("models", [])
            for entry in models_list:
                model_id = entry.get("id", "")
                if not model_id:
                    continue

                capabilities = entry.get("capabilities", ["chat", "draft", "review", "revise", "proofread"])
                providers = entry.get("providers", [])
                if isinstance(providers, str):
                    providers = [p.strip() for p in providers.split(",") if p.strip()]

                self.models[model_id] = ModelInfo(
                    id=model_id,
                    display_name=entry.get("display_name", self._extract_display_name(model_id)),
                    min_tier=entry.get("tier", "free_trial"),
                    capabilities=capabilities,
                    is_open_source=is_open_source_model(model_id),
                    is_featured=entry.get("featured", True),
                    preferred_providers=providers
                )

            if config.get("default_model"):
                self.default_model = config["default_model"]

            logger.info(f"Loaded {len(self.models)} approved models from {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load models from {path}: {e}")
            return False

    def _load_models_from_env(self, models_str: str):
        """Parse pipe-delimited APPROVED_MODELS_LIST env var."""
        for model_entry in models_str.split(";"):
            model_entry = model_entry.strip()
            if not model_entry:
                continue

            parts = model_entry.split("|")
            if len(parts) < 4:
                logger.warning(f"Invalid model entry (need at least 4 parts): {model_entry}")
                continue

            model_id, display_name, min_tier, capabilities_str = parts[:4]
            capabilities = [c.strip() for c in capabilities_str.split(",")]

            is_featured = False
            if len(parts) >= 5:
                featured_flag = parts[4].strip().upper()
                is_featured = featured_flag in ("Y", "YES", "TRUE", "1")

            preferred_providers = []
            if len(parts) >= 6 and parts[5].strip():
                preferred_providers = [p.strip() for p in parts[5].split(",") if p.strip()]

            self.models[model_id] = ModelInfo(
                id=model_id,
                display_name=display_name,
                min_tier=min_tier,
                capabilities=capabilities,
                is_open_source=is_open_source_model(model_id),
                is_featured=is_featured,
                preferred_providers=preferred_providers
            )

        logger.info(f"Loaded {len(self.models)} approved models from APPROVED_MODELS_LIST env var")

    def _extract_display_name(self, model_id: str) -> str:
        """Extract display name from model ID."""

        name = model_id.split("/")[-1]
        return name.replace("-", " ").title()

    def _sync_prices_if_needed(self):
        """Sync prices from OpenRouter if cache is stale (non-blocking on failure)."""
        if self.last_sync and (datetime.now() - self.last_sync).total_seconds() < self.price_sync_interval * 3600:
            return

        try:
            self.sync_prices_from_openrouter()
        except Exception as e:

            logger.warning(f"Price sync failed (non-blocking): {e}")

    def sync_prices_from_openrouter(self) -> bool:
        """
        Fetch current prices from OpenRouter API.

        OpenRouter endpoint: GET https://openrouter.ai/api/v1/models
        Returns model info including pricing.
        """
        if not self.openrouter_api_key:
            logger.warning("No OpenRouter API key, cannot sync prices")
            return False

        try:
            logger.info("Syncing model prices from OpenRouter...")

            response = httpx.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {self.openrouter_api_key}"},
                timeout=10.0                                             
            )
            response.raise_for_status()

            data = response.json()
            models_data = data.get("data", [])

            updated_count = 0
            for model_data in models_data:
                model_id = model_data.get("id")
                if model_id in self.models:
                    pricing = model_data.get("pricing", {})

                    prompt_price = float(pricing.get("prompt", "0"))
                    completion_price = float(pricing.get("completion", "0"))

                    self.models[model_id].input_price = prompt_price * 1_000_000
                    self.models[model_id].output_price = completion_price * 1_000_000
                    self.models[model_id].context_window = model_data.get("context_length", 0)

                    arch = model_data.get("architecture", {})
                    modality = arch.get("modality", "")
                    self.models[model_id].supports_vision = "image" in modality.split("->")[0]
                    self.models[model_id].last_price_update = datetime.now()
                    updated_count += 1

                    logger.debug(f"Updated {model_id}: ${self.models[model_id].input_price:.2f}/${self.models[model_id].output_price:.2f} per 1M tokens")

            self.last_sync = datetime.now()
            logger.info(f"Price sync complete: updated {updated_count}/{len(self.models)} models")
            return True

        except Exception as e:
            logger.error(f"Failed to sync prices from OpenRouter: {e}")
            return False

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """Get model info by ID."""
        self._sync_prices_if_needed()
        return self.models.get(model_id)

    def get_approved_models(self, user_tier: str = "free_trial", capability: str = None) -> List[ModelInfo]:
        """
        Get list of models available to user based on their tier.

        Args:
            user_tier: User's subscription tier
            capability: Optional filter by capability (e.g., 'chat', 'review')

        Returns:
            List of ModelInfo objects user can access
        """
        self._sync_prices_if_needed()

        tier_order = ["free_trial", "early_adopter", "professional", "business", "unlimited"]

        effective_tier = "unlimited" if user_tier == "demo" else user_tier
        user_tier_idx = tier_order.index(effective_tier) if effective_tier in tier_order else 0

        available = []
        for model in self.models.values():

            if model.min_tier == "system":
                continue

            model_tier_idx = tier_order.index(model.min_tier) if model.min_tier in tier_order else 0
            if user_tier_idx < model_tier_idx:
                continue

            if capability and capability not in model.capabilities:
                continue

            available.append(model)

        return available

    def get_default_model(self) -> str:
        """Get the default model ID for new users."""
        return self.default_model

    def get_model_provider_preferences(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get OpenRouter provider preferences for a specific model.

        Returns provider order dict for extra_body, or None if no specific providers configured.
        """
        model = self.get_model(model_id)

        if not model or not model.preferred_providers:
            return None

        return {
            "order": model.preferred_providers,
            "allow_fallbacks": True                                                     
        }

    def calculate_cost(
        self, 
        model_id: str, 
        prompt_tokens: int, 
        completion_tokens: int
    ) -> Dict[str, Any]:
        """
        Calculate actual cost for an API call based on token usage.

        Args:
            model_id: OpenRouter model ID
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens

        Returns:
            Dict with cost breakdown
        """
        model = self.get_model(model_id)

        if not model:

            logger.warning(f"Model {model_id} not in registry, using estimate")
            input_cost = (prompt_tokens / 1_000_000) * 1.0                
            output_cost = (completion_tokens / 1_000_000) * 2.0                
        else:
            input_cost = (prompt_tokens / 1_000_000) * model.input_price
            output_cost = (completion_tokens / 1_000_000) * model.output_price

        total_cost = input_cost + output_cost

        return {
            "model_id": model_id,
            "model_name": model.display_name if model else model_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(total_cost, 6),
            "is_open_source": model.is_open_source if model else False,
        }

    def validate_model_for_user(self, model_id: str, user_tier: str, capability: str = "chat") -> Dict[str, Any]:
        """
        Validate if user can use a specific model.

        Returns:
            Dict with 'valid' bool and 'reason' if invalid
        """
        model = self.get_model(model_id)

        if not model:
            return {"valid": False, "reason": f"Model {model_id} is not approved"}

        if model.min_tier == "system":
            return {"valid": False, "reason": f"Model {model_id} is for system use only"}

        tier_order = ["free_trial", "early_adopter", "professional", "business", "unlimited"]
        effective_tier = "unlimited" if user_tier == "demo" else user_tier
        user_tier_idx = tier_order.index(effective_tier) if effective_tier in tier_order else 0
        model_tier_idx = tier_order.index(model.min_tier) if model.min_tier in tier_order else 0

        if user_tier_idx < model_tier_idx:
            return {
                "valid": False, 
                "reason": f"Model {model.display_name} requires {model.min_tier} tier or higher"
            }

        if capability not in model.capabilities:
            return {
                "valid": False,
                "reason": f"Model {model.display_name} does not support {capability}"
            }

        return {"valid": True}

_registry: Optional[ModelRegistry] = None

def get_model_registry() -> ModelRegistry:
    """Get the global model registry instance."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry

def get_approved_models(user_tier: str = "free_trial", capability: str = None) -> List[Dict[str, Any]]:
    """Get approved models as list of dicts for API response."""
    registry = get_model_registry()
    models = registry.get_approved_models(user_tier, capability)
    return [m.to_dict() for m in models]

def calculate_action_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> Dict[str, Any]:
    """Calculate cost for an action."""
    registry = get_model_registry()
    return registry.calculate_cost(model_id, prompt_tokens, completion_tokens)

def get_model_info(model_id: str) -> Optional[Dict[str, Any]]:
    """Get model info as dict."""
    registry = get_model_registry()
    model = registry.get_model(model_id)
    return model.to_dict() if model else None

def sync_prices() -> bool:
    """Force a price sync from OpenRouter."""
    registry = get_model_registry()
    return registry.sync_prices_from_openrouter()

PRIVACY_EXPLAINER = {
    "title": "Privacy & Data Handling",
    "summary": (
        "Open-source models run with Zero Data Retention (ZDR) "
        "via OpenRouter. Proprietary models subject to provider terms."
    ),
    "open_source_note": (
        "Open-source models (DeepSeek, Kimi, GLM, Mistral) are routed through OpenRouter "
        "to ZDR-compliant inference providers. Model weights are public — only inference "
        "runs on the provider's servers. Your prompts and outputs are not stored or used "
        "for training."
    ),
    "proprietary_note": (
        "Proprietary models (Anthropic models, Gemini) are routed directly to each provider's API. "
        "Data handling is subject to Anthropic or Google's terms of service."
    ),
    "bullet_points": [
        "Open-source: routed via OpenRouter with ZDR, data never stored or trained on",
        "Proprietary: subject to provider terms (Anthropic, Google)",
        "Open-source = auditable weights, inference on independent servers"
    ]
}

def get_privacy_explainer() -> Dict[str, Any]:
    """Get privacy messaging for UI display."""
    return PRIVACY_EXPLAINER
