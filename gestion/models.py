from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        OPERADOR = "OPERADOR", "Manejador de Dron"

    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.OPERADOR,
        verbose_name="Rol en el sistema",
    )
    rut_o_dni = models.CharField(max_length=20, blank=True, verbose_name="Identificación")
    telefono = models.CharField(max_length=30, blank=True)

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def es_admin(self):
        return self.rol == self.Rol.ADMIN or self.is_superuser

    def nombre_completo(self):
        return self.get_full_name() or self.username

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_rol_display()})"


class Condominio(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    direccion = models.CharField(max_length=255, blank=True)
    comuna_ciudad = models.CharField(max_length=100, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Condominio"
        verbose_name_plural = "Condominios"

    def __str__(self):
        return self.nombre


class MarcaDron(models.Model):
    """Catálogo administrable por CRUD (Ej: DJI, Autel, Parrot, etc.)."""

    nombre = models.CharField(max_length=100, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Marca de Dron"
        verbose_name_plural = "Marcas de Drones"

    def __str__(self):
        return self.nombre


class Dron(models.Model):
    class Estado(models.TextChoices):
        OPERATIVO = "OPERATIVO", "Operativo"
        MANTENIMIENTO = "MANTENIMIENTO", "En Mantenimiento"
        INACTIVO = "INACTIVO", "Inactivo / Baja"

    codigo_identificador = models.CharField(
        max_length=100,
        unique=True,
        help_text="Código interno o número de serie del dron (Ej: DRON-01)",
    )
    marca = models.ForeignKey(
        MarcaDron,
        on_delete=models.PROTECT,
        related_name="drones",
    )
    modelo = models.CharField(
        max_length=100,
        blank=True,
        help_text="Ej: Mavic 3 Enterprise, Mini 4 Pro",
    )
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.OPERATIVO
    )
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["marca__nombre", "codigo_identificador"]
        verbose_name = "Dron"
        verbose_name_plural = "Drones"

    @property
    def disponible(self):
        return self.estado == self.Estado.OPERATIVO and self.marca.activa

    def __str__(self):
        return f"{self.codigo_identificador} - {self.marca.nombre} {self.modelo}".strip()


class Turno(models.Model):
    operador = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="turnos",
        verbose_name="Operador",
    )
    condominio = models.ForeignKey(
        Condominio,
        on_delete=models.PROTECT,
        related_name="turnos",
    )
    fecha_inicio = models.DateTimeField(default=timezone.now)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    cerrado = models.BooleanField(default=False)
    observaciones_generales = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha_inicio"]
        verbose_name = "Turno"
        verbose_name_plural = "Turnos"
        indexes = [
            models.Index(fields=["condominio", "fecha_inicio"]),
            models.Index(fields=["operador", "fecha_inicio"]),
        ]

    @property
    def duracion_horas(self):
        fin = self.fecha_fin or timezone.now()
        return round((fin - self.fecha_inicio).total_seconds() / 3600, 1)

    @property
    def vuelos_completados(self):
        return self.vuelos.filter(hora_fin__isnull=False).count()

    @property
    def tiene_vuelo_abierto(self):
        return self.vuelos.filter(hora_fin__isnull=True).exists()

    @property
    def vuelos_sin_video(self):
        return self.vuelos.filter(hora_fin__isnull=False).filter(
            models.Q(video_r2_key="") | models.Q(video_subido_en__isnull=True)
        ).count()

    def __str__(self):
        return (
            f"Turno #{self.id} | {self.operador} | {self.condominio} "
            f"({self.fecha_inicio.strftime('%Y-%m-%d')})"
        )


class Vuelo(models.Model):
    turno = models.ForeignKey(
        Turno,
        on_delete=models.CASCADE,
        related_name="vuelos",
    )
    dron = models.ForeignKey(
        Dron,
        on_delete=models.PROTECT,
        related_name="vuelos",
    )
    hora_inicio = models.DateTimeField()
    hora_fin = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(
        blank=True,
        help_text="Novedades detectadas durante la ronda",
    )

    # Metadatos del archivo en Cloudflare R2 (nunca el binario).
    video_r2_key = models.CharField(
        max_length=500,
        blank=True,
        help_text="Ruta/Key del objeto en Cloudflare R2 "
        "(Ej: condominios/1/2026/11/turno_45/vuelo_90.mp4)",
    )
    video_peso_mb = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    video_subido_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["hora_inicio"]
        verbose_name = "Vuelo"
        verbose_name_plural = "Vuelos"
        indexes = [
            models.Index(fields=["hora_inicio"]),
            models.Index(fields=["dron", "hora_inicio"]),
        ]

    @property
    def duracion_minutos(self):
        if self.hora_inicio and self.hora_fin:
            delta = self.hora_fin - self.hora_inicio
            return round(delta.total_seconds() / 60, 1)
        return None

    @property
    def en_curso(self):
        return self.hora_fin is None

    @property
    def video_expirado(self):
        """El objeto ya fue eliminado por la regla de ciclo de vida de R2."""
        if not self.video_subido_en:
            return False
        limite = self.video_subido_en + timedelta(days=60)
        return timezone.now() > limite

    @property
    def video_disponible(self):
        """True si el video se subió y sigue dentro de la ventana de 60 días."""
        if not self.video_r2_key or not self.video_subido_en:
            return False
        return not self.video_expirado

    def __str__(self):
        return (
            f"Vuelo #{self.id} - Dron {self.dron.codigo_identificador} "
            f"({self.hora_inicio.strftime('%H:%M')})"
        )
