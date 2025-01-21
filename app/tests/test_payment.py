import json
import logging
import uuid

import httpx
import json_advanced as json
import pytest
from ufaas_fastapi_business.models import Business

from apps.payment.models import Payment
from apps.payment.services import get_wallets, payments_options
from tests.constants import StaticData

uid = lambda i: uuid.UUID(f"{i:032}")

base_route = "/api/v1/apps/payment"
payment_endpoint = f"{base_route}/payments/"


@pytest.mark.asyncio
async def test_payment_options():
    payment = Payment(
        business_name="pixiee",
        user_id="5a8745b1-784a-4793-bbca-ad2f2b67d101",
        wallet_id="f5024d17-5330-48e8-a3e7-0ec569680c3e",
        amount=10000,
        description="test",
        callback_url="https://app.pixiee.io",
    )
    options = await payments_options(payment)
    logging.info(f"payment_options: {json.dumps(options)}")

    business = await Business.get_by_name(payment.business_name)
    await get_wallets(business, payment.user_id)


@pytest.mark.asyncio
async def test_create_payment(
    client: httpx.AsyncClient, auth_headers_business, constants: StaticData
):
    response = await client.post(
        payment_endpoint,
        headers=auth_headers_business,
        json={
            "wallet_id": constants.wallet_id_1_1,
            "amount": 1000,
            "description": "test",
            "callback_url": "https://forms.pixiee.io/data",
        },
    )
    resp_json = response.json()
    logging.info(f"create_payment: {json.dumps(resp_json)}")
    assert response.status_code == 200
    assert resp_json.get("uid")
