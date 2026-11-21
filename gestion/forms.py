from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import Condominio, Dron, MarcaDron, Turno, Usuario

INPUT_CLASSES = (
    "w-full rounded-xl border border-slate-700 bg-slate-900/70 px-3.5 py-2.5 "
    "text-sm text-slate-100 placeholder-slate-500 shadow-sm transition "
    "focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-400/30"
)
CHECKBOX_CLASSES = (
    "h-4 w-4 rounded border-slate-600 bg-slate-900 text-cyan-500 "
    "focus:ring-2 focus:ring-cyan-400/40"
)
SELECT_CLASSES = INPUT_CLASSES + " pr-9"


class EstiloFormMixin:
    """Aplica clases de Tailwind de forma uniforme a todos los widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", CHECKBOX_CLASSES)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", SELECT_CLASSES)
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", INPUT_CLASSES)
                widget.attrs.setdefault("rows", 3)
            else:
                widget.attrs.setdefault("class", INPUT_CLASSES)
            if campo.required and not isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("required", True)


class CondominioForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Condominio
        fields = ["nombre", "direccion", "comuna_ciudad", "activo"]
        widgets = {
            "nombre": forms.TextInput(
                attrs={"placeholder": "Ej: Condominio Los Robles", "autofocus": True}
            ),
            "direccion": forms.TextInput(attrs={"placeholder": "Av. Principal 1234"}),
            "comuna_ciudad": forms.TextInput(attrs={"placeholder": "Ej: Santiago"}),
        }


class MarcaDronForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = MarcaDron
        fields = ["nombre", "activa"]
        widgets = {
            "nombre": forms.TextInput(
                attrs={"placeholder": "Ej: DJI, Autel, Parrot", "autofocus": True}
            )
        }


class DronForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Dron
        fields = [
            "codigo_identificador",
            "marca",
            "modelo",
            "estado",
            "notas",
        ]
        widgets = {
            "codigo_identificador": forms.TextInput(
                attrs={"placeholder": "Ej: DRON-01", "autofocus": True}
            ),
            "marca": forms.Select(),
            "modelo": forms.TextInput(attrs={"placeholder": "Ej: Mavic 3 Enterprise"}),
            "notas": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Observaciones de la unidad..."}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["marca"].queryset = MarcaDron.objects.all()

    def clean(self):
        cleaned = super().clean()
        marca = cleaned.get("marca")
        estado = cleaned.get("estado")
        if marca and not marca.activa and estado == Dron.Estado.OPERATIVO:
            if not (self.instance.pk and self.instance.marca_id == marca.pk):
                self.add_error(
                    "marca",
                    "No puedes dejar operativo un dron de una marca desactivada.",
                )
        return cleaned


class UsuarioCrearForm(EstiloFormMixin, forms.Form):
    username = forms.CharField(
        label="Nombre de usuario",
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Ej: jrivas", "autofocus": True}),
    )
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo electrónico", required=False)
    rol = forms.ChoiceField(label="Rol en el sistema", choices=Usuario.Rol.choices)
    rut_o_dni = forms.CharField(label="Identificación (RUT/DNI)", max_length=20, required=False)
    telefono = forms.CharField(label="Teléfono", max_length=30, required=False)
    is_active = forms.BooleanField(label="Cuenta activa", required=False, initial=True)
    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Mínimo 8 caracteres y no puede ser una clave común.",
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if Usuario.objects.filter(username__iexact=username).exists():
            raise ValidationError("Ya existe un usuario con ese nombre.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and Usuario.objects.filter(email__iexact=email).exists():
            raise ValidationError("Ya existe un usuario con ese correo.")
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if password1:
            usuario_temporal = Usuario(
                username=cleaned.get("username", ""),
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
                email=cleaned.get("email", ""),
            )
            try:
                validate_password(password1, usuario_temporal)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


class UsuarioEditarForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "rol",
            "rut_o_dni",
            "telefono",
            "is_active",
        ]
        widgets = {
            "username": forms.TextInput(attrs={"autofocus": True}),
            "email": forms.EmailInput(),
        }

    def __init__(self, *args, usuario_solicitante=None, **kwargs):
        self.usuario_solicitante = usuario_solicitante
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        existe = Usuario.objects.filter(username__iexact=username).exclude(
            pk=self.instance.pk
        )
        if existe.exists():
            raise ValidationError("Ya existe un usuario con ese nombre.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email:
            existe = Usuario.objects.filter(email__iexact=email).exclude(
                pk=self.instance.pk
            )
            if existe.exists():
                raise ValidationError("Ya existe un usuario con ese correo.")
        return email

    def clean(self):
        cleaned = super().clean()
        if self.usuario_solicitante and self.instance.pk == self.usuario_solicitante.pk:
            if cleaned.get("is_active") is False:
                self.add_error("is_active", "No puedes desactivar tu propia cuenta.")
            if cleaned.get("rol") != Usuario.Rol.ADMIN and not self.instance.is_superuser:
                self.add_error("rol", "No puedes quitarte el rol de administrador.")
        return cleaned


class RestablecerPasswordForm(EstiloFormMixin, forms.Form):
    password1 = forms.CharField(
        label="Nueva contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "autofocus": True}),
    )
    password2 = forms.CharField(
        label="Confirmar nueva contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if p1 and self.usuario:
            try:
                validate_password(p1, self.usuario)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


class IniciarTurnoForm(EstiloFormMixin, forms.Form):
    condominio = forms.ModelChoiceField(
        label="Condominio",
        queryset=Condominio.objects.filter(activo=True),
        empty_label="Selecciona un condominio",
    )
    observaciones_generales = forms.CharField(
        label="Observaciones generales",
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "Instrucciones o novedades del turno..."}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["condominio"].queryset = Condominio.objects.filter(activo=True)


class IniciarVueloForm(EstiloFormMixin, forms.Form):
    dron = forms.ModelChoiceField(
        label="Dron",
        queryset=Dron.objects.none(),
        empty_label="Selecciona un dron operativo",
    )
    observaciones = forms.CharField(
        label="Observaciones de despegue",
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "Zona a patrullar, condiciones, etc."}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dron"].queryset = Dron.objects.filter(
            estado=Dron.Estado.OPERATIVO, marca__activa=True
        ).select_related("marca")


class FinalizarVueloForm(EstiloFormMixin, forms.Form):
    observaciones = forms.CharField(
        label="Novedades al aterrizar",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Incidencias, hallazgos o cierre del vuelo...",
            }
        ),
    )


class CerrarTurnoForm(EstiloFormMixin, forms.Form):
    observaciones_generales = forms.CharField(
        label="Observaciones generales del turno",
        required=False,
        help_text="Opcional. Quedarán registradas en la bitácora.",
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class BitacoraFiltroForm(EstiloFormMixin, forms.Form):
    MESES = [
        (1, "Enero"),
        (2, "Febrero"),
        (3, "Marzo"),
        (4, "Abril"),
        (5, "Mayo"),
        (6, "Junio"),
        (7, "Julio"),
        (8, "Agosto"),
        (9, "Septiembre"),
        (10, "Octubre"),
        (11, "Noviembre"),
        (12, "Diciembre"),
    ]

    condominio = forms.ModelChoiceField(
        label="Condominio",
        queryset=Condominio.objects.all(),
        required=False,
        empty_label="Todos los condominios",
    )
    mes = forms.TypedChoiceField(
        label="Mes",
        choices=MESES,
        coerce=int,
        initial=timezone.localdate().month,
    )
    anio = forms.TypedChoiceField(
        label="Año",
        coerce=int,
        initial=timezone.localdate().year,
    )
    operador = forms.ModelChoiceField(
        label="Operador",
        queryset=Usuario.objects.filter(rol=Usuario.Rol.OPERADOR),
        required=False,
        empty_label="Todos los operadores",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        anio_actual = timezone.localdate().year
        anios = list(range(anio_actual - 3, anio_actual + 2))
        self.fields["anio"].choices = [(a, str(a)) for a in reversed(anios)]
        self.fields["condominio"].queryset = Condominio.objects.all()
        self.fields["operador"].queryset = Usuario.objects.filter(
            Q(rol=Usuario.Rol.OPERADOR) | Q(turnos__isnull=False)
        ).distinct()
        self.fields["condominio"].widget.attrs["class"] = SELECT_CLASSES
        self.fields["mes"].widget.attrs["class"] = SELECT_CLASSES
        self.fields["anio"].widget.attrs["class"] = SELECT_CLASSES
        self.fields["operador"].widget.attrs["class"] = SELECT_CLASSES
