import logging
import uuid
from decimal import Decimal

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi_mongo_base.core.exceptions import BaseHTTPException
from fastapi_mongo_base.utils import basic
from ufaas_fastapi_business.middlewares import authorization_middleware, get_business
from ufaas_fastapi_business.routes import AbstractAuthRouter

from ..config.models import Configuration
from .models import Payment
from .schemas import (
    PaymentCreateSchema,
    PaymentRetrieveSchema,
    PaymentSchema,
    PaymentStatus,
    PaymentUpdateSchema,
)
from .services import (
    create_proposal,
    get_wallets,
    payments_options,
    start_payment,
    verify_payment,
)


class PaymentRouter(AbstractAuthRouter[Payment, PaymentSchema]):
    def __init__(self):
        super().__init__(model=Payment, schema=PaymentSchema, user_dependency=None)

    def config_schemas(self, schema, **kwargs):
        super().config_schemas(schema)
        self.create_request_schema = PaymentCreateSchema
        self.retrieve_response_schema = PaymentRetrieveSchema

    def config_routes(self, **kwargs):
        super().config_routes(delete_route=False, **kwargs)
        self.router.add_api_route(
            "/start",
            self.start_direct_payment,
            methods=["GET"],
            # response_model=self.retrieve_response_schema,
        )
        self.router.add_api_route(
            "/{uid:uuid}/start",
            self.start_payment,
            methods=["GET", "POST"],
            # response_model=self.retrieve_response_schema,
        )
        self.router.add_api_route(
            "/{uid:uuid}/verify",
            self.verify_payment,
            methods=["GET", "POST"],
        )

    async def get_auth(self, request: Request):
        auth = await authorization_middleware(request, anonymous_accepted=True)
        if request.method in ["POST", "PATCH", "DELETE"]:
            if not auth.user_id:
                raise BaseHTTPException(status_code=401, detail="Unauthorized")
        return auth

    async def retrieve_item(self, request: Request, uid: uuid.UUID):
        auth = await self.get_auth(request)
        logging.info(f"retrieve_item: {uid=}, {auth=}")
        item = await self.get_item(uid, business_name=auth.business.name)
        if auth.user_id:
            wallets = await get_wallets(auth.business, auth.user_id)
        else:
            wallets = None
        options = await payments_options(item)
        return self.retrieve_response_schema(
            **item.model_dump(), ipgs=options, wallets=wallets
        )

    async def create_item(self, request: Request, data: PaymentCreateSchema):
        auth = await self.get_auth(request)

        if not "currency" in data.model_fields_set:
            data.currency = auth.business.config.default_currency

        if not data.available_ipgs:
            configuration: Configuration = await Configuration.get_config(
                auth.business.name
            )
            data.available_ipgs = configuration.ipgs

        item = Payment(
            business_name=auth.business.name,
            user_id=auth.user_id,
            **data.model_dump(exclude=["user_id"]),
        )
        await item.save()
        return item

        # return await super().create_item(request, item.model_dump())

    async def update_item(self, request: Request, data: PaymentUpdateSchema):

        raise NotImplementedError

    async def start_direct_payment(
        self,
        request: Request,
        wallet_id: uuid.UUID,
        amount: Decimal,
        description: str,
        callback_url: str,
        test: bool = False,
    ):
        payment: Payment = await self.create_item(
            request,
            PaymentCreateSchema(
                wallet_id=wallet_id,
                amount=amount,
                description=description,
                callback_url=callback_url,
                is_test=test,
            ),
        )
        logging.info(
            f"start_direct_payment: {wallet_id=}, {amount=}, {description=}, {callback_url=}, {test=}"
        )
        return await self.start_payment(request, payment.uid)

    async def start_payment(
        self, request: Request, uid: uuid.UUID, ipg: str = None, amount: Decimal = None
    ):
        auth = await self.get_auth(request)
        item: Payment = await self.get_item(uid, business_name=auth.business.name)

        logging.info(f"{auth.user_id=} {item.user_id=}")

        if ipg is None:
            ipg = item.available_ipgs[0]

        start_data = await start_payment(
            payment=item,
            business=auth.business,
            ipg=ipg,
            amount=amount,
            user_id=auth.user_id,
            phone=auth.user.phone if auth.user else None,
        )

        if start_data["status"]:
            if request.method == "GET":
                return RedirectResponse(url=start_data["url"])
            else:
                return {"redirect_url": start_data["url"]}

        raise BaseHTTPException(status_code=400, **start_data)

    from pydantic import BaseModel

    class VerifyResponse(BaseModel):
        code: str
        refid: str
        clientrefid: str | None = None
        cardnumber: str | None = None
        cardhashpan: str | None = None

    @basic.try_except_wrapper
    async def verify_payment(
        self,
        request: Request,
        uid: uuid.UUID,
    ):
        business = await get_business(request)

        item: Payment = await self.get_item(uid, business_name=business.name)
        payment_status = item.status

        payment: Payment = await verify_payment(business=business, payment=item)

        if payment.status == PaymentStatus.PENDING:
            # return proper response
            return payment
        if payment.status == PaymentStatus.SUCCESS:
            if payment_status == PaymentStatus.PENDING:
                await create_proposal(payment)
            else:
                logging.info(f"payment was not pending {payment_status=}")

        return RedirectResponse(
            url=f"{payment.callback_url}?success={payment.is_successful}",
            status_code=303,
        )


router = PaymentRouter().router
