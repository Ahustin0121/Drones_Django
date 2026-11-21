"""Limpia los archivos de video locales que superaron la retención."""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from gestion.models import Vuelo
from gestion.services import r2_storage


class Command(BaseCommand):
    help = (
        "Elimina del disco local los videos que superaron la ventana de retención. "
        "Los metadatos del vuelo se conservan para la bitácora histórica."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias",
            type=int,
            default=settings.R2_VIDEO_RETENTION_DAYS,
            help="Días de retención (por defecto 60).",
        )
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Muestra los archivos que se eliminarían sin borrarlos.",
        )

    def handle(self, *args, **opciones):
        dias = opciones["dias"]
        if dias < 1:
            raise ValueError("Los días de retención deben ser mayores que cero.")
        limite = timezone.now() - timedelta(days=dias)
        vuelos = Vuelo.objects.filter(
            video_subido_en__lt=limite, video_r2_key__gt=""
        ).only("id", "video_r2_key", "video_subido_en")

        eliminados = 0
        bytes_liberados = 0
        for vuelo in vuelos.iterator():
            try:
                ruta = r2_storage.ruta_local(vuelo.video_r2_key)
            except r2_storage.ErrorAlmacenamiento:
                continue
            if not ruta.is_file():
                continue
            tamano = ruta.stat().st_size
            if opciones["simular"]:
                self.stdout.write(f"[simulación] {ruta} ({tamano} bytes)")
            else:
                ruta.unlink()
            eliminados += 1
            bytes_liberados += tamano

        estado = "se eliminarían" if opciones["simular"] else "eliminados"
        self.stdout.write(
            self.style.SUCCESS(
                f"{eliminados} archivo(s) {estado}; "
                f"{bytes_liberados / (1024 * 1024):.1f} MB liberados. "
                "Los registros de la bitácora se conservaron."
            )
        )
