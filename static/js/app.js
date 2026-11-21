/* AeroVigía · interacciones generales */
(function () {
    "use strict";

    document.addEventListener("alpine:init", function () {
        if (!window.Alpine) return;

        window.Alpine.data("cronometro", function (inicioIso) {
            return {
                inicio: new Date(inicioIso).getTime(),
                ahora: Date.now(),
                intervalo: null,
                init: function () {
                    this.intervalo = setInterval(() => {
                        this.ahora = Date.now();
                    }, 1000);
                },
                destroy: function () {
                    clearInterval(this.intervalo);
                },
                get tiempo() {
                    let segundos = Math.max(
                        0,
                        Math.floor((this.ahora - this.inicio) / 1000)
                    );
                    const h = Math.floor(segundos / 3600);
                    segundos %= 3600;
                    const m = Math.floor(segundos / 60);
                    const s = segundos % 60;
                    return (
                        String(h).padStart(2, "0") +
                        ":" +
                        String(m).padStart(2, "0") +
                        ":" +
                        String(s).padStart(2, "0")
                    );
                },
            };
        });
    });

    function cerrarMensaje(elemento) {
        elemento.style.transition = "opacity .25s ease, transform .25s ease";
        elemento.style.opacity = "0";
        elemento.style.transform = "translateY(-4px)";
        setTimeout(() => elemento.remove(), 260);
    }

    function iniciarMensajes() {
        document.querySelectorAll(".js-mensaje").forEach(function (mensaje) {
            const boton = mensaje.querySelector(".js-cerrar-mensaje");
            if (boton) boton.addEventListener("click", () => cerrarMensaje(mensaje));
            setTimeout(() => {
                if (document.body.contains(mensaje)) cerrarMensaje(mensaje);
            }, 9000);
        });
    }

    function iniciarConfirmaciones() {
        document.querySelectorAll("form[data-confirm]").forEach(function (form) {
            form.addEventListener("submit", function (evento) {
                if (!window.confirm(form.dataset.confirm)) {
                    evento.preventDefault();
                }
            });
        });
    }

    function iniciarVisorVideo() {
        const dialogo = document.getElementById("video-dialog");
        const reproductor = document.getElementById("video-player");
        const titulo = document.getElementById("video-dialog-title");
        if (!dialogo || !reproductor) return;

        document.querySelectorAll("[data-video-url]").forEach(function (boton) {
            boton.addEventListener("click", function () {
                const url = boton.dataset.videoUrl;
                if (!url) return;
                reproductor.src = url;
                if (titulo) {
                    titulo.textContent =
                        boton.dataset.videoTitle || "Video del vuelo";
                }
                if (typeof dialogo.showModal === "function") {
                    dialogo.showModal();
                } else {
                    dialogo.setAttribute("open", "");
                }
                const reproduccion = reproductor.play();
                if (reproduccion && reproduccion.catch) {
                    reproduccion.catch(() => {});
                }
            });
        });

        function cerrar() {
            reproductor.pause();
            reproductor.removeAttribute("src");
            reproductor.load();
            if (dialogo.open) dialogo.close();
        }

        const botonCerrar = dialogo.querySelector("[data-cerrar-video]");
        if (botonCerrar) botonCerrar.addEventListener("click", cerrar);
        dialogo.addEventListener("close", function () {
            reproductor.pause();
            reproductor.removeAttribute("src");
        });
        dialogo.addEventListener("click", function (evento) {
            if (evento.target === dialogo) cerrar();
        });
    }

    function iniciarTablasEstado() {
        document.querySelectorAll("[data-enviar-al-cambiar]").forEach(function (select) {
            select.addEventListener("change", function () {
                if (select.form) select.form.requestSubmit();
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        iniciarMensajes();
        iniciarConfirmaciones();
        iniciarVisorVideo();
        iniciarTablasEstado();
    });
})();
