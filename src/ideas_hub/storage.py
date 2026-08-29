import asyncio

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ideas_hub.config import get_settings


class ObjectStore:
    def __init__(self) -> None:
        s = get_settings()
        self.bucket = s.minio_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if s.minio_secure else 'http'}://{s.minio_endpoint}",
            aws_access_key_id=s.minio_access_key,
            aws_secret_access_key=s.minio_secret_key,
        )

    @retry(
        retry=retry_if_exception_type((BotoCoreError, ClientError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(8),
        reraise=True,
    )
    async def ensure_bucket(self) -> None:
        def _ensure() -> None:
            existing = {x["Name"] for x in self.client.list_buckets().get("Buckets", [])}
            if self.bucket not in existing:
                self.client.create_bucket(Bucket=self.bucket)

        await asyncio.to_thread(_ensure)

    async def put_text(self, key: str, text: str, content_type: str = "text/html") -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType=content_type,
        )
