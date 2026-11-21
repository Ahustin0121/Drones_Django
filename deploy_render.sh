#!/bin/bash
# 🚀 Script de despliegue automático para AeroVigía en Render
#
# Este script sube el proyecto a Render usando render-cli.
# Requiere que ya estés autenticado con render-cli.
#
# Uso:
#   chmod +x deploy_render.sh
#   ./deploy_render.sh
#
#
# ✅ Requisitos:
# - Tener una cuenta en https://render.com
# - Tener instalado render-cli: https://render.com/docs/cli
# - Estar en el directorio /home/Ahus/Escritorio/drones
# - Tener el archivo render.yaml y .env (con variables de entorno)
#
# 📝 Notas:
# - El script no requiere conexión a internet permanente.
# - El despliegue se realiza automáticamente en el entorno.
# - Una vez listo, el sitio estará disponible en https://aerovigia.onrender.com
#
#
# 🔐 Variables de entorno (debes tenerlas en .env):
# SECRET_KEY=...
# R2_ACCOUNT_ID=...
# R2_ACCESS_KEY_ID=...
# R2_SECRET_ACCESS_KEY=...
# R2_BUCKET_NAME=...
# DATABASE_URL=postgresql://usuario:clave@host:5432/aerovigia
#
# ⚠️ Asegúrate de que el archivo .env esté en el directorio actual.
#
# Ejecución:
#   ./deploy_render.sh

#
# Verifica que estás en el directorio correcto:
if [ ! -d "./gestion" ]; then
  echo "❌ Error: No se encontró el directorio "gestion"."
  echo "👉 Asegúrate de que el proyecto esté en /home/Ahus/Escritorio/drones."
  exit 1
fi

# Verifica que el archivo render.yaml existe
if [ ! -f "render.yaml" ]; then
  echo "❌ Error: No se encontró el archivo render.yaml."
  echo "👉 Asegúrate de que esté en el directorio actual."
  exit 1
fi

# Verifica que el archivo .env existe
if [ ! -f ".env" ]; then
  echo "❌ Error: No se encontró el archivo .env."
  echo "👉 Crea un archivo .env copiando .env.example y completando los valores."
  exit 1
fi

# Verifica que el archivo requirements.txt existe
if [ ! -f "requirements.txt" ]; then
  echo "❌ Error: No se encontró requirements.txt."
  echo "👉 Asegúrate de que esté en el directorio actual."
  exit  1
fi

# Mensaje de inicio
echo "✅ Iniciando despliegue en Render..."
echo "➡️ El proyecto se subirá en el entorno "aerovigia"."

# Autenticación (requiere que ya estés logueado)
if ! render auth status > /dev/null 2>&1; then
  echo "❌ No estás autenticado con render-cli."
  echo "👉 Inicia sesión con: render login"
  exit 1
fi

# Sube el proyecto
if render deploy --app aerovigia --path .; then
  echo "✅ Despliegue exitoso!"
  echo "👉 El sitio está disponible en: https://aerovigia.onrender.com"
  echo "👉 Puedes ver el estado en: https://render.com/apps/aerovigia"
else
  echo "❌ Error al desplegar. Revisa los logs en render-cli."
  exit 1
fi

# Mensaje final
echo "🎉 El sistema AeroVigía está listo para producción!"
echo "📌 Accede con: admin / admin123"