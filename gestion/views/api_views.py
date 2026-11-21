import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from gestion.models import Turno, Vuelo
from gestion.services import r2_storage


def _json_error(mensaje, status=400):
    return JsonResponse({"ok": False, "error": mensaje}, status=status)


def _cuerpo_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return None


def _autorizado(usuario, turno):
    return usuario.is_authenticated and (
        usuario.es_admin() or turno.operador_id == usuario.id
    )


@require_POST
def presigned_uploads(request, pk):
    """
    Genera URLs firmadas (o URLs locales en modo de desarrollo) para que el
    navegador suba los videos directamente al almacenamiento.
    """
    turno = get_object_or_404(
        Turno.objects.select_related("condominio", "operador"), pk=pk
    )
    if not _autorizado(request.user, turno):
        return _json_error("No tienes permisos sobre este turno.", 403)
    if not turno.cerrado:
        return _json_error("El turno debe estar cerrado para subir videos.", 409)

    datos = _cuerpo_json(request)
    if datos is None:
        return _json_error("El cuerpo de la petición no es JSON válido.")

    ids = datos.get("vuelo_ids")
    if not isinstance(ids, list) or not ids:
        return _json_error("Debes indicar al menos un vuelo.")
    if len(ids) > 40:
        return _json_error("Máximo 40 vuelos por lote.")
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return _json_error("Los identificadores de vuelo no son válidos.")

    vuelos = list(
        turno.vuelos.filter(pk__in=ids, hora_fin__isnull=False).select_related(
            "turno__condominio"
        )
    )
    encontrados = {v.pk for v in vuelos}
    faltantes = [i for i in ids if i not in encontrados]
    if faltantes:
        return _json_error(
            f"Vuelos no encontrados o sin finalizar: {faltantes}.", 404
        )

    modo = "r2" if r2_storage.r2_configurado() else "local"
    resultado = []
    try:
        for vuelo in vuelos:
            key = r2_storage.key_para_vuelo(vuelo)
            if modo == "r2":
                url = r2_storage.generar_presigned_put(key)
                metodo = "PUT"
                headers = {"Content-Type": "video/mp4"}
            else:
                url = reverse("gestion:api_subida_local", args=[vuelo.pk])
                metodo = "POST"
                headers = {}
            resultado.append(
                {
                    "vuelo_id": vuelo.pk,
                    "modo": modo,
                    "upload_url": url,
                    "method": metodo,
                    "headers": headers,
                    "key": key,
                    "confirm_url": reverse(
                        "gestion:api_confirmar_video", args=[vuelo.pk]
                    ),
                }
            )
    except r2_storage.ErrorAlmacenamiento:
        return _json_error("No se pudieron generar las URLs de subida.", 502)

    return JsonResponse(
        {
            "ok": True,
            "modo": modo,
            "expira_en": 3600,
            "vuelos": resultado,
        }
    )


@require_POST
def subida_local(request, pk):
    """Receptor de respaldo para desarrollo cuando R2 no está configurado."""
    if r2_storage.r2_configurado():
        return _json_error("La subida local está deshabilitada porque R2 está activo.", 403)

    vuelo = get_object_or_404(
        Vuelo.objects.select_related("turno__operador"), pk=pk
    )
    if not _autorizado(request.user, vuelo.turno):
        return _json_error("No tienes permisos sobre este vuelo.", 403)
    if not vuelo.turno.cerrado:
        return _json_error("El turno debe estar cerrado.", 409)

    archivo = request.FILES.get("file")
    if not archivo:
        return _json_error("No se recibió ningún archivo de video.")

    tipo = (archivo.content_type or "").lower()
    nombre = (archivo.name or "").lower()
    extensiones_validas = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
    if not tipo.startswith("video/") and not nombre.endswith(extensiones_validas):
        return _json_error("El archivo debe ser un video MP4/MOV/WebM.")
    if archivo.size == 0:
        return _json_error("El archivo está vacío.")

    key = r2_storage.key_para_vuelo(vuelo)
    try:
        peso = r2_storage.guardar_video_local(archivo, key)
    except r2_storage.ErrorAlmacenamiento as exc:
        return _json_error(str(exc), 413)

    return JsonResponse({"ok": True, "key": key, "peso_mb": float(peso)})


@require_POST
def confirmar_video(request, pk):
    """Confirma la subida, verifica el objeto y guarda los metadatos en PostgreSQL."""
    vuelo = get_object_or_404(
        Vuelo.objects.select_related("turno__operador"), pk=pk
    )
    if not _autorizado(request.user, vuelo.turno):
        return _json_error("No tienes permisos sobre este vuelo.", 403)
    if not vuelo.turno.cerrado:
        return _json_error("El turno debe estar cerrado.", 409)

    key = r2_storage.key_para_vuelo(vuelo)
    peso_recibido = None
    datos = _cuerpo_json(request)
    if datos:
        try:
            if datos.get("peso_mb") is not None:
                peso_recibido = Decimal(str(datos["peso_mb"])).quantize(
                    Decimal("0.01")
                )
        except (InvalidOperation, TypeError, ValueError):
            peso_recibido = None

    try:
        if r2_storage.r2_configurado():
            existe, peso = r2_storage.existe_video_r2(key)
            if not existe:
                return _json_error(
                    "El video aún no está disponible en el almacenamiento. "
                    "Espera unos segundos e inténtalo de nuevo.",
                    409,
                )
        else:
            peso = r2_storage.peso_video_local_mb(key)
            if peso is None:
                return _json_error(
                    "El archivo no existe en el almacenamiento local. "
                    "Vuelve a intentar la subida.",
                    409,
                )
    except r2_storage.ErrorAlmacenamiento as exc:
        return _json_error(str(exc), 502)

    if peso is None:
        peso = peso_recibido
    if peso is None:
        return _json_error("No fue posible determinar el peso del video.", 422)

    vuelo.video_r2_key = key
    vuelo.video_peso_mb = peso
    vuelo.video_subido_en = timezone.now()
    vuelo.save(update_fields=["video_r2_key", "video_peso_mb", "video_subido_en"])

    return JsonResponse(
        {
            "ok": True,
            "vuelo_id": vuelo.pk,
            "video_r2_key": key,
            "peso_mb": float(peso),
            "video_subido_en": vuelo.video_subido_en.isoformat(),
            "video_disponible": vuelo.video_disponible,
        }
    )


@require_GET
def video_url(request, pk):
    vuelo = get_object_or_404(
        Vuelo.objects.select_related("turno__operador"), pk=pk
    )
    if not _autorizado(request.user, vuelo.turno):
        return _json_error("No tienes permisos sobre este vuelo.", 403)
    if not vuelo.video_disponible:
        return _json_error(
            "El video no está disponible o expiró (retención de 60 días).", 410
        )
    return JsonResponse(
        {
            "ok": True,
            "url": reverse("gestion:video_vuelo", args=[vuelo.pk]),
            "expira_en": 3600,
        }
    )
