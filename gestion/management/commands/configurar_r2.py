"""Configura CORS y la regla de ciclo de vida de 60 días en Cloudflare R2."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from gestion.services import r2_storage


class Command(BaseCommand):
    help = (
        "Aplica CORS y la regla de expiración de videos (60 días por defecto) "
        "al bucket de Cloudflare R2 configurado."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--origen",
            action="append",
            default=[],
            help=(
                "Origen permitido para las subidas del navegador. Puede repetirse. "
                "Ej: --origen https://aerovigia.onrender.com"
            ),
        )
        parser.add_argument(
            "--sin-cors",
            action="store_true",
            help="No modifica la configuración CORS del bucket.",
        )
        parser.add_argument(
            "--sin-ciclo",
            action="store_true",
            help="No modifica la regla de ciclo de vida del bucket.",
        )
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Muestra lo que se aplicaría sin cambiar el bucket.",
        )

    def handle(self, *args, **opciones):
        if not r2_storage.r2_configurado():
            raise CommandError(
                "Cloudflare R2 no está configurado. Define R2_ACCOUNT_ID, "
                "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY y R2_BUCKET_NAME."
            )

        cliente = r2_storage.cliente_r2()
        bucket = settings.R2_BUCKET_NAME
        simulacion = opciones["simular"]

        if not opciones["sin_cors"]:
            origenes = opciones["origen"] or list(settings.CSRF_TRUSTED_ORIGINS)
            if not origenes:
                origenes = ["http://localhost:8000", "http://127.0.0.1:8000"]
            regla_cors = {
                "AllowedOrigins": origenes,
                "AllowedMethods": ["GET", "PUT", "HEAD"],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3600,
            }
            if simulacion:
                self.stdout.write(f"[simulación] CORS en «{bucket}»: {regla_cors}")
            else:
                cliente.put_bucket_cors(
                    Bucket=bucket,
                    CORSConfiguration={"CORSRules": [regla_cors]},
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"CORS aplicado en «{bucket}» para: {', '.join(origenes)}"
                    )
                )

        if not opciones["sin_ciclo"]:
            dias = settings.R2_VIDEO_RETENTION_DAYS
            regla_ciclo = {
                "ID": f"expirar-videos-{dias}-dias",
                "Filter": {"Prefix": "condominios/"},
                "Status": "Enabled",
                "Expiration": {"Days": dias},
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
            }
            if simulacion:
                self.stdout.write(
                    f"[simulación] Ciclo de vida en «{bucket}»: {regla_ciclo}"
                )
            else:
                cliente.put_bucket_lifecycle_configuration(
                    Bucket=bucket,
                    LifecycleConfiguration={"Rules": [regla_ciclo]},
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Regla de ciclo de vida aplicada: los videos se eliminan "
                        f"{dias} días después de su creación."
                    )
                )

        if simulacion:
            self.stdout.write(self.style.WARNING("Simulación completada; no se cambió nada."))
        else:
            self.stdout.write(
                self.style.SUCCESS("Configuración de Cloudflare R2 completada.")
            )
