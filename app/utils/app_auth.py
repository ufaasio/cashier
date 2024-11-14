import hashlib
import hmac
from datetime import datetime

from aiocache import cached
from fastapi_mongo_base._utils.aionetwork import aio_request
from pydantic import BaseModel, field_validator


class AppAuth(BaseModel):
    # app_secret: str
    app_id: str
    scopes: list[str]
    timestamp: float
    sso_url: str
    secret: str | None = None

    @field_validator("timestamp")
    def check_timestamp(cls, v: int):
        if datetime.now().timestamp() - v > 60:
            raise ValueError("Timestamp expired.")
        return v

    @property
    def hash_key_part(self):
        scopes_hash = hashlib.sha256("".join(self.scopes).encode()).hexdigest()
        return f"{self.app_id}{scopes_hash}{self.timestamp}{self.sso_url}"

    def check_secret(self, app_secret: bytes | str):
        if type(app_secret) != str:
            app_secret = app_secret.decode("utf-8")

        key = f"{self.hash_key_part}{app_secret}"
        return hmac.compare_digest(
            self.secret, hashlib.sha256(key.encode()).hexdigest()
        )

    def get_secret(self, app_secret: bytes | str):
        if type(app_secret) != str:
            app_secret = app_secret.decode("utf-8")

        key = f"{self.hash_key_part}{app_secret}"
        return hashlib.sha256(key.encode()).hexdigest()


@cached(ttl=10 * 60)
async def get_access_token(
    app_id: str, app_secret, business_sso_url: str, scopes: list[str]
):
    app_auth = AppAuth(
        app_id=app_id,
        scopes=scopes,
        timestamp=datetime.now().timestamp(),
        sso_url=business_sso_url,
    )
    app_auth.secret = app_auth.get_secret(app_secret)
    response = await aio_request(
        method="post",
        url=f"https://sso.ufaas.io/app-auth/access",
        json=app_auth.model_dump(),
    )

    return response
