from django.contrib.auth.views import LogoutView
from django.urls import path

from gestion.views import (
    admin_crud_views,
    api_views,
    auth_views,
    bitacora_views,
    operador_views,
)

app_name = "gestion"

urlpatterns = [
    path("", auth_views.inicio, name="inicio"),
    path("login/", auth_views.IniciarSesionView.as_view(), name="login"),
    path(
        "logout/",
        LogoutView.as_view(next_page="gestion:login"),
        name="logout",
    ),
    path("health/", auth_views.health, name="health"),
    # Operador
    path("operador/", operador_views.dashboard, name="operador_dashboard"),
    path("operador/turnos/abrir/", operador_views.abrir_turno, name="abrir_turno"),
    path(
        "operador/turnos/<int:pk>/cerrar/",
        operador_views.cerrar_turno,
        name="cerrar_turno",
    ),
    path(
        "operador/vuelos/iniciar/",
        operador_views.iniciar_vuelo,
        name="iniciar_vuelo",
    ),
    path(
        "operador/vuelos/<int:pk>/finalizar/",
        operador_views.finalizar_vuelo,
        name="finalizar_vuelo",
    ),
    path(
        "operador/turnos/<int:pk>/subir-videos/",
        operador_views.subir_videos,
        name="subir_videos",
    ),
    path("operador/historial/", operador_views.historial, name="historial"),
    # Detalle y reproducción compartidos
    path("turnos/<int:pk>/", operador_views.turno_detalle, name="turno_detalle"),
    path("vuelos/<int:pk>/video/", operador_views.video_vuelo, name="video_vuelo"),
    path("api/vuelos/<int:pk>/video-url/", operador_views.video_url_api, name="video_url_api"),
    # APIs de subida
    path(
        "api/turnos/<int:pk>/presigned-uploads/",
        api_views.presigned_uploads,
        name="api_presigned_uploads",
    ),
    path(
        "api/vuelos/<int:pk>/subida-local/",
        api_views.subida_local,
        name="api_subida_local",
    ),
    path(
        "api/vuelos/<int:pk>/confirmar-video/",
        api_views.confirmar_video,
        name="api_confirmar_video",
    ),
    path("api/vuelos/<int:pk>/video/", api_views.video_url, name="api_video_url"),
    # Administración
    path("admin-panel/", admin_crud_views.dashboard, name="admin_dashboard"),
    path("admin-panel/bitacora/", bitacora_views.bitacora, name="bitacora"),
    path("admin-panel/condominios/", admin_crud_views.condominios, name="condominios"),
    path(
        "admin-panel/condominios/nuevo/",
        admin_crud_views.condominio_crear,
        name="condominio_crear",
    ),
    path(
        "admin-panel/condominios/<int:pk>/editar/",
        admin_crud_views.condominio_editar,
        name="condominio_editar",
    ),
    path(
        "admin-panel/condominios/<int:pk>/toggle/",
        admin_crud_views.condominio_toggle,
        name="condominio_toggle",
    ),
    path("admin-panel/marcas/", admin_crud_views.marcas, name="marcas"),
    path("admin-panel/marcas/nueva/", admin_crud_views.marca_crear, name="marca_crear"),
    path(
        "admin-panel/marcas/<int:pk>/editar/",
        admin_crud_views.marca_editar,
        name="marca_editar",
    ),
    path(
        "admin-panel/marcas/<int:pk>/toggle/",
        admin_crud_views.marca_toggle,
        name="marca_toggle",
    ),
    path("admin-panel/drones/", admin_crud_views.drones, name="drones"),
    path("admin-panel/drones/nuevo/", admin_crud_views.dron_crear, name="dron_crear"),
    path(
        "admin-panel/drones/<int:pk>/editar/",
        admin_crud_views.dron_editar,
        name="dron_editar",
    ),
    path(
        "admin-panel/drones/<int:pk>/estado/",
        admin_crud_views.dron_cambiar_estado,
        name="dron_cambiar_estado",
    ),
    path("admin-panel/usuarios/", admin_crud_views.usuarios, name="usuarios"),
    path(
        "admin-panel/usuarios/nuevo/",
        admin_crud_views.usuario_crear,
        name="usuario_crear",
    ),
    path(
        "admin-panel/usuarios/<int:pk>/editar/",
        admin_crud_views.usuario_editar,
        name="usuario_editar",
    ),
    path(
        "admin-panel/usuarios/<int:pk>/toggle/",
        admin_crud_views.usuario_toggle,
        name="usuario_toggle",
    ),
    path(
        "admin-panel/usuarios/<int:pk>/password/",
        admin_crud_views.usuario_password,
        name="usuario_password",
    ),
]
