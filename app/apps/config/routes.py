from fastapi import Request
from fastapi_mongo_base.core.exceptions import BaseHTTPException
from ufaas_fastapi_business.routes import AbstractAuthRouter
from usso.fastapi import jwt_access_security

from .models import Configuration
from .schemas import Config


class ConfigRouter(AbstractAuthRouter[Configuration, Config]):
    def __init__(self):
        super().__init__(
            model=Configuration,
            schema=Config,
            user_dependency=jwt_access_security,
            # prefix="/configurations",
        )

    async def get_auth(self, request: Request):
        user = await super().get_user(request)
        if not user:
            raise BaseHTTPException(401, "unauthorized", "Unauthorized")
        return user

    async def list_items(self, request: Request, offset: int = 0, limit: int = 10):
        return await super().list_items(request, offset, limit)


router = ConfigRouter().router
