from beanie import init_beanie
from fastapi_mongo_base._utils import basic
from fastapi_mongo_base.models import BaseEntity
from motor.motor_asyncio import AsyncIOMotorClient

from .config import Settings


async def init_db():
    client = AsyncIOMotorClient(Settings.mongo_uri)
    db = client.get_database(Settings.project_name)
    await init_beanie(
        database=db,
        document_models=[
            cls
            for cls in basic.get_all_subclasses(BaseEntity)
            if not (
                hasattr(cls, "Settings")
                and getattr(cls.Settings, "__abstract__", False)
            )
        ],
    )
    return db
