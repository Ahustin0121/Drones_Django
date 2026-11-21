"""
Integración con Cloudflare R2 mediante boto3 (API compatible con S3).

Modo R2: las URLs PUT/GET se firman en el backend y el navegador transfiere
los videos directamente al bucket, sin pasar por Django.

Modo local: si R2 no está configurado, las subidas se guardan en
MEDIA_ROOT/videos para poder probar el flujo completo en desarrollo.
"""
from __future__ import annotations

import mimetypes
from decimal import Decimal
from pathlib import Path

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from gestion.models import Vuelo


class R2NoConfigurado(Exception):
    pass


class ErrorAlmacenamiento(Exception):
    pass


def r2_configurado() -> bool:
    return bool(
        settings.R2_ACCOUNT_ID
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.R2_BUCKET_NAME
    )


def endpoint_r2() -> str:
    return f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"


def cliente_r2():
    if not r2_configurado():
        raise R2NoConfigurado("Cloudflare R2 no está configurado.")
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint_r2(),
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


def key_para_vuelo(vuelo: Vuelo) -> str:
    """Estructura estable de objetos: condominios/{id}/{año}/{mes}/turno_{id}/vuelo_{id}.mp4"""
    inicio = vuelo.hora_inicio
    return (
        f"condominios/{vuelo.turno.condominio_id}/{inicio.year}/{inicio.month:02d}/"
        f"turno_{vuelo.turno_id}/vuelo_{vuelo.id}.mp4"
    )


def generar_presigned_put(key: str, expires: int | None = None) -> str:
    cliente = cliente_r2()
    try:
        return cliente.generate_presigned_url(
            "put_object",
            Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
            ExpiresIn=expires or settings.R2_PRESIGN_EXPIRES,
        )
    except (BotoCoreError, ClientError) as exc:
        raise ErrorAlmacenamiento(f"No se pudo firmar la subida: {exc}") from exc


def generar_presigned_get(key: str, expires: int = 3600) -> str:
    cliente = cliente_r2()
    try:
        return cliente.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": key,
                "ResponseContentType": "video/mp4",
                "ResponseContentDisposition": f'inline; filename="{Path(key).name}"',
            },
            ExpiresIn=expires,
        )
    except (BotoCoreError, ClientError) as exc:
        raise ErrorAlmacenamiento(f"No se pudo firmar la reproducción: {exc}") from exc


# ---------------------------------------------------------------------------
# Modo local de respaldo
# ---------------------------------------------------------------------------
def directorio_local() -> Path:
    ruta = Path(settings.MEDIA_ROOT) / "videos"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_local(key: str) -> Path:
    """Evita cualquier intento de path traversal dentro de MEDIA_ROOT."""
    base = directorio_local().resolve()
    destino = (base / key).resolve()
    if not str(destino).startswith(str(base)):
        raise ErrorAlmacenamiento("Ruta de almacenamiento inválida.")
    return destino


def guardar_video_local(archivo: UploadedFile, key: str) -> Decimal:
    destino = ruta_local(key)
    destino.parent.mkdir(parents=True, exist_ok=True)

    if archivo.size > settings.VIDEO_LOCAL_MAX_BYTES:
        limite_gb = settings.VIDEO_LOCAL_MAX_BYTES / (1024**3)
        raise ErrorAlmacenamiento(f"El archivo supera el límite de {limite_gb:.1f} GB.")

    with destino.open("wb") as salida:
        for chunk in archivo.chunks():
            salida.write(chunk)

    peso_mb = Decimal(archivo.size) / Decimal(1024 * 1024)
    return peso_mb.quantize(Decimal("0.01"))


def existe_video_local(key: str) -> bool:
    return ruta_local(key).is_file()


def peso_video_local_mb(key: str) -> Decimal | None:
    ruta = ruta_local(key)
    if not ruta.is_file():
        return None
    peso = Decimal(ruta.stat().st_size) / Decimal(1024 * 1024)
    return peso.quantize(Decimal("0.01"))


def existe_video_r2(key: str) -> tuple[bool, Decimal | None]:
    """Verifica que el objeto exista en R2 y devuelve su tamaño en MB."""
    cliente = cliente_r2()
    try:
        respuesta = cliente.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    except ClientError as exc:
        codigo = str(exc.response.get("Error", {}).get("Code", ""))
        if codigo in {"404", "NoSuchKey", "NotFound"}:
            return False, None
        raise ErrorAlmacenamiento(f"No se pudo verificar el video en R2: {exc}") from exc
    except BotoCoreError as exc:
        raise ErrorAlmacenamiento(f"No se pudo verificar el video en R2: {exc}") from exc

    tamano = respuesta.get("ContentLength")
    if tamano is None:
        return True, None
    peso = Decimal(tamano) / Decimal(1024 * 1024)
    return True, peso.quantize(Decimal("0.01"))


def tipo_contenido(nombre: str) -> str:
    return mimetypes.guess_type(nombre)[0] or "application/octet-stream"
