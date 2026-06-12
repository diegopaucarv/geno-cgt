# backend/app/services/almacenamiento.py
import os

from minio import Minio


class GestorDeArchivosMinIO:
    def __init__(self):
        # Lee las credenciales de tu archivo .env que configuraste para Docker
        self.cliente = Minio(
            endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.environ.get("MINIO_ACCESS_KEY"),
            secret_key=os.environ.get("MINIO_SECRET_KEY"),
            secure=False,  # Falso porque en desarrollo local no usas HTTPS
        )
        self.bucket = "corpus-investigacion"
        self._asegurar_bucket_existe()

    def _asegurar_bucket_existe(self):
        if not self.cliente.bucket_exists(self.bucket):
            self.cliente.make_bucket(self.bucket)

    def subir_documento_crudo(self, id_documento: str, archivo_fisico) -> str:
        """
        Sube el PDF o Audio a MinIO y retorna la ruta para guardar en Postgres.
        """
        nombre_destino = f"raw/{id_documento}_{archivo_fisico.filename}"

        self.cliente.put_object(
            bucket_name=self.bucket,
            object_name=nombre_destino,
            data=archivo_fisico.file,
            length=-1,
            part_size=10 * 1024 * 1024,
        )

        # Retornamos la ruta que se guardará en la columna 'ruta_minio' de Postgres
        return f"s3://{self.bucket}/{nombre_destino}"
