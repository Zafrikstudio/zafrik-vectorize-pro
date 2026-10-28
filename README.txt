ZAFRIK VECTORIZE PRO V3 - Render

ARCHIVOS:
- app.py
- requirements.txt
- render.yaml
- templates/index.html

DEPLOY:
1. Sube esta carpeta a un repositorio de GitHub.
2. En Render crea un nuevo Web Service desde ese repositorio.
3. Render puede detectar render.yaml.
4. Si lo configuras manualmente:
   Build Command: pip install -r requirements.txt
   Start Command: gunicorn app:app
5. Usa Python 3.12.

La vectorización usa VTracer en el servidor y genera SVG real.
