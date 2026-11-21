from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect

from gestion.forms import EstiloFormMixin


class LoginForm(EstiloFormMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": "Tu nombre de usuario",
                "autofocus": True,
                "autocomplete": "username",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "placeholder": "Tu contraseña",
                "autocomplete": "current-password",
            }
        )


def inicio(request):
    """Redirección inteligente según el rol del usuario autenticado."""
    if not request.user.is_authenticated:
        return redirect("gestion:login")
    if request.user.es_admin():
        return redirect("gestion:admin_dashboard")
    return redirect("gestion:operador_dashboard")


class IniciarSesionView(LoginView):
    template_name = "auth/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        nombre = self.request.user.get_full_name() or self.request.user.username
        messages.success(self.request, f"Bienvenido de vuelta, {nombre}.")
        return respuesta

    def get_success_url(self):
        if self.request.user.es_admin():
            return "/admin-panel/"
        return "/operador/"


def health(request):
    """Endpoint liviano para monitoreo en Render."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        estado = "ok"
        codigo = 200
    except Exception:  # pragma: no cover - solo monitoreo
        estado = "error"
        codigo = 503
    return JsonResponse({"status": estado, "service": "aerovigia"}, status=codigo)
