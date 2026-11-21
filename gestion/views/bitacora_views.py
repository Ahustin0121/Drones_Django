from collections import defaultdict
from django.shortcuts import render
from django.utils import timezone

from gestion.decorators import admin_required
from gestion.forms import BitacoraFiltroForm
from gestion.models import Condominio, Usuario, Vuelo


def _iniciales(usuario):
    nombres = f"{usuario.first_name} {usuario.last_name}".strip()
    if not nombres:
        return usuario.username[:2].upper()
    partes = [p for p in nombres.split() if p]
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def _mes_anterior(mes, anio):
    if mes == 1:
        return 12, anio - 1
    return mes - 1, anio


def _mes_siguiente(mes, anio):
    if mes == 12:
        return 1, anio + 1
    return mes + 1, anio


def _construir_grupos(vuelos):
    """Agrupa por condominio -> operador -> marca, con días y vuelos detallados."""
    condominios = {}

    for vuelo in vuelos:
        turno = vuelo.turno
        condominio = turno.condominio
        operador = turno.operador
        marca = vuelo.dron.marca
        fecha_local = timezone.localtime(vuelo.hora_inicio)
        dia = fecha_local.day

        grupo_condo = condominios.setdefault(
            condominio.pk,
            {
                "condominio": condominio,
                "total": 0,
                "minutos": 0,
                "dias": set(),
                "operadores": {},
            },
        )
        grupo_condo["total"] += 1
        grupo_condo["minutos"] += vuelo.duracion_minutos or 0
        grupo_condo["dias"].add(fecha_local.date())

        grupo_op = grupo_condo["operadores"].setdefault(
            operador.pk,
            {
                "operador": operador,
                "nombre": operador.nombre_completo(),
                "iniciales": _iniciales(operador),
                "total": 0,
                "minutos": 0,
                "dias": set(),
                "marcas": {},
                "vuelos": [],
            },
        )
        grupo_op["total"] += 1
        grupo_op["minutos"] += vuelo.duracion_minutos or 0
        grupo_op["dias"].add(fecha_local.date())
        grupo_op["vuelos"].append(vuelo)

        grupo_marca = grupo_op["marcas"].setdefault(
            marca.pk,
            {"nombre": marca.nombre, "total": 0, "dias": set()},
        )
        grupo_marca["total"] += 1
        grupo_marca["dias"].add(dia)

    resultado = []
    for grupo_condo in condominios.values():
        operadores = []
        for grupo_op in grupo_condo["operadores"].values():
            marcas = []
            for grupo_marca in grupo_op["marcas"].values():
                dias_ordenados = sorted(grupo_marca["dias"])
                marcas.append(
                    {
                        "nombre": grupo_marca["nombre"],
                        "total": grupo_marca["total"],
                        "dias": ", ".join(f"{d:02d}" for d in dias_ordenados),
                        "total_dias": len(dias_ordenados),
                    }
                )
            marcas.sort(key=lambda m: (-m["total"], m["nombre"]))
            grupo_op["marcas"] = marcas
            grupo_op["vuelos"].sort(key=lambda v: v.hora_inicio)
            grupo_op["horas"] = round(grupo_op["minutos"] / 60, 1)
            grupo_op["total_dias"] = len(grupo_op["dias"])
            grupo_op.pop("dias", None)
            operadores.append(grupo_op)

        operadores.sort(key=lambda o: (-o["total"], o["nombre"]))
        grupo_condo["operadores"] = operadores
        grupo_condo["horas"] = round(grupo_condo["minutos"] / 60, 1)
        grupo_condo["total_dias"] = len(grupo_condo["dias"])
        grupo_condo.pop("dias", None)
        resultado.append(grupo_condo)

    resultado.sort(key=lambda g: g["condominio"].nombre)
    return resultado


@admin_required
def bitacora(request):
    hoy = timezone.localdate()
    form = BitacoraFiltroForm(request.GET or None)

    if form.is_bound and form.is_valid():
        datos = form.cleaned_data
    else:
        datos = {
            "condominio": None,
            "mes": hoy.month,
            "anio": hoy.year,
            "operador": None,
        }
        form = BitacoraFiltroForm(
            initial={"mes": hoy.month, "anio": hoy.year}
        )

    mes = datos["mes"]
    anio = datos["anio"]
    condominio_sel = datos["condominio"]
    operador_sel = datos["operador"]

    queryset = (
        Vuelo.objects.filter(
            hora_fin__isnull=False,
            hora_inicio__year=anio,
            hora_inicio__month=mes,
        )
        .select_related(
            "turno__condominio", "turno__operador", "dron__marca"
        )
        .order_by(
            "turno__condominio__nombre",
            "turno__operador__first_name",
            "hora_inicio",
        )
    )
    if condominio_sel:
        queryset = queryset.filter(turno__condominio=condominio_sel)
    if operador_sel:
        queryset = queryset.filter(turno__operador=operador_sel)

    vuelos = list(queryset)
    grupos = _construir_grupos(vuelos)

    total_vuelos = len(vuelos)
    minutos_totales = sum(v.duracion_minutos or 0 for v in vuelos)
    operadores_unicos = {v.turno.operador_id for v in vuelos}
    condominios_unicos = {v.turno.condominio_id for v in vuelos}
    dias_unicos = {
        timezone.localtime(v.hora_inicio).date() for v in vuelos
    }

    meses = dict(BitacoraFiltroForm.MESES)
    prev_mes, prev_anio = _mes_anterior(mes, anio)
    next_mes, next_anio = _mes_siguiente(mes, anio)

    contexto = {
        "form": form,
        "grupos": grupos,
        "total_vuelos": total_vuelos,
        "total_operadores": len(operadores_unicos),
        "total_condominios": len(condominios_unicos),
        "total_dias": len(dias_unicos),
        "horas_totales": round(minutos_totales / 60, 1),
        "mes_label": f"{meses[mes]} {anio}",
        "mes_sel": mes,
        "anio_sel": anio,
        "condominio_sel": condominio_sel,
        "operador_sel": operador_sel,
        "prev_mes": prev_mes,
        "prev_anio": prev_anio,
        "next_mes": next_mes,
        "next_anio": next_anio,
        "es_mes_actual": (mes == hoy.month and anio == hoy.year),
        "hay_filtro_condominio": condominio_sel is not None,
        "total_condominios_catalogo": Condominio.objects.count(),
        "total_operadores_catalogo": Usuario.objects.filter(
            rol=Usuario.Rol.OPERADOR
        ).count(),
    }
    return render(request, "admin_panel/bitacora.html", contexto)
