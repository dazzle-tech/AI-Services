"""S3-compatible encrypted object storage."""

from io import BytesIO
from uuid import UUID

import boto3
from botocore.client import Config

from app.core.config import settings


class ObjectStorage:
    """Store and retrieve audio files with server-side encryption."""

    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            use_ssl=settings.s3_use_ssl,
            config=Config(signature_version="s3v4"),
        )
        self._bucket = settings.s3_bucket
        self._encryption = (settings.s3_server_side_encryption or "").strip()
        self._ensure_bucket()

    def _upload_extra_args(self, content_type: str) -> dict[str, str]:
        extra_args = {"ContentType": content_type}
        if self._encryption:
            extra_args["ServerSideEncryption"] = self._encryption
        return extra_args

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            self._client.create_bucket(Bucket=self._bucket)

    def upload_audio(self, session_id: UUID, filename: str, data: bytes, content_type: str) -> str:
        key = f"sessions/{session_id}/{filename}"
        extra_args = self._upload_extra_args(content_type)
        self._client.upload_fileobj(BytesIO(data), self._bucket, key, ExtraArgs=extra_args)
        return f"s3://{self._bucket}/{key}"

    def download_audio(self, audio_uri: str) -> bytes:
        _, _, bucket_and_key = audio_uri.partition("s3://")
        bucket, _, key = bucket_and_key.partition("/")
        buffer = BytesIO()
        self._client.download_fileobj(bucket, key, buffer)
        return buffer.getvalue()

    def delete_audio(self, audio_uri: str) -> None:
        _, _, bucket_and_key = audio_uri.partition("s3://")
        bucket, _, key = bucket_and_key.partition("/")
        self._client.delete_object(Bucket=bucket, Key=key)


def get_object_storage() -> ObjectStorage:
    return ObjectStorage()
