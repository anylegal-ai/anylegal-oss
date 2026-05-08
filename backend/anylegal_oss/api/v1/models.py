"""Model selection routes — FastAPI."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from anylegal_oss.db.database import (
    get_user_balance,
    get_user_preferred_model,
    set_user_preferred_model,
)

from anylegal_oss.core.pricing import (
    get_approved_models,
    get_model_info,
    get_privacy_explainer,
    get_model_registry,
)

logger = logging.getLogger(__name__)

OSS_USER_ID = 1

router = APIRouter(prefix="/api/v1", tags=["models"])

@router.get("/models")
def get_models(capability: Optional[str] = None):
    """List approved models available to the user.

    Query params:
        capability: Filter by capability (chat, draft, review, revise, proofread)
    """
    try:
        user_id = OSS_USER_ID

        balance_info = get_user_balance(user_id)
        user_tier = balance_info['subscription_tier'] if balance_info else 'free_trial'

        models = get_approved_models(user_tier, capability)
        preferred_model = get_user_preferred_model(user_id)
        privacy_info = get_privacy_explainer()

        return {
            "models": models,
            "user_tier": user_tier,
            "preferred_model": preferred_model,
            "default_model": get_model_registry().get_default_model(),
            "privacy_info": privacy_info,
        }
    except Exception as e:
        logger.error(f"Error getting models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get models")

@router.get("/models/info/{model_id:path}")
def get_model_details(model_id: str):
    """Get detailed info about a specific model."""
    try:
        model_info = get_model_info(model_id)
        if not model_info:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found or not approved")
        return model_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get model info")

@router.get("/user/model")
def get_user_model():
    """Get the user's current model preference."""
    try:
        user_id = OSS_USER_ID
        preferred_model = get_user_preferred_model(user_id)
        default_model = get_model_registry().get_default_model()

        active_model_id = preferred_model or default_model
        model_info = get_model_info(active_model_id)

        return {
            "preferred_model": preferred_model,
            "default_model": default_model,
            "active_model": active_model_id,
            "model_info": model_info,
        }
    except Exception as e:
        logger.error(f"Error getting user model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get user model")

@router.put("/user/model")
async def set_user_model(request: Request):
    """Set the user's preferred model."""
    try:
        user_id = OSS_USER_ID
        data = await request.json()
        model_id = data.get('model_id')

        if not model_id:
            raise HTTPException(status_code=400, detail="model_id is required")

        balance_info = get_user_balance(user_id)
        user_tier = balance_info['subscription_tier'] if balance_info else 'free_trial'

        registry = get_model_registry()
        validation = registry.validate_model_for_user(model_id, user_tier)
        if not validation['valid']:
            raise HTTPException(status_code=403, detail=validation['reason'])

        if set_user_preferred_model(user_id, model_id):
            model_info = get_model_info(model_id)
            return {"success": True, "preferred_model": model_id, "model_info": model_info}
        raise HTTPException(status_code=500, detail="Failed to set model preference")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting user model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to set model preference")

@router.get("/models/privacy")
def get_privacy_info():
    """Get privacy explainer for model selection."""
    return get_privacy_explainer()
