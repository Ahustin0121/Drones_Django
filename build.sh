#!/usr/bin/env bash
# Script de construcción para Render.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate --noinput

# Los datos de demostración solo se cargan si se solicita explícitamente.
if [ "${SEED_DEMO:-False}" = "True" ]; then
    python manage.py seed_demo
fi
