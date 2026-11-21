## 🚀 AeroVigía - Sistema de Gestión de Drones

### 📝 Resumen
Sistema completo de gestión de drones con Django 5.2.19, PostgreSQL, Tailwind CSS y Cloudflare R2. Funciona localmente y está listo para desplegar en Render.

### 🔧 Cómo usar

#### ✅ Local (desarrollo)
1. Abre el proyecto en `/home/Ahus/Escritorio/drones`.
2. Crea un archivo `.env` copiando `.env.example` y completando los valores.
3. Ejecuta:
   ```bash
   .venv/bin/python manage.py runserver
   ```
4. Accede a `http://127.0.0.1:8000`.

#### 🚀 Render (producción)
1. Sube el proyecto a Render usando el archivo `render.yaml`.
2. Asegúrate de que las variables de entorno estén definidas:
   - `SECRET_KEY`
   - `DATABASE_URL` (automáticamente asignado por Render)
   - `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
3. El sistema se desplegará automáticamente con:
   - Gunicorn
   - Base de datos PostgreSQL
   - Cloudflare R2 para almacenamiento de videos
   - Retención de 60 días

### 🔐 Credenciales demo
- `admin / admin123`
- `pepito.rivas / operador123`
- `camila.soto` y `diego.fuentes` (con contraseña `operador123`)

### 📂 Estructura clave
- `requirements.txt` → Dependencias
- `.env.example` → Variables de entorno
- `build.sh` → Script de construcción
- `Procfile` → Configuración de gunicorn
- `render.yaml` → Configuración para Render
- `gestion/` → Código principal
- `static/` → CSS, JS, videos
- `media/` → Videos (local o R2)

### 📝 Funcionalidades
- Flujo de operador: abrir turno, registrar vuelos, cerrar turno.
- Subida de videos: comprimidos en el navegador a 720p H.264.
- Bitácora mensual: filtrada por condominio, operador y marca de drone.
- Retención de 60 días en R2; videos locales se limpian automáticamente.

### 🚨 Limitaciones
- Solo se puede usar R2 en producción (no en desarrollo).
- No hay soporte para múltiples usuarios simultáneos.
- Los videos se almacenan como URLs, no como datos en la base de datos.

### 📎 Cómo desplegar en Render
1. Sube el proyecto a Render.
2. Asegúrate de que `render.yaml` esté correctamente configurado.
3. Configura las variables de entorno en la interfaz de Render.
4. El sistema se ejecutará automáticamente.

👉 **¡Listo para producción!**