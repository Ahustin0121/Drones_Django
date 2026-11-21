from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def _verificar_autenticacion(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required(view_func):
    """Permite el acceso únicamente a administradores autenticados."""

    @_verificar_autenticacion
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.es_admin():
            raise PermissionDenied("Esta sección es exclusiva de administradores.")
        return view_func(request, *args, **kwargs)

    return wrapper


def operador_required(view_func):
    """Permite el acceso a operadores; redirige a los admins a su panel."""

    @_verificar_autenticacion
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.es_admin():
            messages.info(
                request,
                "Tu cuenta es de administrador. Usa el panel administrativo.",
            )
            return redirect("gestion:admin_dashboard")
        if request.user.rol != "OPERADOR":
            raise PermissionDenied("Se requiere el rol de operador.")
        return view_func(request, *args, **kwargs)

    return wrapper
