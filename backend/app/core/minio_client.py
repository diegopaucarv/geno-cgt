import io
import os
from typing import BinaryIO, List, Optional

import aioboto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile

# Configuración desde variables de entorno (ponlas en tu .env)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "gt-documents")
MINIO_SECURE = (
    os.getenv("MINIO_SECURE", "false").lower() == "true"
)  # false para HTTP local

session = aioboto3.Session()


class MinIOClient:
    def __init__(self):
        self.endpoint = MINIO_ENDPOINT
        self.access_key = MINIO_ACCESS_KEY
        self.secret_key = MINIO_SECRET_KEY
        self.bucket = MINIO_BUCKET
        self.secure = MINIO_SECURE

    async def ensure_bucket_exists(self):
        """Crea el bucket si no existe (se llama al iniciar la app)"""
        async with session.client(
            "s3",
            endpoint_url=f"http{'s' if self.secure else ''}://{self.endpoint}",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure,
        ) as s3:
            try:
                await s3.head_bucket(Bucket=self.bucket)
            except ClientError:
                # El bucket no existe, lo creamos
                await s3.create_bucket(Bucket=self.bucket)
                print(f"Bucket {self.bucket} creado exitosamente")

    async def upload_file(
        self, file: UploadFile, object_key: str, content_type: Optional[str] = None
    ) -> str:
        """
        Sube un archivo a MinIO.
        - file: archivo recibido por FastAPI (UploadFile)
        - object_key: ruta dentro del bucket, ej: "proyectos/123/mi_documento.pdf"
        - content_type: opcional, si no se pasa se intenta detectar
        Retorna la key pública (que puede usarse para descargar después)
        """
        content = await file.read()
        file_size = len(content)

        # Si no se especifica content_type, usar el que trae UploadFile o detectar
        actual_content_type = (
            content_type or file.content_type or "application/octet-stream"
        )

        async with session.client(
            "s3",
            endpoint_url=f"http{'s' if self.secure else ''}://{self.endpoint}",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure,
        ) as s3:
            try:
                await s3.put_object(
                    Bucket=self.bucket,
                    Key=object_key,
                    Body=content,
                    ContentType=actual_content_type,
                    ContentLength=file_size,
                )
                return object_key
            except ClientError as e:
                raise HTTPException(
                    status_code=500, detail=f"Error subiendo archivo: {str(e)}"
                )

    async def download_file(self, object_key: str) -> bytes:
        """Descarga un archivo completo (para archivos pequeños)."""
        async with session.client(
            "s3",
            endpoint_url=f"http{'s' if self.secure else ''}://{self.endpoint}",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure,
        ) as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=object_key)
                return await response["Body"].read()
            except ClientError as e:
                raise HTTPException(
                    status_code=404, detail=f"Archivo no encontrado: {str(e)}"
                )

    async def generate_presigned_url(
        self, object_key: str, expiration: int = 3600
    ) -> str:
        """
        Genera una URL prefirmada para descarga temporal sin autenticación adicional.
        Útil para enviar al frontend y que descargue directamente desde MinIO.
        """
        async with session.client(
            "s3",
            endpoint_url=f"http{'s' if self.secure else ''}://{self.endpoint}",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure,
        ) as s3:
            try:
                url = await s3.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": self.bucket, "Key": object_key},
                    ExpiresIn=expiration,
                )
                return url
            except ClientError as e:
                raise HTTPException(
                    status_code=500, detail=f"Error generando URL: {str(e)}"
                )

    async def delete_file(self, object_key: str) -> bool:
        """Elimina un objeto del bucket."""
        async with session.client(
            "s3",
            endpoint_url=f"http{'s' if self.secure else ''}://{self.endpoint}",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure,
        ) as s3:
            try:
                await s3.delete_object(Bucket=self.bucket, Key=object_key)
                return True
            except ClientError:
                return False

    async def list_files(self, prefix: str = "") -> List[str]:
        """Lista las claves de los objetos dentro de un prefijo (carpeta virtual)."""
        async with session.client(
            "s3",
            endpoint_url=f"http{'s' if self.secure else ''}://{self.endpoint}",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure,
        ) as s3:
            try:
                response = await s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
                if "Contents" not in response:
                    return []
                return [obj["Key"] for obj in response["Contents"]]
            except ClientError:
                return []


# Instancia global para usar en la aplicación
minio_client = MinIOClient()
