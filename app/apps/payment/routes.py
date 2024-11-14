import logging
import uuid
from decimal import Decimal

from core.exceptions import BaseHTTPException
from fastapi import Request
from fastapi.responses import RedirectResponse
from ufaas_fastapi_business.middlewares import authorization_middleware, get_business
from ufaas_fastapi_business.routes import AbstractAuthRouter

from .models import Payment
from .schemas import (
    PaymentCreateSchema,
    PaymentRetrieveSchema,
    PaymentSchema,
    PaymentStatus,
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

    def config_routes(self):
        self.router.add_api_route(
            "/",
            self.list_items,
            methods=["GET"],
            response_model=self.list_response_schema,
            status_code=200,
        )
        self.router.add_api_route(
            "/{uid:uuid}",
            self.retrieve_item,
            methods=["GET"],
            response_model=self.retrieve_response_schema,
            status_code=200,
        )
        self.router.add_api_route(
            "/",
            self.create_item,
            methods=["POST"],
            response_model=self.create_response_schema,
            status_code=201,
        )
        self.router.add_api_route(
            "/start",
            self.start_direct_payment,
            methods=["GET"],
            # response_model=self.retrieve_response_schema,
        )
        self.router.add_api_route(
            "/{uid:uuid}/start",
            self.start_payment,
            methods=["GET"],
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

    async def create_item(self, request: Request, item: PaymentCreateSchema):
        auth = await self.get_auth(request)

        item = self.model(
            business_name=auth.business.name,
            user_id=auth.user_id,
            **item.model_dump(),
        )
        await item.save()
        return self.create_response_schema(**item.model_dump())

        # return await super().create_item(request, item.model_dump())

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
        self, request: Request, uid: uuid.UUID, ipg: str, amount: Decimal = None
    ):
        auth = await self.get_auth(request)
        item: Payment = await self.get_item(uid, business_name=auth.business.name)

        start_data = await start_payment(
            payment=item,
            business=auth.business,
            ipg=ipg,
            amount=amount,
            user_id=auth.user_id,
        )

        if start_data["status"]:
            return RedirectResponse(url=start_data["url"])
        else:
            raise BaseHTTPException(status_code=400, detail=start_data["message"])

    from pydantic import BaseModel

    class VerifyResponse(BaseModel):
        code: str
        refid: str
        clientrefid: str | None = None
        cardnumber: str | None = None
        cardhashpan: str | None = None

    async def verify_payment(
        self,
        request: Request,
        uid: uuid.UUID,
    ):
        logging.info(f"verify_payment: {uid=} {request.method=}")
        try:
            business = await get_business(request)

            item: Payment = await self.get_item(uid, business_name=business.name)
            if item.status != PaymentStatus.PENDING:
                return RedirectResponse(url=item.callback_url, status_code=303)

            payment: Payment = await verify_payment(business=business, item=item)

            if payment.status == PaymentStatus.SUCCESS:
                await create_proposal(payment, business)
                # pass

            return RedirectResponse(
                url=f"{payment.callback_url}?success={payment.is_successful}",
                status_code=303,
            )
        except Exception as e:
            logging.error(f"verify error: {e}")
            raise e


router = PaymentRouter().router
