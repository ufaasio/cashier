from fastapi_mongo_base.models import BusinessEntity
from pymongo import ASCENDING, IndexModel

from .schemas import Config


class Configuration(Config, BusinessEntity):
    class Settings:
        indexes = BusinessEntity.Settings.indexes + [
            IndexModel([("business_name", ASCENDING)], unique=True)
        ]

    @classmethod
    async def get_config(cls, business_name: str) -> "Configuration":
        return await cls.find_one({"business_name": business_name})
