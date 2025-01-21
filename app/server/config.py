"""FastAPI server configuration."""

import dataclasses
from pathlib import Path

import dotenv
from ufaas_fastapi_business.core import config

dotenv.load_dotenv()


@dataclasses.dataclass
class Settings(config.Settings):
    """Server config settings."""

    base_dir: Path = Path(__file__).resolve().parent.parent
    base_path: str = "/api/v1/apps/cashier"
    currency: str = "IRR"
