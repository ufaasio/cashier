import logging
import uuid
from decimal import Decimal

from apps.config.models import Configuration
from fastapi_mongo_base.core.exceptions import BaseHTTPException
from fastapi_mongo_base.utils import aionetwork
from server.config import Settings
from ufaas_fastapi_business.models import Business

from .models import Payment
from .schemas import (
    ExtensionSchema,
    IPGPurchaseSchema,
    ProposalCreateSchema,
    PurchaseSchema,
    PurchaseStatus,
    WalletSchema,
)


def purchase_business_url(business: Business, ipg: str) -> str:
    return f"{business.config.api_os_url}/{ipg}/purchases/"


async def payments_options(payment: Payment) -> list[ExtensionSchema]:
    business = await Business.get_by_name(payment.business_name)
    available_ipgs_paged = await aionetwork.aio_request(
        url=f"{business.config.api_os_url}/installeds/",
        params={"type": "ipg", "limit": 100},
        headers={"Authorization": f"Bearer {await business.get_access_token()}"},
    )
    # available_ipgs_paged: dict = response.json()
    available_ipgs: list[dict] = available_ipgs_paged.get("items", [])
    # TODO filter by currency

    if payment.available_ipgs:
        available_ipgs = [
            ipg for ipg in available_ipgs if ipg.get("name") in payment.available_ipgs
        ]
    return [ExtensionSchema(**available_ipg) for available_ipg in available_ipgs]


async def get_wallets(business: Business, user_id: uuid.UUID) -> list[WalletSchema]:
    logging.info(f"{business.name=}, {business.config.core_url}")
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
    phone: str = None,
    **kwargs,
) -> dict:
    if payment.is_overdue():
        await payment.fail("Payment is overdue")
        return {
            "status": False,
            "message": "Payment is overdue",
            "error": "payment_overdue",
        }

    if amount is None:
        amount = payment.amount

    if not payment.status.is_open():
        return {
            "status": False,
            "message": f"Payment was {payment.status}",
            "error": "invalid_payment",
        }

    callback_url = (
        f"https://{business.domain}{Settings.base_path}/payments/{payment.uid}/verify"
    )
    headers = {"Authorization": f"Bearer {await business.get_access_token()}"}
    ipg_schema = IPGPurchaseSchema(
        user_id=user_id,
        wallet_id=payment.wallet_id,
        amount=amount,
        description=payment.description,
        callback_url=callback_url,
        phone=phone,
    )
    logging.info(f"{ipg_schema=}")
    response = await aionetwork.aio_request(
        method="post",
        url=purchase_business_url(business, ipg),
        json=ipg_schema.model_dump(mode="json"),
        headers=headers,
        timeout=10,
    )
    purchase = PurchaseSchema(uid=response.get("uid"), ipg=ipg, user_id=user_id)
    payment.tries.append(purchase)
    payment.status = PurchaseStatus.PENDING
    await payment.save()
    logging.info(f"{purchase=}")
    return {
        "status": True,
        "uid": payment.uid,
        "url": f"{purchase_business_url(business, ipg)}{purchase.uid}/start/",
    }


async def verify_payment(business: Business, payment: Payment, **kwargs) -> Payment:
    # if payment.status in ["SUCCESS", "FAILED"]:
    #     return payment

    for try_ in payment.tries:
        if try_.status.is_open():
            url = f"{purchase_business_url(business, try_.ipg)}{try_.uid}"

            response = await aionetwork.aio_request(
                url=url,
                headers={
                    "Authorization": f"Bearer {await business.get_access_token()}",
                    "Accept-Encoding": "identity",
                },
            )
            purchase = PurchaseSchema(**response, ipg=try_.ipg)
            logging.info(f"verify_payment\n{url=}\n{purchase=}\n{try_=}\n\n")
            if purchase.status.is_open():
                continue
            if purchase.status == "SUCCESS":
                await payment.success_purchase(purchase.uid)
                continue
            elif purchase.status == "FAILED":
                await payment.fail_purchase(purchase.uid)
                continue

    return payment


async def create_proposal(payment: Payment) -> dict:
    business = await payment.get_business()
    # business.config
    config: Configuration = await Configuration.get_config(business.name)

    wallets = await get_wallets(business, payment.user_id)
    logging.info(f"{wallets=}")
    for wallet_ in wallets:
        if wallet_.uid == payment.wallet_id:
            if wallet_.balance.get(payment.currency) >= payment.amount:
                break
            else:
                logging.error(
                    "\n".join(
                        [
                            f"insufficient_funds",
                            f" {payment.amount=}",
                            f"{wallet_.balance.get(payment.currency)=}",
                        ]
                    )
                )
                raise BaseHTTPException(
                    status_code=402,
                    error="insufficient_funds",
                    message="Not enough balance in the wallet",
                )
    else:
        raise BaseHTTPException(
            status_code=404,
            error="wallet_not_found",
            message="Wallet not found",
        )

    proposal_data = ProposalCreateSchema(
        amount=payment.amount,
        description=payment.description,
        currency=payment.currency,
        task_status="init",
        participants=[
            {"wallet_id": payment.wallet_id, "amount": -payment.amount},
            {"wallet_id": config.wallet_id, "amount": payment.amount},
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
