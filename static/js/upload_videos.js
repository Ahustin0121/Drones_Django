/*
 * AeroVigía · Compresión y subida de videos en lote.
 *
 * Flujo:
 *  1. Se solicitan las URLs firmadas al backend.
 *  2. Cada video se comprime en el navegador con ffmpeg.wasm (720p H.264).
 *  3. Se sube directo a Cloudflare R2 con PUT (o al endpoint local en desarrollo).
 *  4. Se confirma la subida a Django para guardar los metadatos.
 *
 * Si ffmpeg.wasm no puede cargarse, se ofrece continuar con el archivo original.
 */
(function () {
    "use strict";

    const app = document.getElementById("upload-app");
    if (!app) return;

    const btnSubir = document.getElementById("btn-subir");
    const checkComprimir = document.getElementById("comprimir");
    const progresoTotal = document.getElementById("progreso-total");
    const progresoTexto = document.getElementById("progreso-texto");
    const resultadoGlobal = document.getElementById("resultado-global");
    const csrf = app.dataset.csrf || window.CSRF_TOKEN || "";
    const MAX_PARALELAS = 3;
    const MIN_BYTES_COMPRIMIR = 15 * 1024 * 1024;
    const FFMPEG_CORE = "https://unpkg.com/@ffmpeg/core@0.12.6/dist/umd";

    let ocupado = false;
    let ffmpegPromesa = null;
    let ffmpegInstancia = null;
    let subidosSesion = 0;
    // ffmpeg.wasm no es seguro para ejecuciones simultáneas: las compresiones
    // se encolan, mientras las subidas sí avanzan en paralelo.
    let colaCompresion = Promise.resolve();

    const filas = Array.from(document.querySelectorAll(".fila-vuelo")).map(function (fila) {
        const entrada = fila.querySelector(".archivo-vuelo");
        const item = {
            fila: fila,
            id: Number(fila.dataset.vueloId),
            numero: fila.dataset.numero,
            confirmUrl: fila.dataset.confirmUrl,
            input: entrada,
            etiqueta: fila.querySelector(".archivo-etiqueta"),
            estado: fila.querySelector(".estado-vuelo"),
            barra: fila.querySelector(".barra-vuelo"),
            relleno: fila.querySelector(".relleno-vuelo"),
            file: null,
            subido: false,
        };
        entrada.addEventListener("change", function () {
            const archivo = entrada.files && entrada.files[0];
            item.subido = false;
            if (!archivo) {
                item.file = null;
                item.etiqueta.textContent = "Seleccionar video…";
                ocultarEstado(item);
                return;
            }
            item.file = archivo;
            item.etiqueta.textContent = archivo.name;
            mostrarEstado(
                item,
                "Listo · " + formatearPeso(archivo.size),
                "neutro",
                0
            );
        });
        return item;
    });

    function formatearPeso(bytes) {
        if (bytes >= 1024 * 1024 * 1024) {
            return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
        }
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    function dormir(ms) {
        return new Promise((resolver) => setTimeout(resolver, ms));
    }

    function mostrarEstado(item, texto, tipo, porcentaje) {
        if (!item.estado) return;
        const colores = {
            neutro: "text-slate-500",
            trabajo: "text-cyan-300",
            exito: "text-emerald-300",
            error: "text-rose-300",
            aviso: "text-amber-300",
        };
        item.estado.className =
            "estado-vuelo mt-2 text-[10px] sm:ml-12 " + (colores[tipo] || colores.neutro);
        item.estado.textContent = texto;
        item.estado.classList.remove("hidden");
        if (item.barra) {
            item.barra.classList.remove("hidden");
            const valor = Math.max(0, Math.min(100, Number(porcentaje) || 0));
            item.relleno.style.width = valor + "%";
            if (tipo === "exito") {
                item.relleno.style.background = "linear-gradient(90deg,#34d399,#2dd4bf)";
            } else if (tipo === "error") {
                item.relleno.style.background = "linear-gradient(90deg,#fb7185,#f43f5e)";
            } else {
                item.relleno.style.background = "linear-gradient(90deg,#22d3ee,#2dd4bf)";
            }
        }
    }

    function ocultarEstado(item) {
        if (item.estado) {
            item.estado.textContent = "";
            item.estado.classList.add("hidden");
        }
        if (item.barra) item.barra.classList.add("hidden");
        if (item.relleno) item.relleno.style.width = "0%";
    }

    function mostrarGlobal(tipo, html) {
        const estilos = {
            info: "border-cyan-400/20 bg-cyan-400/[0.07] text-cyan-200",
            exito: "border-emerald-400/20 bg-emerald-400/[0.07] text-emerald-200",
            error: "border-rose-400/20 bg-rose-400/[0.07] text-rose-200",
            aviso: "border-amber-400/20 bg-amber-400/[0.07] text-amber-200",
        };
        resultadoGlobal.className =
            "mt-3 rounded-xl border px-3.5 py-3 text-[11px] leading-relaxed " +
            (estilos[tipo] || estilos.info);
        resultadoGlobal.innerHTML = html;
        resultadoGlobal.classList.remove("hidden");
    }

    function ocultarGlobal() {
        resultadoGlobal.classList.add("hidden");
        resultadoGlobal.innerHTML = "";
    }

    function actualizarProgreso(totalSeleccionados) {
        const porcentaje = totalSeleccionados
            ? Math.round((subidosSesion / totalSeleccionados) * 100)
            : 0;
        progresoTotal.style.width = porcentaje + "%";
        progresoTexto.textContent = subidosSesion + " / " + totalSeleccionados;
    }

    function bloquearInterfaz(bloqueado) {
        ocupado = bloqueado;
        btnSubir.disabled = bloqueado;
        btnSubir.classList.toggle("cursor-wait", bloqueado);
        checkComprimir.disabled = bloqueado;
        filas.forEach((fila) => {
            if (fila.input) fila.input.disabled = bloqueado;
        });
        if (bloqueado) {
            window.addEventListener("beforeunload", advertirSalida);
        } else {
            window.removeEventListener("beforeunload", advertirSalida);
        }
    }

    function advertirSalida(evento) {
        evento.preventDefault();
        evento.returnValue = "";
    }

    // ------------------------------------------------------------------
    // ffmpeg.wasm
    // ------------------------------------------------------------------
    function cargarScript(src) {
        return new Promise(function (resolver, rechazar) {
            if (window.FFmpegWASM && window.FFmpegWASM.FFmpeg) {
                resolver();
                return;
            }
            const existente = document.querySelector('script[data-ffmpeg="1"]');
            if (existente) {
                existente.addEventListener("load", resolver);
                existente.addEventListener("error", rechazar);
                return;
            }
            const script = document.createElement("script");
            script.src = src;
            script.dataset.ffmpeg = "1";
            script.async = true;
            script.onload = resolver;
            script.onerror = function () {
                rechazar(new Error("No se pudo descargar el compresor."));
            };
            document.head.appendChild(script);
        });
    }

    async function descargarComoBlobURL(url, tipo) {
        const respuesta = await fetch(url, { mode: "cors" });
        if (!respuesta.ok) {
            throw new Error("No se pudo descargar un componente del compresor.");
        }
        const datos = await respuesta.arrayBuffer();
        return URL.createObjectURL(new Blob([datos], { type: tipo }));
    }

    async function cargarFFmpeg() {
        if (ffmpegInstancia) return ffmpegInstancia;
        if (ffmpegPromesa) return ffmpegPromesa;

        ffmpegPromesa = (async function () {
            mostrarGlobal(
                "info",
                "<strong>Preparando el compresor de video…</strong><br>La primera vez se descargan unos 32 MB. Esto puede tardar un momento."
            );
            await cargarScript(app.dataset.ffmpegScript);
            const Clase = window.FFmpegWASM && window.FFmpegWASM.FFmpeg;
            if (!Clase) throw new Error("ffmpeg.wasm no está disponible.");

            const instancia = new Clase();
            const [coreURL, wasmURL] = await Promise.all([
                descargarComoBlobURL(FFMPEG_CORE + "/ffmpeg-core.js", "text/javascript"),
                descargarComoBlobURL(FFMPEG_CORE + "/ffmpeg-core.wasm", "application/wasm"),
            ]);
            await instancia.load({ coreURL: coreURL, wasmURL: wasmURL });
            ffmpegInstancia = instancia;
            return instancia;
        })().catch(function (error) {
            ffmpegPromesa = null;
            throw error;
        });

        return ffmpegPromesa;
    }

    async function comprimirVideo(ffmpeg, item) {
        const archivo = item.file;
        const entrada = "entrada_" + item.id + extensionSegura(archivo.name);
        const salida = "salida_" + item.id + ".mp4";

        mostrarEstado(item, "Comprimiendo a 720p… 0 %", "trabajo", 4);
        const bytes = new Uint8Array(await archivo.arrayBuffer());
        await ffmpeg.writeFile(entrada, bytes);

        let ultimoPct = -1;
        const alProgresar = function (evento) {
            const pct = Math.max(
                0,
                Math.min(99, Math.round((evento.progress || 0) * 100))
            );
            if (pct !== ultimoPct) {
                ultimoPct = pct;
                mostrarEstado(
                    item,
                    "Comprimiendo a 720p… " + pct + " %",
                    "trabajo",
                    pct
                );
            }
        };

        ffmpeg.on("progress", alProgresar);
        try {
            await ffmpeg.exec(
                [
                    "-i", entrada,
                    "-vf", "scale=-2:720",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-b:v", "1200k",
                    "-maxrate", "1400k",
                    "-bufsize", "2800k",
                    "-r", "30",
                    "-c:a", "aac",
                    "-b:a", "96k",
                    "-movflags", "+faststart",
                    salida,
                ],
                30 * 60 * 1000
            );
            const datos = await ffmpeg.readFile(salida);
            const bytesSalida =
                datos instanceof Uint8Array ? datos : new Uint8Array(datos);
            const blob = new Blob([bytesSalida.buffer], { type: "video/mp4" });
            if (!blob.size) throw new Error("El video comprimido quedó vacío.");
            const nuevoArchivo = new File(
                [blob],
                "vuelo_" + item.id + ".mp4",
                { type: "video/mp4" }
            );
            const eraMasPequeno = nuevoArchivo.size < archivo.size;
            const mensaje = eraMasPequeno
                ? "Comprimido: " +
                  formatearPeso(archivo.size) +
                  " → " +
                  formatearPeso(nuevoArchivo.size)
                : "Video procesado · " + formatearPeso(nuevoArchivo.size);
            mostrarEstado(item, mensaje, "trabajo", 100);
            return nuevoArchivo;
        } finally {
            ffmpeg.off("progress", alProgresar);
            try { await ffmpeg.deleteFile(entrada); } catch (error) { /* ignorar */ }
            try { await ffmpeg.deleteFile(salida); } catch (error) { /* ignorar */ }
        }
    }

    function extensionSegura(nombre) {
        const punto = (nombre || "").lastIndexOf(".");
        if (punto === -1) return ".mp4";
        const extension = nombre.slice(punto).toLowerCase();
        return /^\.[a-z0-9]{2,5}$/.test(extension) ? extension : ".mp4";
    }

    function comprimirEnCola(ffmpeg, item) {
        const tarea = colaCompresion.then(function () {
            return comprimirVideo(ffmpeg, item);
        });
        // La cola no se detiene aunque una compresión individual falle.
        colaCompresion = tarea.catch(function () {});
        return tarea;
    }

    // ------------------------------------------------------------------
    // API Django
    // ------------------------------------------------------------------
    async function obtenerUrls(vueloIds) {
        const respuesta = await fetch(app.dataset.presignedUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrf,
            },
            body: JSON.stringify({ vuelo_ids: vueloIds }),
        });
        let datos = {};
        try { datos = await respuesta.json(); } catch (error) { /* ignorar */ }
        if (!respuesta.ok || !datos.ok) {
            throw new Error(
                datos.error || "No se pudieron preparar las URLs de subida."
            );
        }
        const mapa = new Map();
        datos.vuelos.forEach((entrada) => mapa.set(Number(entrada.vuelo_id), entrada));
        return mapa;
    }

    async function subirAServidor(item, archivo, info) {
        if (info.method === "PUT") {
            const respuesta = await fetch(info.upload_url, {
                method: "PUT",
                headers: { "Content-Type": archivo.type || "video/mp4" },
                body: archivo,
            });
            if (!respuesta.ok) {
                throw new Error(
                    "R2 rechazó la subida (HTTP " + respuesta.status + ")."
                );
            }
            return;
        }

        const formulario = new FormData();
        formulario.append("file", archivo, archivo.name);
        const respuesta = await fetch(info.upload_url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-CSRFToken": csrf },
            body: formulario,
        });
        let datos = {};
        try { datos = await respuesta.json(); } catch (error) { /* ignorar */ }
        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.error || "La subida local falló.");
        }
    }

    async function confirmarEnDjango(item, archivo) {
        const peso = Number((archivo.size / (1024 * 1024)).toFixed(2));
        let ultimoError = "No se pudo confirmar la subida.";
        for (let intento = 0; intento < 5; intento++) {
            const respuesta = await fetch(item.confirmUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf,
                },
                body: JSON.stringify({ peso_mb: peso }),
            });
            let datos = {};
            try { datos = await respuesta.json(); } catch (error) { /* ignorar */ }
            if (respuesta.ok && datos.ok) return datos;
            ultimoError = datos.error || ultimoError;
            if (respuesta.status !== 409) break;
            await dormir(1200 + intento * 900);
        }
        throw new Error(ultimoError);
    }

    async function procesarItem(item, info, usarFFmpeg) {
        let archivo = item.file;
        if (!archivo) return;

        if (usarFFmpeg && archivo.size >= MIN_BYTES_COMPRIMIR) {
            try {
                mostrarEstado(item, "Preparando compresión…", "trabajo", 2);
                const ffmpeg = await cargarFFmpeg();
                const comprimido = await comprimirEnCola(ffmpeg, item);
                if (comprimido.size < archivo.size) {
                    archivo = comprimido;
                } else {
                    mostrarEstado(
                        item,
                        "El original pesa menos; se conserva el archivo original.",
                        "aviso",
                        100
                    );
                }
            } catch (error) {
                console.error("Compresión fallida:", error);
                mostrarEstado(
                    item,
                    "No se pudo comprimir; se subirá el original (" +
                        formatearPeso(archivo.size) + ").",
                    "aviso",
                    100
                );
                await dormir(700);
            }
        }

        mostrarEstado(
            item,
            "Subiendo " + formatearPeso(archivo.size) + "…",
            "trabajo",
            100
        );
        await subirAServidor(item, archivo, info);
        await confirmarEnDjango(item, archivo);

        item.subido = true;
        item.file = null;
        item.input.value = "";
        item.etiqueta.textContent = "Reemplazar video";
        mostrarEstado(
            item,
            "Video subido correctamente · " + formatearPeso(archivo.size),
            "exito",
            100
        );
    }

    async function esperarCupo(activas) {
        while (activas.size >= MAX_PARALELAS) {
            await Promise.race(Array.from(activas));
        }
    }

    // ------------------------------------------------------------------
    // Acción principal
    // ------------------------------------------------------------------
    btnSubir.addEventListener("click", async function () {
        if (ocupado) return;

        const seleccionadas = filas.filter((fila) => fila.file);
        if (!seleccionadas.length) {
            mostrarGlobal(
                "aviso",
                "Selecciona al menos un archivo de video antes de continuar."
            );
            return;
        }

        bloquearInterfaz(true);
        subidosSesion = 0;
        actualizarProgreso(seleccionadas.length);
        const errores = [];
        let compresionDisponible = checkComprimir.checked;

        try {
            mostrarGlobal("info", "Solicitando URLs de subida seguras…");
            const infoPorVuelo = await obtenerUrls(
                seleccionadas.map((fila) => fila.id)
            );

            if (compresionDisponible) {
                try {
                    mostrarEstado(
                        seleccionadas[0],
                        "Cargando compresor…",
                        "trabajo",
                        1
                    );
                    await cargarFFmpeg();
                    ocultarGlobal();
                } catch (error) {
                    console.error(error);
                    compresionDisponible = false;
                    const continuar = window.confirm(
                        "No fue posible cargar el compresor de video (ffmpeg.wasm).\n\n" +
                        "¿Deseas subir los archivos originales sin comprimir?"
                    );
                    if (!continuar) {
                        bloquearInterfaz(false);
                        mostrarGlobal(
                            "aviso",
                            "Subida cancelada. Puedes desmarcar «Comprimir a 720p» para subir los originales."
                        );
                        return;
                    }
                    mostrarGlobal(
                        "aviso",
                        "Se subirán los archivos originales, sin compresión."
                    );
                }
            }

            const activas = new Set();
            for (const item of seleccionadas) {
                const info = infoPorVuelo.get(item.id);
                if (!info) {
                    errores.push("Vuelo #" + item.numero + ": sin URL de subida.");
                    mostrarEstado(item, "No se recibió una URL de subida.", "error", 0);
                    continue;
                }

                await esperarCupo(activas);
                const promesa = (async function () {
                    try {
                        await procesarItem(item, info, compresionDisponible);
                        subidosSesion += 1;
                    } catch (error) {
                        console.error("Subida fallida:", error);
                        errores.push("Vuelo #" + item.numero + ": " + error.message);
                        mostrarEstado(
                            item,
                            error.message || "Error al subir.",
                            "error",
                            100
                        );
                    } finally {
                        actualizarProgreso(seleccionadas.length);
                    }
                })();
                activas.add(promesa);
                promesa.finally(function () {
                    activas.delete(promesa);
                });
            }

            await Promise.all(activas);

            if (errores.length === 0) {
                mostrarGlobal(
                    "exito",
                    "<strong>¡Listo!</strong> Todos los videos se subieron y confirmaron correctamente. " +
                        "Puedes volver al detalle del turno."
                );
                btnSubir.innerHTML =
                    '<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="2.2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5"/></svg> Subida completada';
                btnSubir.classList.remove(
                    "from-cyan-400", "to-teal-400",
                    "hover:from-cyan-300", "hover:to-teal-300"
                );
                btnSubir.classList.add("bg-emerald-400", "text-emerald-950");
            } else {
                mostrarGlobal(
                    "error",
                    "<strong>" + subidosSesion + " de " + seleccionadas.length +
                        "</strong> video(s) se subieron correctamente.<br>" +
                        errores.map(function (e) { return "· " + e; }).join("<br>") +
                        "<br><br>Vuelve a seleccionar los archivos fallidos para reintentar."
                );
                btnSubir.innerHTML =
                    '<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"/></svg> Reintentar subida';
            }
        } catch (error) {
            console.error(error);
            mostrarGlobal(
                "error",
                "<strong>No se pudo iniciar la subida.</strong><br>" +
                    (error.message || "Error inesperado.")
            );
        } finally {
            bloquearInterfaz(false);
        }
    });
})();
