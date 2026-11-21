from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from gestion.models import Condominio, Dron, MarcaDron, Turno, Usuario, Vuelo


class ModelosBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user(
            username="admin_test",
            password="clave-segura-123",
            rol=Usuario.Rol.ADMIN,
            is_superuser=True,
            is_staff=True,
        )
        cls.operador = Usuario.objects.create_user(
            username="operador_test",
            password="clave-segura-123",
            first_name="Pepito",
            last_name="Rivas",
            rol=Usuario.Rol.OPERADOR,
        )
        cls.condominio = Condominio.objects.create(
            nombre="Condominio Test", comuna_ciudad="Santiago"
        )
        cls.marca = MarcaDron.objects.create(nombre="DJI")
        cls.dron = Dron.objects.create(
            codigo_identificador="DRON-TEST",
            marca=cls.marca,
            modelo="Mavic 3",
        )


class VueloModelTests(ModelosBaseTestCase):
    def setUp(self):
        self.turno = Turno.objects.create(
            operador=self.operador, condominio=self.condominio
        )

    def test_duracion_minutos(self):
        inicio = timezone.now()
        vuelo = Vuelo.objects.create(
            turno=self.turno,
            dron=self.dron,
            hora_inicio=inicio,
            hora_fin=inicio + timedelta(minutes=20, seconds=30),
        )
        self.assertEqual(vuelo.duracion_minutos, 20.5)

    def test_video_disponible_dentro_de_60_dias(self):
        vuelo = Vuelo.objects.create(
            turno=self.turno,
            dron=self.dron,
            hora_inicio=timezone.now() - timedelta(hours=1),
            hora_fin=timezone.now(),
            video_r2_key="condominios/1/vuelo.mp4",
            video_subido_en=timezone.now() - timedelta(days=59),
        )
        self.assertTrue(vuelo.video_disponible)
        self.assertFalse(vuelo.video_expirado)

    def test_video_expirado_despues_de_60_dias(self):
        vuelo = Vuelo.objects.create(
            turno=self.turno,
            dron=self.dron,
            hora_inicio=timezone.now() - timedelta(days=62),
            hora_fin=timezone.now() - timedelta(days=62, hours=-1),
            video_r2_key="condominios/1/vuelo.mp4",
            video_subido_en=timezone.now() - timedelta(days=61),
        )
        self.assertFalse(vuelo.video_disponible)
        self.assertTrue(vuelo.video_expirado)

    def test_video_sin_metadatos_no_esta_disponible(self):
        vuelo = Vuelo.objects.create(
            turno=self.turno,
            dron=self.dron,
            hora_inicio=timezone.now(),
        )
        self.assertFalse(vuelo.video_disponible)
        self.assertFalse(vuelo.video_expirado)
        self.assertTrue(vuelo.en_curso)

    def test_turno_propiedades(self):
        self.turno.vuelos.create(
            dron=self.dron,
            hora_inicio=timezone.now() - timedelta(minutes=40),
            hora_fin=timezone.now() - timedelta(minutes=20),
        )
        self.turno.vuelos.create(dron=self.dron, hora_inicio=timezone.now())
        self.assertEqual(self.turno.vuelos_completados, 1)
        self.assertTrue(self.turno.tiene_vuelo_abierto)
        self.assertEqual(self.turno.vuelos_sin_video, 1)

    def test_disponibilidad_dron(self):
        self.assertTrue(self.dron.disponible)
        self.marca.activa = False
        self.marca.save(update_fields=["activa"])
        self.assertFalse(self.dron.disponible)


class UsuarioModelTests(ModelosBaseTestCase):
    def test_admin_identificado_por_rol_o_superusuario(self):
        self.assertTrue(self.admin.es_admin())
        self.assertFalse(self.operador.es_admin())

    def test_nombre_completo(self):
        self.assertEqual(self.operador.nombre_completo(), "Pepito Rivas")
