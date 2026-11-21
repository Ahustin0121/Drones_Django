"""
Carga datos de demostración para probar la plataforma de inmediato.

Uso:
    python manage.py seed_demo
    python manage.py seed_demo --limpiar   # borra turnos/vuelos y vuelve a generar

Credenciales creadas:
    admin / admin123                  (Administrador)
    pepito.rivas / operador123        (Operador)
    camila.soto / operador123         (Operador)
    diego.fuentes / operador123       (Operador)
"""
import shutil
import subprocess
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from gestion.models import Condominio, Dron, MarcaDron, Turno, Usuario, Vuelo
from gestion.services import r2_storage


class Command(BaseCommand):
    help = "Crea catálogos, usuarios y turnos de demostración."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Elimina los turnos y vuelos existentes antes de generar datos.",
        )
        parser.add_argument(
            "--sin-videos",
            action="store_true",
            help="No genera videos locales de demostración.",
        )

    def handle(self, *args, **opciones):
        self.stdout.write(self.style.MIGRATE_HEADING("Preparando datos de AeroVigía…"))

        if opciones["limpiar"]:
            cantidad = Turno.objects.count()
            Turno.objects.all().delete()
            self.stdout.write(f"  · {cantidad} turno(s) eliminados junto con sus vuelos.")

        usuarios = self._crear_usuarios()
        condominios = self._crear_condominios()
        marcas, drones = self._crear_flota()
        self._crear_turnos(
            usuarios, condominios, drones, generar_videos=not opciones["sin_videos"]
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Datos de demostración listos."))
        self.stdout.write("")
        self.stdout.write("  Administrador : admin / admin123")
        self.stdout.write("  Operadores    : pepito.rivas / operador123")
        self.stdout.write("                  camila.soto / operador123")
        self.stdout.write("                  diego.fuentes / operador123")
        self.stdout.write("")

    # ------------------------------------------------------------------
    def _crear_usuarios(self):
        datos = [
            {
                "username": "admin",
                "password": "admin123",
                "first_name": "Valentina",
                "last_name": "Rojas",
                "email": "admin@aerovigia.cl",
                "rol": Usuario.Rol.ADMIN,
                "es_super": True,
            },
            {
                "username": "pepito.rivas",
                "password": "operador123",
                "first_name": "Pepito",
                "last_name": "Rivas",
                "email": "pepito.rivas@aerovigia.cl",
                "rol": Usuario.Rol.OPERADOR,
            },
            {
                "username": "camila.soto",
                "password": "operador123",
                "first_name": "Camila",
                "last_name": "Soto",
                "email": "camila.soto@aerovigia.cl",
                "rol": Usuario.Rol.OPERADOR,
            },
            {
                "username": "diego.fuentes",
                "password": "operador123",
                "first_name": "Diego",
                "last_name": "Fuentes",
                "email": "diego.fuentes@aerovigia.cl",
                "rol": Usuario.Rol.OPERADOR,
            },
        ]
        usuarios = {}
        for item in datos:
            usuario, creado = Usuario.objects.get_or_create(
                username=item["username"],
                defaults={
                    "first_name": item["first_name"],
                    "last_name": item["last_name"],
                    "email": item["email"],
                    "rol": item["rol"],
                    "is_active": True,
                    "is_staff": item.get("es_super", False),
                    "is_superuser": item.get("es_super", False),
                },
            )
            if creado:
                usuario.set_password(item["password"])
                usuario.save()
            usuarios[item["username"]] = usuario
        self.stdout.write(f"  · Usuarios: {Usuario.objects.count()}")
        return usuarios

    def _crear_condominios(self):
        datos = [
            ("Condominio Los Robles", "Av. Los Robles 1240", "Santiago"),
            ("Condominio Vista Parque", "Camino El Parque 85", "Las Condes"),
            ("Edificio Marina Norte", "Av. Marina 560", "Viña del Mar"),
            ("Condominio Valle Verde", "Los Aromos 321", "Peñalolén"),
        ]
        for nombre, direccion, comuna in datos:
            Condominio.objects.get_or_create(
                nombre=nombre,
                defaults={"direccion": direccion, "comuna_ciudad": comuna, "activo": True},
            )
        self.stdout.write(f"  · Condominios: {Condominio.objects.count()}")
        return list(Condominio.objects.filter(activo=True).order_by("nombre"))

    def _crear_flota(self):
        marcas = {}
        for nombre in ["DJI", "Autel", "Parrot", "Skydio"]:
            marca, _ = MarcaDron.objects.get_or_create(
                nombre=nombre, defaults={"activa": True}
            )
            marcas[nombre] = marca

        datos_drones = [
            ("DRON-01", "DJI", "Mavic 3 Enterprise", Dron.Estado.OPERATIVO),
            ("DRON-02", "DJI", "Mavic 3T", Dron.Estado.OPERATIVO),
            ("DRON-03", "Autel", "EVO Max 4T", Dron.Estado.OPERATIVO),
            ("DRON-04", "Autel", "EVO Lite+", Dron.Estado.OPERATIVO),
            ("DRON-05", "Parrot", "Anafi USA", Dron.Estado.OPERATIVO),
            ("DRON-06", "Parrot", "Anafi Thermal", Dron.Estado.MANTENIMIENTO),
            ("DRON-07", "Skydio", "X10", Dron.Estado.OPERATIVO),
            ("DRON-08", "DJI", "Matrice 30T", Dron.Estado.INACTIVO),
        ]
        for codigo, marca, modelo, estado in datos_drones:
            Dron.objects.get_or_create(
                codigo_identificador=codigo,
                defaults={
                    "marca": marcas[marca],
                    "modelo": modelo,
                    "estado": estado,
                },
            )
        self.stdout.write(f"  · Marcas: {MarcaDron.objects.count()} | Drones: {Dron.objects.count()}")
        return marcas, list(Dron.objects.filter(estado=Dron.Estado.OPERATIVO))

    def _crear_turnos(self, usuarios, condominios, drones, generar_videos=True):
        if Turno.objects.exists():
            self.stdout.write(
                self.style.WARNING(
                    "  · Ya existen turnos; no se generan datos históricos nuevos. "
                    "Usa --limpiar para regenerarlos."
                )
            )
            return

        operadores = [
            usuarios["pepito.rivas"],
            usuarios["camila.soto"],
            usuarios["diego.fuentes"],
        ]
        programa = [
            (1, 0, 0, 7, 8, 0),
            (2, 1, 1, 5, 9, 0),
            (3, 2, 2, 6, 14, 0),
            (5, 0, 1, 8, 8, 0),
            (6, 3, 0, 4, 18, 0),
            (8, 1, 2, 7, 9, 0),
            (9, 2, 0, 5, 15, 0),
            (11, 0, 2, 6, 8, 0),
            (13, 3, 1, 8, 20, 0),
            (14, 1, 0, 5, 9, 0),
            (16, 2, 2, 4, 8, 0),
            (18, 0, 0, 7, 14, 0),
            (20, 3, 2, 6, 9, 0),
            (22, 1, 1, 5, 18, 0),
            (24, 0, 2, 8, 8, 0),
            (27, 2, 0, 4, 9, 0),
            (29, 3, 1, 7, 8, 0),
            (32, 1, 0, 6, 14, 0),
            (35, 0, 1, 5, 9, 0),
            (38, 2, 2, 7, 8, 0),
            (41, 3, 0, 4, 18, 0),
            (44, 0, 2, 6, 9, 0),
            (47, 1, 1, 8, 8, 0),
            (50, 2, 0, 5, 14, 0),
            (54, 3, 2, 7, 9, 0),
            (58, 0, 1, 6, 8, 0),
            (63, 1, 0, 5, 9, 0),
            (67, 2, 2, 8, 14, 0),
            (72, 0, 0, 6, 8, 0),
            (78, 3, 1, 5, 9, 0),
        ]
        observaciones = [
            "Ronda perimetral sin novedades.",
            "Se observa portón de acceso abierto; se informa a conserjería.",
            "Vehículo no identificado estacionado en zona restringida.",
            "Iluminación del sector norte con falla intermitente.",
            "Ronda completa. Sin incidencias relevantes.",
            "Se detecta movimiento en área de piscina; se verificó sin riesgo.",
            "Viento moderado durante el vuelo, sin afectar la operación.",
        ]
        hoy = timezone.localdate()
        tz = timezone.get_current_timezone()
        total_turnos = 0
        total_vuelos = 0
        video_flights = []
        viejo_marcado = False

        for indice, (dias, condo_idx, op_idx, n_vuelos, hora, minuto) in enumerate(
            programa
        ):
            fecha = hoy - timedelta(days=dias)
            condominio = condominios[condo_idx % len(condominios)]
            operador = operadores[op_idx % len(operadores)]
            inicio = timezone.make_aware(
                datetime.combine(fecha, time(hora, minuto)), tz
            )
            fin_turno = inicio + timedelta(minutes=25 * n_vuelos + 15)

            turno = Turno.objects.create(
                operador=operador,
                condominio=condominio,
                fecha_inicio=inicio,
                fecha_fin=fin_turno,
                cerrado=True,
                observaciones_generales=(
                    "Turno de vigilancia programada. "
                    f"{'Jornada completa.' if n_vuelos >= 6 else 'Operación parcial.'}"
                ),
            )
            total_turnos += 1

            for j in range(n_vuelos):
                hora_inicio = inicio + timedelta(minutes=25 * j)
                hora_fin = hora_inicio + timedelta(minutes=18 + (j % 3))
                dron = drones[(indice + j) % len(drones)]
                vuelo = Vuelo.objects.create(
                    turno=turno,
                    dron=dron,
                    hora_inicio=hora_inicio,
                    hora_fin=hora_fin,
                    observaciones=observaciones[(indice + j) % len(observaciones)]
                    if j % 2 == 0
                    else "",
                )
                total_vuelos += 1
                if indice < 6 and j < max(1, n_vuelos - 2):
                    video_flights.append(vuelo)
                elif dias > 60 and not viejo_marcado:
                    vuelo.video_r2_key = r2_storage.key_para_vuelo(vuelo)
                    vuelo.video_peso_mb = 185.40
                    vuelo.video_subido_en = fin_turno + timedelta(hours=1)
                    vuelo.save(
                        update_fields=[
                            "video_r2_key",
                            "video_peso_mb",
                            "video_subido_en",
                        ]
                    )

            if dias > 60:
                viejo_marcado = True

        self.stdout.write(
            f"  · Turnos: {total_turnos} | Vuelos: {total_vuelos}"
        )

        if generar_videos and video_flights:
            self._generar_videos_demo(video_flights)

    # ------------------------------------------------------------------
    def _generar_videos_demo(self, vuelos):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.stdout.write(
                self.style.WARNING(
                    "  · ffmpeg no está instalado; los vuelos de demo quedarán sin video."
                )
            )
            return

        temp_dir = Path(tempfile.mkdtemp(prefix="aerovigia_demo_"))
        muestra = temp_dir / "muestra.mp4"
        comando = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=24:duration=8",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-crf",
            "30",
            "-movflags",
            "+faststart",
            str(muestra),
        ]
        try:
            subprocess.run(comando, check=True, capture_output=True, timeout=120)
        except (subprocess.SubprocessError, OSError):
            self.stdout.write(
                self.style.WARNING(
                    "  · No se pudo generar el video de demostración (se omite)."
                )
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return

        peso_mb = round(muestra.stat().st_size / (1024 * 1024), 2)
        ahora = timezone.now()
        for vuelo in vuelos:
            key = r2_storage.key_para_vuelo(vuelo)
            destino = r2_storage.ruta_local(key)
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(muestra, destino)
            vuelo.video_r2_key = key
            vuelo.video_peso_mb = peso_mb
            # Escalonado para que todos sigan vigentes (< 60 días).
            vuelo.video_subido_en = ahora - timedelta(days=1, hours=vuelo.id % 12)
            vuelo.save(
                update_fields=["video_r2_key", "video_peso_mb", "video_subido_en"]
            )

        shutil.rmtree(temp_dir, ignore_errors=True)
        self.stdout.write(
            f"  · {len(vuelos)} video(s) de demostración generados ({peso_mb} MB c/u)."
        )
