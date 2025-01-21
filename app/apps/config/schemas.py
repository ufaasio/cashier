import uuid

from fastapi_mongo_base.schemas import BusinessEntitySchema


class Config(BusinessEntitySchema):
    wallet_id: uuid.UUID | None = None

    ipgs: list[str] = ["ipg"]
