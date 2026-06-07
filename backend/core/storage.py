"""
Simple storage utility for raw payload archival.
Uploads to Supabase Storage or S3 when configured, otherwise writes to local `raw_storage/`.
"""
import json
import os
from datetime import datetime
from typing import Any

from backend.core.config import get_settings
from backend.core.supabase import get_supabase_client

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    _HAS_BOTO = True
except Exception:
    _HAS_BOTO = False

settings = get_settings()


def _ensure_local_dir(path: str):
    os.makedirs(path, exist_ok=True)


def upload_raw(payload: Any, key: str) -> str:
    """Upload raw JSON payload.

    - `payload`: JSON-serializable object
    - `key`: object key (without extension), e.g. 'notion/ws123/page_abc'

    Returns a URL or local path to the stored object.
    """
    body = json.dumps(payload, default=str)

    # If Supabase is configured, prefer Supabase Storage for server-side uploads.
    supabase = get_supabase_client()
    if supabase and settings.supabase_service_role_key and settings.supabase_storage_bucket:
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            object_key = f"{key}/{timestamp}.json"
            bucket = supabase.storage.from_(settings.supabase_storage_bucket)
            bucket.upload(
                object_key,
                body.encode("utf-8"),
                {"content-type": "application/json"},
            )
            return f"supabase://{settings.supabase_storage_bucket}/{object_key}"
        except Exception:
            # fall through to S3/local fallback
            pass

    # If AWS is configured and boto3 available, upload to S3
    if _HAS_BOTO and settings.aws_access_key_id and settings.aws_secret_access_key and settings.aws_s3_bucket:
        try:
            region_name = settings.aws_region or os.getenv("AWS_REGION") or "ap-south-1"
            s3 = boto3.client(
                's3',
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=region_name,
            )
            bucket = settings.aws_s3_bucket
            object_key = f"{key}.json"
            s3.put_object(Bucket=bucket, Key=object_key, Body=body.encode('utf-8'))
            return f"s3://{bucket}/{object_key}"
        except (BotoCoreError, ClientError) as e:
            # fallback to local
            pass

    # Local fallback
    storage_dir = os.path.join(os.getcwd(), "raw_storage")
    _ensure_local_dir(storage_dir)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"{key.replace('/', '_')}_{timestamp}.json"
    path = os.path.join(storage_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path
