from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Condominio, Dron, MarcaDron, Turno, Usuario, Vuelo


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Datos de operación",
            {"fields": ("rol", "rut_o_dni", "telefono")},
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Datos de operación",
            {"fields": ("rol", "rut_o_dni", "telefono")},
        ),
    )
    list_display = ("username", "get_full_name", "rol", "is_active", "is_staff")
    list_filter = ("rol", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "first_name", "last_name", "email", "rut_o_dni")


@admin.register(Condominio)
class CondominioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "comuna_ciudad", "activo", "creado_en")
    list_filter = ("activo", "comuna_ciudad")
    search_fields = ("nombre", "direccion", "comuna_ciudad")


@admin.register(MarcaDron)
class MarcaDronAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activa")
    list_filter = ("activa",)
    search_fields = ("nombre",)


@admin.register(Dron)
class DronAdmin(admin.ModelAdmin):
    list_display = ("codigo_identificador", "marca", "modelo", "estado")
    list_filter = ("estado", "marca")
    search_fields = ("codigo_identificador", "modelo", "marca__nombre")


class VueloInline(admin.TabularInline):
    model = Vuelo
    extra = 0
    fields = ("dron", "hora_inicio", "hora_fin", "observaciones")
    readonly_fields = ()


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "operador",
        "condominio",
        "fecha_inicio",
        "fecha_fin",
        "cerrado",
    )
    list_filter = ("cerrado", "condominio", "operador")
    date_hierarchy = "fecha_inicio"
    search_fields = (
        "operador__username",
        "operador__first_name",
        "operador__last_name",
        "condominio__nombre",
    )
    inlines = [VueloInline]


@admin.register(Vuelo)
class VueloAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "turno",
        "dron",
        "hora_inicio",
        "hora_fin",
        "video_r2_key",
    )
    list_filter = ("dron__marca", "dron")
    date_hierarchy = "hora_inicio"
    search_fields = ("dron__codigo_identificador", "turno__condominio__nombre")
    readonly_fields = ("video_subido_en",)
