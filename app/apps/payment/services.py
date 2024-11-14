import logging
import uuid
from decimal import Decimal

from fastapi_mongo_base._utils import aionetwork
from server.config import Settings
from ufaas_fastapi_business.models import Business

from .models import Payment
from .schemas import (
    ExtensionSchema,
    IPGPurchaseSchema,
    ProposalCreateSchema,
    PurchaseSchema,
    WalletSchema,
)


def purchase_business_url(business: Business, ipg: str) -> str:
    return f"{business.config.api_os_url}/{ipg}/purchases"


async def payments_options(payment: Payment) -> list[ExtensionSchema]:
    business = await Business.get_by_name(payment.business_name)
    available_ipgs_paged = await aionetwork.aio_request(
        url=f"{business.config.api_os_url}/installeds/",
        params={"type": "ipg", "limit": 100},
        headers={"Authorization": f"Bearer {await business.get_access_token()}"},
    )
    # available_ipgs_paged: dict = response.json()
    available_ipgs: list[dict] = available_ipgs_paged.get("items", [])

    if payment.available_ipgs:
        available_ipgs = [
            ipg for ipg in available_ipgs if ipg.get("name") in payment.available_ipgs
        ]
    return [ExtensionSchema(**available_ipg) for available_ipg in available_ipgs]


async def get_wallets(business: Business, user_id: uuid.UUID) -> list[WalletSchema]:
    wallets = await aionetwork.aio_request(
        url=f"{business.config.core_url}api/v1/wallets/",
        params={"user_id": str(user_id), "limit": 100},
        headers={"Authorization": f"Bearer {await business.get_access_token()}"},
    )

    return (
        [WalletSchema(**wallet) for wallet in wallets.get("items")] if wallets else None
    )


async def start_payment(
    payment: Payment,
    business: Business,
    ipg: str,
    *,
    amount: Decimal = None,
    user_id: uuid.UUID = None,
    **kwargs,
) -> dict:
    if payment.is_overdue():
        await payment.fail("Payment is overdue")
        return {"status": False, "message": "Payment is overdue"}

    if amount is None:
        amount = payment.amount

    if not payment.status.is_open():
        return {"status": False, "message": "Payment is not open"}

    callback_url = (
        f"https://{business.domain}{Settings.base_path}/payments/{payment.uid}/verify"
    )
    headers = {
        "Authorization": f"Bearer {await business.get_access_token()}",
        "content-type": "application/json",
    }
    ipg_schema = IPGPurchaseSchema(
        user_id=user_id,
        wallet_id=payment.wallet_id,
        amount=amount,
        description=payment.description,
        phone=payment.phone,
        callback_url=callback_url,
    )
    response = await aionetwork.aio_request(
        method="post",
        url=purchase_business_url(business, ipg),
        data=ipg_schema.model_dump_json(),
        headers=headers,
        timeout=10,
    )
    purchase = PurchaseSchema(uid=response.get("uid"), ipg=ipg, user_id=user_id)
    payment.tries.append(purchase)
    await payment.save()
    return {
        "status": True,
        "uid": payment.uid,
        "url": f"{purchase_business_url(business, ipg)}/{purchase.uid}/start/",
    }


async def verify_payment(business: Business, payment: Payment, **kwargs) -> Payment:
    # if payment.status in ["SUCCESS", "FAILED"]:
    #     return payment

    for try_ in payment.tries:
        if try_.status.is_open():
            url = f"{purchase_business_url(business, try_.ipg)}/{try_.uid}/"
            response = await aionetwork.aio_request(
                method="get",
                url=url,
                headers={
                    "Authorization": f"Bearer {await business.get_access_token()}"
                },
            )
            purchase = PurchaseSchema(**response)
            if not purchase.status.is_open():
                continue
            if purchase.status == "SUCCESS":
                await payment.success_purchase(purchase.uid)
                continue
            elif purchase.status == "FAILED":
                await payment.fail_purchase(purchase.uid)
                continue

    return payment


async def create_proposal(payment: Payment, business: Business) -> dict:
    proposal_data = ProposalCreateSchema(
        amount=payment.amount,
        description=payment.description,
        currency=Settings.currency,
        task_status="init",
        participants=[
            {"wallet_id": payment.wallet_id, "amount": payment.amount},
            {"wallet_id": business.config.income_wallet_id, "amount": -payment.amount},
        ],
        note=None,
        meta_data=None,
    ).model_dump_json()

    access_token = await business.get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "content-type": "application/json",
    }

    response = await aionetwork.aio_request(
        method="post",
        url=business.config.core_url,
        data=proposal_data,
        headers=headers,
        raise_exception=False,
    )
    if "error" in response:
        logging.error(f"Error in create_proposal {response}")
        # raise PayPingException(f"Error in create_proposal {response}")
    return response
