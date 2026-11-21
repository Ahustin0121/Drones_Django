from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from gestion.decorators import admin_required
from gestion.forms import (
    CondominioForm,
    DronForm,
    MarcaDronForm,
    RestablecerPasswordForm,
    UsuarioCrearForm,
    UsuarioEditarForm,
)
from gestion.models import Condominio, Dron, MarcaDron, Turno, Usuario, Vuelo


def _hace_meses(anio, mes, cantidad):
    total = anio * 12 + (mes - 1) - cantidad
    return total // 12, total % 12 + 1


def _nombre_mes(mes):
    return [
        "",
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    ][mes]


def _proteger_superusuario(request, objetivo):
    if objetivo.is_superuser and not request.user.is_superuser:
        raise PermissionDenied("Solo un superusuario puede modificar esa cuenta.")


@admin_required
def dashboard(request):
    hoy = timezone.localdate()
    mes_actual = Q(fecha_inicio__year=hoy.year, fecha_inicio__month=hoy.month)

    stats = {
        "condominios_activos": Condominio.objects.filter(activo=True).count(),
        "condominios_total": Condominio.objects.count(),
        "drones_operativos": Dron.objects.filter(
            estado=Dron.Estado.OPERATIVO, marca__activa=True
        ).count(),
        "drones_total": Dron.objects.count(),
        "operadores_activos": Usuario.objects.filter(
            rol=Usuario.Rol.OPERADOR, is_active=True
        ).count(),
        "turnos_mes": Turno.objects.filter(mes_actual).count(),
        "vuelos_mes": Vuelo.objects.filter(
            hora_inicio__year=hoy.year, hora_inicio__month=hoy.month
        ).count(),
        "turnos_activos": Turno.objects.filter(cerrado=False).count(),
        "videos_pendientes": Vuelo.objects.filter(
            hora_fin__isnull=False, video_subido_en__isnull=True
        ).count(),
    }

    # Serie de los últimos 6 meses para el gráfico de barras.
    serie = []
    for i in range(5, -1, -1):
        anio, mes = _hace_meses(hoy.year, hoy.month, i)
        cantidad = Vuelo.objects.filter(
            hora_inicio__year=anio, hora_inicio__month=mes
        ).count()
        serie.append(
            {
                "etiqueta": f"{_nombre_mes(mes)[:3]} {str(anio)[2:]}",
                "mes": f"{_nombre_mes(mes)} {anio}",
                "cantidad": cantidad,
            }
        )
    maximo = max((s["cantidad"] for s in serie), default=0)
    for s in serie:
        s["porcentaje"] = round((s["cantidad"] / maximo) * 100) if maximo else 0

    recientes = (
        Turno.objects.select_related("operador", "condominio")
        .annotate(total_vuelos=Count("vuelos"))
        .order_by("-fecha_inicio")[:8]
    )

    top_operadores = (
        Usuario.objects.filter(rol=Usuario.Rol.OPERADOR)
        .annotate(
            vuelos_mes=Count(
                "turnos__vuelos",
                filter=Q(
                    turnos__vuelos__hora_inicio__year=hoy.year,
                    turnos__vuelos__hora_inicio__month=hoy.month,
                ),
            )
        )
        .filter(vuelos_mes__gt=0)
        .order_by("-vuelos_mes", "first_name", "username")[:5]
    )

    contexto = {
        "stats": stats,
        "serie": serie,
        "recientes": recientes,
        "top_operadores": top_operadores,
        "mes_label": f"{_nombre_mes(hoy.month)} {hoy.year}",
        "hoy": hoy,
    }
    return render(request, "admin_panel/dashboard.html", contexto)


# ---------------------------------------------------------------------------
# Condominios
# ---------------------------------------------------------------------------
@admin_required
def condominios(request):
    busqueda = request.GET.get("q", "").strip()
    queryset = Condominio.objects.annotate(
        total_turnos=Count("turnos", distinct=True)
    )
    if busqueda:
        queryset = queryset.filter(
            Q(nombre__icontains=busqueda) | Q(comuna_ciudad__icontains=busqueda)
        )
    return render(
        request,
        "admin_panel/condominios.html",
        {"condominios": queryset, "busqueda": busqueda},
    )


@admin_required
def condominio_crear(request):
    form = CondominioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        condominio = form.save()
        messages.success(request, f"Condominio «{condominio.nombre}» creado correctamente.")
        return redirect("gestion:condominios")
    return render(
        request,
        "admin_panel/condominio_form.html",
        {"form": form, "titulo": "Nuevo condominio", "es_edicion": False},
    )


@admin_required
def condominio_editar(request, pk):
    condominio = get_object_or_404(Condominio, pk=pk)
    form = CondominioForm(request.POST or None, instance=condominio)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Condominio actualizado correctamente.")
        return redirect("gestion:condominios")
    return render(
        request,
        "admin_panel/condominio_form.html",
        {
            "form": form,
            "titulo": "Editar condominio",
            "subtitulo": condominio.nombre,
            "objeto": condominio,
            "es_edicion": True,
        },
    )


@admin_required
@require_POST
def condominio_toggle(request, pk):
    condominio = get_object_or_404(Condominio, pk=pk)
    condominio.activo = not condominio.activo
    condominio.save(update_fields=["activo"])
    estado = "activado" if condominio.activo else "desactivado"
    messages.success(request, f"Condominio «{condominio.nombre}» {estado}.")
    return redirect("gestion:condominios")


# ---------------------------------------------------------------------------
# Marcas de drones
# ---------------------------------------------------------------------------
@admin_required
def marcas(request):
    queryset = MarcaDron.objects.annotate(total_drones=Count("drones"))
    return render(
        request,
        "admin_panel/marcas.html",
        {"marcas": queryset},
    )


@admin_required
def marca_crear(request):
    form = MarcaDronForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        marca = form.save()
        messages.success(request, f"Marca «{marca.nombre}» creada correctamente.")
        return redirect("gestion:marcas")
    return render(
        request,
        "admin_panel/marca_form.html",
        {"form": form, "titulo": "Nueva marca", "es_edicion": False},
    )


@admin_required
def marca_editar(request, pk):
    marca = get_object_or_404(MarcaDron, pk=pk)
    form = MarcaDronForm(request.POST or None, instance=marca)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Marca actualizada correctamente.")
        return redirect("gestion:marcas")
    return render(
        request,
        "admin_panel/marca_form.html",
        {
            "form": form,
            "titulo": "Editar marca",
            "subtitulo": marca.nombre,
            "objeto": marca,
            "es_edicion": True,
        },
    )


@admin_required
@require_POST
def marca_toggle(request, pk):
    marca = get_object_or_404(MarcaDron, pk=pk)
    marca.activa = not marca.activa
    marca.save(update_fields=["activa"])
    estado = "activada" if marca.activa else "desactivada"
    messages.success(request, f"Marca «{marca.nombre}» {estado}.")
    if not marca.activa:
        messages.info(
            request,
            "Los drones de esta marca no aparecerán disponibles para nuevos vuelos.",
        )
    return redirect("gestion:marcas")


# ---------------------------------------------------------------------------
# Drones
# ---------------------------------------------------------------------------
@admin_required
def drones(request):
    estado = request.GET.get("estado", "").strip()
    marca_id = request.GET.get("marca", "").strip()
    queryset = Dron.objects.select_related("marca").annotate(
        total_vuelos=Count("vuelos")
    )
    if estado in dict(Dron.Estado.choices):
        queryset = queryset.filter(estado=estado)
    if marca_id.isdigit():
        queryset = queryset.filter(marca_id=int(marca_id))
    return render(
        request,
        "admin_panel/drones.html",
        {
            "drones": queryset,
            "marcas": MarcaDron.objects.all(),
            "estados": Dron.Estado.choices,
            "estado_sel": estado,
            "marca_sel": marca_id,
        },
    )


@admin_required
def dron_crear(request):
    form = DronForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dron = form.save()
        messages.success(
            request, f"Dron «{dron.codigo_identificador}» registrado correctamente."
        )
        return redirect("gestion:drones")
    return render(
        request,
        "admin_panel/dron_form.html",
        {"form": form, "titulo": "Nuevo dron", "es_edicion": False},
    )


@admin_required
def dron_editar(request, pk):
    dron = get_object_or_404(Dron, pk=pk)
    form = DronForm(request.POST or None, instance=dron)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dron actualizado correctamente.")
        return redirect("gestion:drones")
    return render(
        request,
        "admin_panel/dron_form.html",
        {
            "form": form,
            "titulo": "Editar dron",
            "subtitulo": dron.codigo_identificador,
            "objeto": dron,
            "es_edicion": True,
        },
    )


@admin_required
@require_POST
def dron_cambiar_estado(request, pk):
    dron = get_object_or_404(Dron, pk=pk)
    nuevo_estado = request.POST.get("estado", "")
    if nuevo_estado not in dict(Dron.Estado.choices):
        messages.error(request, "Estado de dron no válido.")
        return redirect("gestion:drones")
    dron.estado = nuevo_estado
    dron.save(update_fields=["estado"])
    messages.success(
        request,
        f"Dron «{dron.codigo_identificador}» actualizado a "
        f"«{dron.get_estado_display()}».",
    )
    return redirect("gestion:drones")


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
@admin_required
def usuarios(request):
    rol = request.GET.get("rol", "").strip()
    busqueda = request.GET.get("q", "").strip()
    queryset = Usuario.objects.annotate(total_turnos=Count("turnos")).order_by(
        "rol", "first_name", "username"
    )
    if rol in dict(Usuario.Rol.choices):
        queryset = queryset.filter(rol=rol)
    if busqueda:
        queryset = queryset.filter(
            Q(username__icontains=busqueda)
            | Q(first_name__icontains=busqueda)
            | Q(last_name__icontains=busqueda)
            | Q(email__icontains=busqueda)
        )
    return render(
        request,
        "admin_panel/usuarios.html",
        {
            "usuarios": queryset,
            "roles": Usuario.Rol.choices,
            "rol_sel": rol,
            "busqueda": busqueda,
        },
    )


@admin_required
def usuario_crear(request):
    form = UsuarioCrearForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        usuario = Usuario.objects.create_user(
            username=datos["username"],
            password=datos["password1"],
            first_name=datos["first_name"],
            last_name=datos["last_name"],
            email=datos["email"],
            rol=datos["rol"],
            rut_o_dni=datos["rut_o_dni"],
            telefono=datos["telefono"],
            is_active=datos["is_active"],
        )
        messages.success(
            request,
            f"Usuario «{usuario.username}» creado con el rol "
            f"{usuario.get_rol_display()}.",
        )
        return redirect("gestion:usuarios")
    return render(
        request,
        "admin_panel/usuario_form.html",
        {"form": form, "titulo": "Nuevo usuario", "es_edicion": False},
    )


@admin_required
def usuario_editar(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    _proteger_superusuario(request, usuario)
    form = UsuarioEditarForm(
        request.POST or None,
        instance=usuario,
        usuario_solicitante=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Usuario actualizado correctamente.")
        return redirect("gestion:usuarios")
    return render(
        request,
        "admin_panel/usuario_form.html",
        {
            "form": form,
            "titulo": "Editar usuario",
            "subtitulo": usuario.username,
            "objeto": usuario,
            "es_edicion": True,
        },
    )


@admin_required
@require_POST
def usuario_toggle(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    _proteger_superusuario(request, usuario)
    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect("gestion:usuarios")
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=["is_active"])
    estado = "activado" if usuario.is_active else "desactivado"
    messages.success(request, f"Usuario «{usuario.username}» {estado}.")
    return redirect("gestion:usuarios")


@admin_required
def usuario_password(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    _proteger_superusuario(request, usuario)
    form = RestablecerPasswordForm(request.POST or None, usuario=usuario)
    if request.method == "POST" and form.is_valid():
        usuario.set_password(form.cleaned_data["password1"])
        usuario.save(update_fields=["password"])
        if usuario.pk == request.user.pk:
            update_session_auth_hash(request, usuario)
        messages.success(
            request, f"Contraseña de «{usuario.username}» restablecida correctamente."
        )
        return redirect("gestion:usuarios")
    return render(
        request,
        "admin_panel/usuario_password.html",
        {"form": form, "usuario_obj": usuario},
    )
