import re

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from gestion.decorators import operador_required
from gestion.forms import (
    CerrarTurnoForm,
    FinalizarVueloForm,
    IniciarTurnoForm,
    IniciarVueloForm,
)
from gestion.models import Dron, Turno, Vuelo
from gestion.services import r2_storage


def _turno_activo(usuario):
    return (
        Turno.objects.filter(operador=usuario, cerrado=False)
        .select_related("condominio")
        .order_by("-fecha_inicio")
        .first()
    )


def _puede_ver(usuario, turno):
    return usuario.es_admin() or turno.operador_id == usuario.id


@operador_required
def dashboard(request):
    turno = _turno_activo(request.user)
    vuelos = []
    vuelo_abierto = None
    form_iniciar_vuelo = None
    form_finalizar_vuelo = None

    if turno:
        vuelos = list(
            turno.vuelos.select_related("dron__marca").order_by("hora_inicio")
        )
        vuelo_abierto = next((v for v in vuelos if v.hora_fin is None), None)
        if not vuelo_abierto:
            form_iniciar_vuelo = IniciarVueloForm()
        else:
            form_finalizar_vuelo = FinalizarVueloForm()

    hoy = timezone.localdate()
    turnos_mes = Turno.objects.filter(
        operador=request.user, fecha_inicio__year=hoy.year, fecha_inicio__month=hoy.month
    )
    vuelos_mes = Vuelo.objects.filter(
        turno__operador=request.user,
        hora_inicio__year=hoy.year,
        hora_inicio__month=hoy.month,
    )
    vuelos_mes_lista = list(vuelos_mes)
    minutos_mes = sum(
        (v.duracion_minutos or 0) for v in vuelos_mes_lista if v.duracion_minutos
    )

    recientes = (
        Turno.objects.filter(operador=request.user)
        .select_related("condominio")
        .annotate(total_vuelos=Count("vuelos"))
        .order_by("-fecha_inicio")[:6]
    )

    turno_pendiente = None
    if not turno:
        candidatos = (
            Turno.objects.filter(operador=request.user, cerrado=True, vuelos__isnull=False)
            .filter(
                Q(vuelos__video_r2_key="") | Q(vuelos__video_subido_en__isnull=True)
            )
            .distinct()
            .order_by("-fecha_fin")[:1]
        )
        turno_pendiente = candidatos.first()

    contexto = {
        "turno": turno,
        "vuelos": vuelos,
        "vuelo_abierto": vuelo_abierto,
        "form_iniciar_turno": IniciarTurnoForm(),
        "form_iniciar_vuelo": form_iniciar_vuelo,
        "form_finalizar_vuelo": form_finalizar_vuelo,
        "form_cerrar_turno": CerrarTurnoForm(),
        "stats": {
            "turnos_mes": turnos_mes.count(),
            "vuelos_mes": len(vuelos_mes_lista),
            "horas_mes": round(minutos_mes / 60, 1),
        },
        "recientes": recientes,
        "turno_pendiente": turno_pendiente,
        "drones_disponibles": Dron.objects.filter(
            estado=Dron.Estado.OPERATIVO, marca__activa=True
        ).count(),
    }
    return render(request, "operador/dashboard.html", contexto)


@operador_required
@require_POST
def abrir_turno(request):
    with transaction.atomic():
        activo = (
            Turno.objects.select_for_update()
            .filter(operador=request.user, cerrado=False)
            .exists()
        )
        if activo:
            messages.warning(request, "Ya tienes un turno activo. Debes cerrarlo primero.")
            return redirect("gestion:operador_dashboard")

        form = IniciarTurnoForm(request.POST)
        if form.is_valid():
            turno = Turno.objects.create(
                operador=request.user,
                condominio=form.cleaned_data["condominio"],
                observaciones_generales=form.cleaned_data["observaciones_generales"],
                fecha_inicio=timezone.now(),
            )
            messages.success(
                request,
                f"Turno iniciado en {turno.condominio.nombre}. ¡Buen vuelo!",
            )
        else:
            for errores in form.errors.values():
                for error in errores:
                    messages.error(request, error)
    return redirect("gestion:operador_dashboard")


@operador_required
@require_POST
def iniciar_vuelo(request):
    turno = _turno_activo(request.user)
    if not turno:
        messages.error(request, "No tienes un turno activo.")
        return redirect("gestion:operador_dashboard")

    if turno.vuelos.filter(hora_fin__isnull=True).exists():
        messages.warning(request, "Ya hay un vuelo en curso. Finalízalo antes de despegar.")
        return redirect("gestion:operador_dashboard")

    form = IniciarVueloForm(request.POST)
    if form.is_valid():
        dron = form.cleaned_data["dron"]
        if not dron.disponible:
            messages.error(request, "El dron seleccionado no está disponible.")
        else:
            vuelo = Vuelo.objects.create(
                turno=turno,
                dron=dron,
                hora_inicio=timezone.now(),
                observaciones=form.cleaned_data["observaciones"],
            )
            messages.success(
                request,
                f"Vuelo iniciado con {vuelo.dron.codigo_identificador} "
                f"a las {timezone.localtime(vuelo.hora_inicio):%H:%M}.",
            )
    else:
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
    return redirect("gestion:operador_dashboard")


@operador_required
@require_POST
def finalizar_vuelo(request, pk):
    vuelo = get_object_or_404(
        Vuelo.objects.select_related("turno", "dron"),
        pk=pk,
        turno__operador=request.user,
        turno__cerrado=False,
        hora_fin__isnull=True,
    )
    form = FinalizarVueloForm(request.POST)
    if form.is_valid():
        nueva_observacion = form.cleaned_data["observaciones"].strip()
        if nueva_observacion:
            if vuelo.observaciones:
                vuelo.observaciones = f"{vuelo.observaciones}\n{nueva_observacion}"
            else:
                vuelo.observaciones = nueva_observacion
        vuelo.hora_fin = timezone.now()
        vuelo.save(update_fields=["observaciones", "hora_fin"])
        messages.success(
            request,
            f"Vuelo finalizado. Duración: {vuelo.duracion_minutos} minutos.",
        )
    else:
        messages.error(request, "No se pudo finalizar el vuelo. Revisa los datos.")
    return redirect("gestion:operador_dashboard")


@operador_required
@require_POST
def cerrar_turno(request, pk):
    turno = get_object_or_404(
        Turno.objects.select_related("condominio"),
        pk=pk,
        operador=request.user,
        cerrado=False,
    )
    if turno.vuelos.filter(hora_fin__isnull=True).exists():
        messages.error(request, "Debes finalizar el vuelo en curso antes de cerrar el turno.")
        return redirect("gestion:operador_dashboard")

    form = CerrarTurnoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "No se pudo cerrar el turno.")
        return redirect("gestion:operador_dashboard")

    turno.fecha_fin = timezone.now()
    turno.cerrado = True
    observaciones = form.cleaned_data["observaciones_generales"].strip()
    if observaciones:
        turno.observaciones_generales = (
            f"{turno.observaciones_generales}\n{observaciones}".strip()
            if turno.observaciones_generales
            else observaciones
        )
    turno.save(
        update_fields=["fecha_fin", "cerrado", "observaciones_generales"]
    )
    messages.success(
        request,
        f"Turno cerrado. Ahora puedes subir los videos de "
        f"{turno.vuelos_completados} vuelo(s).",
    )
    return redirect("gestion:subir_videos", pk=turno.pk)


@operador_required
def subir_videos(request, pk):
    turno = get_object_or_404(
        Turno.objects.select_related("condominio", "operador"),
        pk=pk,
        operador=request.user,
    )
    if not turno.cerrado:
        messages.warning(request, "Cierra el turno antes de subir los videos.")
        return redirect("gestion:operador_dashboard")

    vuelos = list(
        turno.vuelos.select_related("dron__marca")
        .filter(hora_fin__isnull=False)
        .order_by("hora_inicio")
    )
    pendientes = [
        v for v in vuelos if not v.video_r2_key or not v.video_subido_en
    ]
    contexto = {
        "turno": turno,
        "vuelos": vuelos,
        "pendientes": pendientes,
        "total_pendientes": len(pendientes),
        "total_disponibles": len(vuelos) - len(pendientes),
        "r2_configurado": r2_storage.r2_configurado(),
    }
    return render(request, "operador/subir_videos.html", contexto)


@operador_required
def historial(request):
    queryset = (
        Turno.objects.filter(operador=request.user)
        .select_related("condominio")
        .annotate(
            total_vuelos=Count("vuelos"),
            videos_subidos=Count(
                "vuelos",
                filter=Q(
                    vuelos__video_r2_key__gt="",
                    vuelos__video_subido_en__isnull=False,
                ),
            ),
            vuelos_abiertos=Count(
                "vuelos", filter=Q(vuelos__hora_fin__isnull=True)
            ),
        )
        .order_by("-fecha_inicio")
    )
    paginador = Paginator(queryset, 15)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "operador/historial.html",
        {"page_obj": pagina, "turnos": pagina.object_list},
    )


def turno_detalle(request, pk):
    """Detalle compartido: el operador ve sus turnos y el admin todos."""
    if not request.user.is_authenticated:
        return redirect("gestion:login")
    turno = get_object_or_404(
        Turno.objects.select_related("operador", "condominio"), pk=pk
    )
    if not _puede_ver(request.user, turno):
        raise Http404

    vuelos = list(
        turno.vuelos.select_related("dron__marca").order_by("hora_inicio")
    )
    minutos = sum((v.duracion_minutos or 0) for v in vuelos)
    contexto = {
        "turno": turno,
        "vuelos": vuelos,
        "minutos_totales": minutos,
        "es_admin": request.user.es_admin(),
        "turno_activo": not turno.cerrado,
    }
    return render(request, "operador/turno_detalle.html", contexto)


RANGO_BYTES = re.compile(r"^bytes=(\d*)-(\d*)$")


def _respuesta_video_local(request, ruta, nombre):
    """Sirve un video local con soporte de Range para permitir la búsqueda."""
    tamano = ruta.stat().st_size
    rango = (request.headers.get("Range") or "").strip()

    if rango:
        coincidencia = RANGO_BYTES.match(rango)
        inicio = fin = None
        if coincidencia:
            inicio_txt, fin_txt = coincidencia.groups()
            if inicio_txt:
                inicio = int(inicio_txt)
                fin = int(fin_txt) if fin_txt else tamano - 1
            elif fin_txt:
                longitud = int(fin_txt)
                inicio = max(tamano - longitud, 0)
                fin = tamano - 1

        if inicio is None or inicio > fin or fin >= tamano:
            respuesta = HttpResponse(status=416)
            respuesta["Content-Range"] = f"bytes */{tamano}"
            respuesta["Accept-Ranges"] = "bytes"
            return respuesta

        longitud = fin - inicio + 1

        def leer_bloques():
            with ruta.open("rb") as archivo:
                archivo.seek(inicio)
                restante = longitud
                while restante > 0:
                    bloque = archivo.read(min(64 * 1024, restante))
                    if not bloque:
                        break
                    restante -= len(bloque)
                    yield bloque

        respuesta = StreamingHttpResponse(
            leer_bloques(), status=206, content_type="video/mp4"
        )
        respuesta["Content-Range"] = f"bytes {inicio}-{fin}/{tamano}"
        respuesta["Content-Length"] = str(longitud)
        respuesta["Accept-Ranges"] = "bytes"
        respuesta["Content-Disposition"] = f'inline; filename="{nombre}"'
        return respuesta

    respuesta = FileResponse(
        ruta.open("rb"),
        content_type="video/mp4",
        as_attachment=False,
        filename=nombre,
    )
    respuesta["Accept-Ranges"] = "bytes"
    return respuesta


def video_vuelo(request, pk):
    """Entrega el video (presigned GET de R2 o archivo local) con control de acceso."""
    if not request.user.is_authenticated:
        return redirect("gestion:login")

    vuelo = get_object_or_404(
        Vuelo.objects.select_related("turno__operador", "dron"), pk=pk
    )
    if not _puede_ver(request.user, vuelo.turno):
        raise Http404

    if not vuelo.video_disponible:
        mensaje = (
            "El video expiró: han transcurrido más de 60 días desde su subida."
            if vuelo.video_r2_key
            else "Este vuelo no tiene un video asociado."
        )
        return HttpResponse(mensaje, status=410, content_type="text/plain; charset=utf-8")

    if r2_storage.r2_configurado() and not r2_storage.existe_video_local(
        vuelo.video_r2_key
    ):
        try:
            url = r2_storage.generar_presigned_get(vuelo.video_r2_key)
            return redirect(url)
        except r2_storage.ErrorAlmacenamiento:
            return HttpResponse(
                "No fue posible generar el enlace de reproducción.",
                status=502,
                content_type="text/plain; charset=utf-8",
            )

    if r2_storage.existe_video_local(vuelo.video_r2_key):
        return _respuesta_video_local(
            request,
            r2_storage.ruta_local(vuelo.video_r2_key),
            f"vuelo_{vuelo.id}.mp4",
        )

    return HttpResponse(
        "El archivo de video no está disponible en el almacenamiento.",
        status=404,
        content_type="text/plain; charset=utf-8",
    )


def video_url_api(request, pk):
    """URL temporal para el reproductor del frontend."""
    if not request.user.is_authenticated:
        return redirect("gestion:login")
    vuelo = get_object_or_404(Vuelo.objects.select_related("turno"), pk=pk)
    if not _puede_ver(request.user, vuelo.turno):
        raise Http404
    if not vuelo.video_disponible:
        return HttpResponse(
            '{"error": "El video no está disponible o expiró (>60 días)."}',
            status=410,
            content_type="application/json",
        )
    return HttpResponse(
        '{"url": "%s"}' % reverse("gestion:video_vuelo", args=[vuelo.pk]),
        content_type="application/json",
    )
