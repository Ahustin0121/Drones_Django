import json
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from gestion.models import Condominio, Dron, MarcaDron, Turno, Usuario, Vuelo
from gestion.services import r2_storage

MEDIA_DE_PRUEBA = tempfile.mkdtemp(prefix="aerovigia_test_media_")


@override_settings(
    MEDIA_ROOT=MEDIA_DE_PRUEBA,
    R2_ACCOUNT_ID="",
    R2_ACCESS_KEY_ID="",
    R2_SECRET_ACCESS_KEY="",
    R2_BUCKET_NAME="",
)
class VideosApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operador = Usuario.objects.create_user(
            username="operador_test",
            password="clave-segura-123",
            rol=Usuario.Rol.OPERADOR,
        )
        cls.otro_operador = Usuario.objects.create_user(
            username="otro_test",
            password="clave-segura-123",
            rol=Usuario.Rol.OPERADOR,
        )
        cls.condominio = Condominio.objects.create(nombre="Condominio Test")
        cls.marca = MarcaDron.objects.create(nombre="DJI")
        cls.dron = Dron.objects.create(
            codigo_identificador="DRON-01", marca=cls.marca
        )
        cls.turno = Turno.objects.create(
            operador=cls.operador,
            condominio=cls.condominio,
            cerrado=True,
            fecha_inicio=timezone.now() - timedelta(hours=2),
            fecha_fin=timezone.now(),
        )
        cls.vuelo = Vuelo.objects.create(
            turno=cls.turno,
            dron=cls.dron,
            hora_inicio=timezone.now() - timedelta(hours=1),
            hora_fin=timezone.now() - timedelta(minutes=40),
        )

    def setUp(self):
        self.client.login(username="operador_test", password="clave-segura-123")

    def test_presigned_local_y_subida_completa(self):
        respuesta = self.client.post(
            reverse("gestion:api_presigned_uploads", args=[self.turno.pk]),
            data=json.dumps({"vuelo_ids": [self.vuelo.pk]}),
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos["modo"], "local")
        info = datos["vuelos"][0]
        self.assertEqual(info["method"], "POST")

        archivo = SimpleUploadedFile(
            "video.mp4", b"\x00\x00\x00\x18ftypmp42" + b"0" * 512, content_type="video/mp4"
        )
        respuesta = self.client.post(info["upload_url"], {"file": archivo})
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.client.post(
            info["confirm_url"],
            data=json.dumps({"peso_mb": 1}),
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["ok"])

        self.vuelo.refresh_from_db()
        self.assertTrue(self.vuelo.video_disponible)
        self.assertIsNotNone(self.vuelo.video_r2_key)
        self.assertIsNotNone(self.vuelo.video_subido_en)

        respuesta = self.client.get(
            reverse("gestion:video_vuelo", args=[self.vuelo.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "video/mp4")

        # Limpieza del archivo local.
        ruta = r2_storage.ruta_local(self.vuelo.video_r2_key)
        if ruta.exists():
            ruta.unlink()

    def test_confirmar_sin_archivo_falla(self):
        respuesta = self.client.post(
            reverse("gestion:api_confirmar_video", args=[self.vuelo.pk]),
            data=json.dumps({"peso_mb": 120}),
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 409)
        self.vuelo.refresh_from_db()
        self.assertIsNone(self.vuelo.video_subido_en)

    def test_otro_operador_no_puede_solicitar_subida(self):
        self.client.logout()
        self.client.login(username="otro_test", password="clave-segura-123")
        respuesta = self.client.post(
            reverse("gestion:api_presigned_uploads", args=[self.turno.pk]),
            data=json.dumps({"vuelo_ids": [self.vuelo.pk]}),
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_no_se_permite_subir_a_turno_abierto(self):
        self.turno.cerrado = False
        self.turno.fecha_fin = None
        self.turno.save(update_fields=["cerrado", "fecha_fin"])
        respuesta = self.client.post(
            reverse("gestion:api_presigned_uploads", args=[self.turno.pk]),
            data=json.dumps({"vuelo_ids": [self.vuelo.pk]}),
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 409)

    def test_video_expirado_no_se_reproduce(self):
        self.vuelo.video_r2_key = "condominios/1/vuelo.mp4"
        self.vuelo.video_subido_en = timezone.now() - timedelta(days=61)
        self.vuelo.save(update_fields=["video_r2_key", "video_subido_en"])
        respuesta = self.client.get(
            reverse("gestion:video_vuelo", args=[self.vuelo.pk])
        )
        self.assertEqual(respuesta.status_code, 410)

    def test_video_url_api(self):
        self.vuelo.video_r2_key = "condominios/1/vuelo.mp4"
        self.vuelo.video_subido_en = timezone.now()
        self.vuelo.save(update_fields=["video_r2_key", "video_subido_en"])
        respuesta = self.client.get(
            reverse("gestion:api_video_url", args=[self.vuelo.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["url"].endswith(f"/vuelos/{self.vuelo.pk}/video/"))
