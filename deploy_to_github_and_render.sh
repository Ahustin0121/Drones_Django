#!/bin/bash

# === CONFIGURACIÓN INICIAL ===

# Variables de entorno (puedes modificar estas según tu caso)
REPO_NAME="aerovigia-drones"
BRANCH_NAME="main"
APP_NAME="aerovigia"

# Directorio del proyecto
PROJECT_DIR="/home/Ahus/Escritorio/drones"

# URL de GitHub (ajusta si es necesario)
GITHUB_REPO="https://github.com/ahus-dora/${REPO_NAME}.git"

# Mensaje de confirmación
echo "✅ Iniciando despliegue: ${REPO_NAME} en GitHub y Render..."

# === PASO 1: VERIFICAR QUE EL PROYECTO ESTÉ EN EL DIRECTORIO CORRECTO ===
if [ ! -d "${PROJECT_DIR}" ]; then
  echo "❌ Error: El directorio del proyecto no existe en ${PROJECT_DIR}"
  exit 1
fi

echo "✅ Directorio de proyecto encontrado: ${PROJECT_DIR}"

# === PASO 2: INICIAR SESIÓN EN GITHUB (con token de acceso) ===
# Si no tienes un token, puedes generar uno en: https://github.com/settings/tokens

read -p "👉 Introduce tu token de acceso de GitHub (personal o con permisos de escritura): " GITHUB_TOKEN

if [ -z "${GITHUB_TOKEN}" ]; then
  echo "❌ Error: El token de GitHub no fue proporcionado."
  exit 1
fi

# === PASO 3: SUBIR EL PROYECTO A GITHUB ===

echo "📌 Subiendo el proyecto a GitHub..."

# Si el repositorio ya existe, lo actualizamos
if git ls-remote --exit-code ${GITHUB_REPO} &>/dev/null; then
  echo "✅ El repositorio ya existe. Actualizando..."
  cd "${PROJECT_DIR}"
  git remote set-url origin ${GITHUB_REPO}
  git config --global user.email "ahus@ahus.com"
  git config --global user.name "Ahus Dora"
  git add .
  git commit -m "Deploy: Actualización automática a GitHub (desde script)"
  git push origin ${BRANCH_NAME}
else
  echo "✅ Repositorio nuevo. Creando..."
  cd "${PROJECT_DIR}"
  git init
  git remote add origin ${GITHUB_REPO}
  git config --global user.email "ahus@ahus.com"
  git config --global user.name "Ahus Dora"
  git add .
  git commit -m "Initial commit: Sistema de gestión de drones AeroVigía"
  git push -u origin ${BRANCH_NAME}
fi

echo "✅ Proyecto subido exitosamente a GitHub: ${GITHUB_REPO}"

# === PASO 4: INICIAR SESIÓN EN RENDER (con token de acceso) ===

read -p "👉 Introduce tu token de acceso de Render (en https://render.com/account/settings/api): " RENDER_TOKEN

if [ -z "${RENDER_TOKEN}" ]; then
  echo "❌ Error: El token de Render no fue proporcionado."
  exit 1
fi

# === PASO 5: DESPLEGAR EN RENDER ===

echo "📌 Iniciando despliegue en Render..."

# Usa el CLI de Render (se requiere que esté instalado)
# Si no lo tienes, puedes instalarlo con: curl -fsSL https://render.com/cli/install.sh | sh

# Si el CLI no está disponible, usamos una versión manual
# Verifica que render-cli esté instalado
if ! command -v render &> /dev/null; then
  echo "❌ Error: El CLI de Render no está instalado."
  echo "👉 Instálalo con: curl -fsSL https://render.com/cli/install.sh | sh"
  exit 1
fi

# Configura el proyecto en Render
render apps create "${APP_NAME}" --region us-central-1 --build-command "bash build.sh" --web-command "gunicorn -b 0.0.0.0:8000 app:application" --env-file ".env" --git-repo ${GITHUB_REPO} --branch ${BRANCH_NAME} --token ${RENDER_TOKEN}

# Verifica el estado
render apps list

echo "✅ El sistema se ha subido exitosamente a Render en: https://aerovigia.onrender.com"

# Finalización
echo "🎉 Despliegue completado!"
echo "💡 Accede a la aplicación en: https://aerovigia.onrender.com"
