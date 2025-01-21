import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from fastapi_mongo_base.schemas import BaseEntitySchema, BusinessOwnedEntitySchema
from fastapi_mongo_base.utils import bsontools, texttools
from pydantic import BaseModel, field_validator, model_validator
from ufaas_fastapi_business.core.enums import Currency


class ExtensionSchema(BaseEntitySchema):
    name: str
    domain: str
    type: str


class WalletSchema(BusinessOwnedEntitySchema):
    balance: dict[str, Decimal]
    wallet_type: str
    main_currency: str


class PurchaseStatus(str, Enum):
    INIT = "INIT"
    PENDING = "PENDING"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"
    REFUNDED = "REFUNDED"

    def is_open(self):
        return self in [PurchaseStatus.INIT, PurchaseStatus.PENDING]


PaymentStatus = PurchaseStatus


class PurchaseSchema(BaseEntitySchema):
    ipg: str
    user_id: uuid.UUID | None = None

    phone: str | None = None

    status: PurchaseStatus = PurchaseStatus.INIT

    failure_reason: str | None = None
    verified_at: datetime | None = None


class IPGPurchaseSchema(BaseModel):
    user_id: uuid.UUID | None = None
    wallet_id: uuid.UUID
    amount: Decimal

    phone: str | None = None
    description: str  # | None = None
    callback_url: str

    status: PurchaseStatus = PurchaseStatus.INIT


class PaymentCreateSchema(BaseModel):
    user_id: uuid.UUID | None = None
    wallet_id: uuid.UUID | None = None
    basket_id: uuid.UUID | None = None
    amount: Decimal
    currency: Currency = Currency.IRR

    # phone: str | None = None
    description: str

    callback_url: str
    is_test: bool = False

    available_ipgs: list[str] | None = None
    accept_wallet: bool = True
    voucher_code: str | None = None

    @model_validator(mode="before")
    def validate_user_wallet(cls, values: dict):
        if not values.get("user_id") and not values.get("wallet_id"):
            raise ValueError("user_id or wallet_id should be set")
        return values

    @field_validator("amount", mode="before")
    def validate_amount(cls, value):
        return bsontools.decimal_amount(value)

    @field_validator("callback_url", mode="before")
    def validate_callback_url(cls, value):
        if not texttools.is_valid_url(value):
            raise ValueError(f"Invalid URL {value}")
        return value


class PaymentUpdateSchema(BaseModel):
    voucher_code: str | None = None


class PaymentSchema(PaymentCreateSchema, BusinessOwnedEntitySchema):
    status: PaymentStatus = PaymentStatus.INIT
    tries: list[PurchaseSchema] = []
    verified_at: datetime | None = None

    duration: int = 60 * 60  # in seconds

    def is_overdue(self):
        return self.created_at + timedelta(self.duration) < datetime.now()

    @classmethod
    @field_validator("amount", mode="before")
    def validate_amount(cls, value):
        return bsontools.decimal_amount(value)


class PaymentRetrieveSchema(PaymentSchema):
    ipgs: list[ExtensionSchema] | None = None
    wallets: list[WalletSchema] | WalletSchema | None = None


class Participant(BaseModel):
    wallet_id: uuid.UUID
    amount: Decimal


class ProposalCreateSchema(BaseModel):
    amount: Decimal
    description: str | None = None
    note: str | None = None
    currency: Currency = Currency.IRR
    task_status: Literal["draft", "init"] = "draft"
    participants: list[Participant]
    meta_data: dict[str, Any] | None = None


class PaymentStartSchema(BaseModel):
    name: str
    amount: Decimal
    currency: str
    callback_url: str
