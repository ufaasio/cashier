from datetime import datetime

from fastapi_mongo_base.models import BusinessOwnedEntity
from fastapi_mongo_base.utils import bsontools
from pydantic import field_serializer, field_validator

from .schemas import PaymentSchema, PaymentStatus


class Payment(PaymentSchema, BusinessOwnedEntity):
    class Settings:
        indexes = BusinessOwnedEntity.Settings.indexes

    @field_validator("amount", mode="before")
    def validate_amount(cls, value):
        return bsontools.decimal_amount(value)

    @field_serializer("status")
    def serialize_status(self, value):
        if isinstance(value, PaymentStatus):
            return value.value
        if isinstance(value, str):
            return value
        return str(value)

    @classmethod
    async def get_payment_by_code(cls, business_name: str, code: str):
        return await cls.find_one(
            cls.is_deleted == False,
            cls.business_name == business_name,
            cls.code == code,
        )

    async def get_business(self):
        from ufaas_fastapi_business.models import Business

        return await Business.get_by_name(self.business_name)

    async def success(self, ref_id: int):
        self.ref_id = ref_id
        self.status = "SUCCESS"
        self.verified_at = datetime.now()
        await self.save()

    async def fail(self, failure_reason: str = None):
        self.status = "FAILED"
        self.failure_reason = failure_reason
        await self.save()

    async def success_purchase(self, uid: str):
        for try_ in self.tries:
            if try_.uid == uid:
                try_.status = "SUCCESS"
                try_.verified_at = datetime.now()
                break
        if self.status == "SUCCESS":
            return
        self.status = "SUCCESS"
        self.verified_at = datetime.now()
        await self.save()

    async def fail_purchase(self, uid: str):
        for try_ in self.tries:
            if try_.uid == uid:
                try_.status = "FAILED"
                try_.verified_at = datetime.now()
                break
        if self.is_overdue():
            self.status = "FAILED"
        await self.save()

    @property
    def is_successful(self):
        return self.status == "SUCCESS"

    @property
    def start_payment_url(self):
        return self.config.payment_request_url(self.code)
