import hmac
import hashlib
import json
from urllib.parse import parse_qsl
from fastapi import Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.services.user_service import user_service
from app.models.user import User


async def verify_init_data(x_init_data: str = Header(...)) -> dict:
    params = dict(parse_qsl(x_init_data, keep_blank_values=True))
    received_hash = params.pop("hash", "")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData")
    return json.loads(params["user"])


async def get_current_user(
    tg_data: dict = Depends(verify_init_data),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await user_service.get_or_create(db, tg_data)


def verify_internal_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")
