# app/config.py
import os

def is_prod() -> bool:
    # 约定：WMS_ENV=prod 时视为生产；默认 dev
    return os.getenv("WMS_ENV", "dev").lower() == "prod"
