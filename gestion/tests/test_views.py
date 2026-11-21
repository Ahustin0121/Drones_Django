from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from gestion.models import Condominio, Dron, MarcaDron, Turno, Usuario, Vuelo


class BaseViewTests(TestCase):
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
        cls.otro_operador = Usuario.objects.create_user(
            username="otro_test",
            password="clave-segura-123",
            first_name="Camila",
            last_name="Soto",
            rol=Usuario.Rol.OPERADOR,
        )
        cls.condominio = Condominio.objects.create(nombre="Condominio Test")
        cls.condominio_inactivo = Condominio.objects.create(
            nombre="Condominio Inactivo", activo=False
        )
        cls.marca = MarcaDron.objects.create(nombre="DJI")
        cls.dron = Dron.objects.create(
            codigo_identificador="DRON-01", marca=cls.marca, modelo="Mavic 3"
        )
        cls.dron_mantenimiento = Dron.objects.create(
            codigo_identificador="DRON-02",
            marca=cls.marca,
            estado=Dron.Estado.MANTENIMIENTO,
        )
        cls.turno_ajeno = Turno.objects.create(
            operador=cls.otro_operador,
            condominio=cls.condominio,
            cerrado=True,
            fecha_fin=timezone.now(),
        )


class AutenticacionYAccesoTests(BaseViewTests):
    def test_raiz_redirige_a_login_sin_autenticacion(self):
        respuesta = self.client.get(reverse("gestion:inicio"))
        self.assertRedirects(respuesta, reverse("gestion:login"))

    def test_login_admin_redirige_al_panel(self):
        respuesta = self.client.post(
            reverse("gestion:login"),
            {"username": "admin_test", "password": "clave-segura-123"},
        )
        self.assertRedirects(respuesta, reverse("gestion:admin_dashboard"))

    def test_login_operador_redirige_a_su_panel(self):
        respuesta = self.client.post(
            reverse("gestion:login"),
            {"username": "operador_test", "password": "clave-segura-123"},
        )
        self.assertRedirects(respuesta, reverse("gestion:operador_dashboard"))

    def test_operador_no_accede_al_panel_admin(self):
        self.client.login(username="operador_test", password="clave-segura-123")
        respuesta = self.client.get(reverse("gestion:admin_dashboard"))
        self.assertEqual(respuesta.status_code, 403)

    def test_operador_no_accede_a_bitacora(self):
        self.client.login(username="operador_test", password="clave-segura-123")
        respuesta = self.client.get(reverse("gestion:bitacora"))
        self.assertEqual(respuesta.status_code, 403)

    def test_admin_es_redirigido_desde_panel_operador(self):
        self.client.login(username="admin_test", password="clave-segura-123")
        respuesta = self.client.get(reverse("gestion:operador_dashboard"))
        self.assertRedirects(respuesta, reverse("gestion:admin_dashboard"))

    def test_operador_no_ve_turno_ajeno(self):
        self.client.login(username="operador_test", password="clave-segura-123")
        respuesta = self.client.get(
            reverse("gestion:turno_detalle", args=[self.turno_ajeno.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_admin_ve_turno_de_cualquier_operador(self):
        self.client.login(username="admin_test", password="clave-segura-123")
        respuesta = self.client.get(
            reverse("gestion:turno_detalle", args=[self.turno_ajeno.pk])
        )
        self.assertEqual(respuesta.status_code, 200)


class FlujoOperadorTests(BaseViewTests):
    def setUp(self):
        self.client.login(username="operador_test", password="clave-segura-123")

    def test_flujo_completo_turno_vuelos_y_cierre(self):
        respuesta = self.client.post(
            reverse("gestion:abrir_turno"),
            {"condominio": self.condominio.pk, "observaciones_generales": "Ronda"},
        )
        self.assertRedirects(respuesta, reverse("gestion:operador_dashboard"))
        turno = Turno.objects.get(operador=self.operador, cerrado=False)

        respuesta = self.client.post(
            reverse("gestion:iniciar_vuelo"),
            {"dron": self.dron.pk, "observaciones": "Despegue"},
        )
        self.assertRedirects(respuesta, reverse("gestion:operador_dashboard"))
        vuelo = turno.vuelos.get()
        self.assertIsNone(vuelo.hora_fin)

        respuesta = self.client.post(
            reverse("gestion:finalizar_vuelo", args=[vuelo.pk]),
            {"observaciones": "Sin novedades"},
        )
        self.assertRedirects(respuesta, reverse("gestion:operador_dashboard"))
        vuelo.refresh_from_db()
        self.assertIsNotNone(vuelo.hora_fin)
        self.assertIn("Sin novedades", vuelo.observaciones)

        respuesta = self.client.post(
            reverse("gestion:cerrar_turno", args=[turno.pk]),
            {"observaciones_generales": "Cierre"},
        )
        self.assertRedirects(
            respuesta, reverse("gestion:subir_videos", args=[turno.pk])
        )
        turno.refresh_from_db()
        self.assertTrue(turno.cerrado)
        self.assertIsNotNone(turno.fecha_fin)

        respuesta = self.client.get(reverse("gestion:subir_videos", args=[turno.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Videos de la jornada")

    def test_no_puede_abrir_dos_turnos(self):
        Turno.objects.create(operador=self.operador, condominio=self.condominio)
        respuesta = self.client.post(
            reverse("gestion:abrir_turno"), {"condominio": self.condominio.pk}
        )
        self.assertRedirects(respuesta, reverse("gestion:operador_dashboard"))
        self.assertEqual(
            Turno.objects.filter(operador=self.operador, cerrado=False).count(), 1
        )

    def test_no_puede_iniciar_vuelo_sin_turno(self):
        respuesta = self.client.post(
            reverse("gestion:iniciar_vuelo"), {"dron": self.dron.pk}
        )
        self.assertRedirects(respuesta, reverse("gestion:operador_dashboard"))
        self.assertEqual(Vuelo.objects.count(), 0)

    def test_no_puede_usar_dron_en_mantenimiento(self):
        Turno.objects.create(operador=self.operador, condominio=self.condominio)
        self.client.post(
            reverse("gestion:iniciar_vuelo"),
            {"dron": self.dron_mantenimiento.pk},
        )
        self.assertEqual(Vuelo.objects.count(), 0)

    def test_no_puede_cerrar_turno_con_vuelo_abierto(self):
        turno = Turno.objects.create(
            operador=self.operador, condominio=self.condominio
        )
        turno.vuelos.create(dron=self.dron, hora_inicio=timezone.now())
        self.client.post(reverse("gestion:cerrar_turno", args=[turno.pk]))
        turno.refresh_from_db()
        self.assertFalse(turno.cerrado)

    def test_no_puede_cerrar_turno_ajeno(self):
        respuesta = self.client.post(
            reverse("gestion:cerrar_turno", args=[self.turno_ajeno.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_historial_solo_muestra_turnos_propios(self):
        Turno.objects.create(
            operador=self.operador,
            condominio=self.condominio,
            cerrado=True,
            fecha_fin=timezone.now(),
        )
        respuesta = self.client.get(reverse("gestion:historial"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.condominio.nombre)
        self.assertNotContains(respuesta, "Camila Soto")


class PanelAdminTests(BaseViewTests):
    def setUp(self):
        self.client.login(username="admin_test", password="clave-segura-123")

    def test_panel_admin_carga(self):
        respuesta = self.client.get(reverse("gestion:admin_dashboard"))
        self.assertEqual(respuesta.status_code, 200)

    def test_bitacora_muestra_agrupacion_por_operador_y_marca(self):
        turno = Turno.objects.create(
            operador=self.otro_operador,
            condominio=self.condominio,
            fecha_inicio=timezone.now() - timedelta(hours=2),
            fecha_fin=timezone.now(),
            cerrado=True,
        )
        turno.vuelos.create(
            dron=self.dron,
            hora_inicio=timezone.now() - timedelta(hours=1),
            hora_fin=timezone.now() - timedelta(minutes=40),
        )
        respuesta = self.client.get(
            reverse("gestion:bitacora"),
            {
                "condominio": self.condominio.pk,
                "mes": timezone.localdate().month,
                "anio": timezone.localdate().year,
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Camila Soto")
        self.assertContains(respuesta, "DJI")
        self.assertContains(respuesta, "Días operados")

    def test_crear_condominio(self):
        respuesta = self.client.post(
            reverse("gestion:condominio_crear"),
            {
                "nombre": "Nuevo Condominio",
                "direccion": "Calle 123",
                "comuna_ciudad": "Providencia",
                "activo": "on",
            },
        )
        self.assertRedirects(respuesta, reverse("gestion:condominios"))
        self.assertTrue(Condominio.objects.filter(nombre="Nuevo Condominio").exists())

    def test_toggle_condominio(self):
        self.client.post(
            reverse("gestion:condominio_toggle", args=[self.condominio.pk])
        )
        self.condominio.refresh_from_db()
        self.assertFalse(self.condominio.activo)

    def test_cambiar_estado_dron(self):
        self.client.post(
            reverse("gestion:dron_cambiar_estado", args=[self.dron.pk]),
            {"estado": Dron.Estado.MANTENIMIENTO},
        )
        self.dron.refresh_from_db()
        self.assertEqual(self.dron.estado, Dron.Estado.MANTENIMIENTO)

    def test_crear_usuario_operador(self):
        respuesta = self.client.post(
            reverse("gestion:usuario_crear"),
            {
                "username": "nuevo.operador",
                "first_name": "Nuevo",
                "last_name": "Operador",
                "email": "nuevo@example.com",
                "rol": Usuario.Rol.OPERADOR,
                "rut_o_dni": "12345678-9",
                "telefono": "+56911111111",
                "is_active": "on",
                "password1": "ClaveMuySegura987!",
                "password2": "ClaveMuySegura987!",
            },
        )
        self.assertRedirects(respuesta, reverse("gestion:usuarios"))
        self.assertTrue(Usuario.objects.filter(username="nuevo.operador").exists())

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.client.post(reverse("gestion:usuario_toggle", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_restringir_password(self):
        respuesta = self.client.post(
            reverse("gestion:usuario_password", args=[self.operador.pk]),
            {"password1": "NuevaClaveSegura987!", "password2": "NuevaClaveSegura987!"},
        )
        self.assertRedirects(respuesta, reverse("gestion:usuarios"))
        self.operador.refresh_from_db()
        self.assertTrue(self.operador.check_password("NuevaClaveSegura987!"))
