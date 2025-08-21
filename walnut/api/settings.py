from fastapi import APIRouter
from pydantic import BaseModel

from walnut.config import settings

router = APIRouter()


class FrontendSettings(BaseModel):
    oidc_enabled: bool
    oidc_provider_name: str


@router.get("/settings/frontend", response_model=FrontendSettings)
async def get_frontend_settings():
    return FrontendSettings(
        oidc_enabled=settings.OIDC_ENABLED,
        oidc_provider_name=settings.OIDC_PROVIDER_NAME,
    )
