from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.deps import require_paired
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.schemas.assets import AssetListResponse
from app.services import asset_pack_service
from app.services.asset_pack_service import AssetKind, AssetTier

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/{kind}", response_model=AssetListResponse)
async def list_assets(
    kind: AssetKind,
    mature: bool = False,
    current_user: User = Depends(require_paired),
) -> AssetListResponse:
    return AssetListResponse(
        standard=asset_pack_service.list_ids(kind, AssetTier.STANDARD),
        nsfw=asset_pack_service.list_ids(kind, AssetTier.NSFW) if mature else [],
    )


@router.get("/{kind}/{tier}/{asset_id:path}")
async def get_asset(
    kind: AssetKind,
    tier: AssetTier,
    asset_id: str,
    current_user: User = Depends(require_paired),
) -> FileResponse:
    path = asset_pack_service.path_for(kind, tier, asset_id)
    if path is None:
        raise NotFoundError("asset not found")
    # `private`: authenticated content, so no shared caches; the client's own cache may keep it.
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
