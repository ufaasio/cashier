import logging
import os
from datetime import datetime, timedelta
from typing import AsyncGenerator

import debugpy
import httpx
import pytest
import pytest_asyncio
from beanie import init_beanie
from fastapi_mongo_base import models as base_mongo_models
from ufaas_fastapi_business.models import Business

from server.config import Settings
from server.server import app as fastapi_app
from tests.constants import StaticData


@pytest.fixture(scope="session", autouse=True)
def setup_debugpy():
    if os.getenv("DEBUGPY", "False").lower() in ("true", "1", "yes"):
        debugpy.listen(("0.0.0.0", 3020))
        debugpy.wait_for_client()


@pytest.fixture(scope="session")
def mongo_client():
    from mongomock_motor import AsyncMongoMockClient

    mongo_client = AsyncMongoMockClient()
    yield mongo_client


# Async setup function to initialize the database with Beanie
async def init_db(mongo_client):
    from fastapi_mongo_base._utils.basic import get_all_subclasses

    database = mongo_client.get_database("test_db")
    await init_beanie(
        database=database,
        document_models=get_all_subclasses(base_mongo_models.BaseEntity),
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def db(mongo_client):
    Settings.config_logger()
    logging.info("Initializing database")
    await init_db(mongo_client)
    logging.info("Database initialized")
    yield
    logging.info("Cleaning up database")


@pytest_asyncio.fixture(scope="session")
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Fixture to provide an AsyncClient for FastAPI app."""

    async with httpx.AsyncClient(
        app=fastapi_app, base_url="http://test.uln.me"
    ) as ac:
        yield ac


@pytest.fixture(scope="session")
def constants():
    return StaticData()


@pytest.fixture(scope="module")
def enrollment_dicts():
    now = datetime.now()

    enrollment_dicts = []
    enrollment_dicts.append(
        dict(
            expired_at=now + timedelta(seconds=2),
            bundles=[dict(asset="image", quota=10)],
        )
    )
    enrollment_dicts.append(
        dict(expired_at=None, bundles=[dict(asset="image", quota=10)])
    )
    enrollment_dicts.append(
        dict(
            expired_at=now + timedelta(seconds=11),
            bundles=[dict(asset="image", quota=10)],
            variant="variant",
        )
    )
    enrollment_dicts.append(
        dict(
            expired_at=now + timedelta(seconds=1),
            bundles=[dict(asset="image", quota=10), dict(asset="text", quota=10)],
        )
    )
    enrollment_dicts.append(
        dict(
            expired_at=now + timedelta(seconds=100),
            bundles=[dict(asset="text", quota=10)],
        )
    )
    return enrollment_dicts


@pytest_asyncio.fixture(scope="session")
async def business(constants: StaticData):
    data = dict(
        name=StaticData.business_name_1,
        domain="test.uln.me",
        user_id=StaticData.user_id_1_1,
        uid=StaticData.business_id_1,
    )
    bus = await Business.get_by_origin(data["domain"])

    yield bus


@pytest_asyncio.fixture(scope="session")
async def access_token_business(business: Business):
    data = {"refresh_token": StaticData.refresh_token}

    async with httpx.AsyncClient(base_url="https://sso.uln.me") as client:
        response = await client.post("/auth/refresh", json=data)
        return response.json()["access_token"]


@pytest_asyncio.fixture(scope="session")
async def access_token_user(business: Business):
    data = {"refresh_token": StaticData.refresh_token_user}
    async with httpx.AsyncClient(base_url="https://sso.uln.me") as client:
        response = await client.post("/auth/refresh", json=data)
        return response.json()["access_token"]


@pytest_asyncio.fixture(scope="session")
async def auth_headers_business(access_token_business):
    return {
        "Authorization": f"Bearer {access_token_business}",
        "Content-Type": "application/json",
    }
