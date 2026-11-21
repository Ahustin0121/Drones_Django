from django.conf import settings
from django.utils import timezone


def app_context(request):
    """Datos globales disponibles en todas las plantillas."""
    contexto = {
        "APP_NAME": "AeroVigía",
        "APP_DEBUG": settings.DEBUG,
        "APP_HOY": timezone.localdate(),
        "R2_CONFIGURADO": settings.R2_ACCOUNT_ID
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.R2_BUCKET_NAME,
    }
    if request.user.is_authenticated and getattr(request.user, "rol", None) == "OPERADOR":
        contexto["turno_activo_global"] = (
            request.user.turnos.filter(cerrado=False).order_by("-fecha_inicio").first()
        )
    return contexto
