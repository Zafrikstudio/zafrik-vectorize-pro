ZAFRIK STUDIO - VECTORIZE PRO V5.1

ARCHIVOS
- app.py: servidor Flask, VTracer y eliminación automática del fondo.
- requirements.txt: dependencias Python, incluido VTracer.
- Dockerfile: imagen para Render.
- render.yaml: configuración del servicio Docker.
- templates/index.html: interfaz web.

SUBIR A GITHUB
1. Abre https://github.com/Zafrikstudio/zafrik-vectorize-pro
2. Entra al repositorio y selecciona Add file > Upload files.
3. Sube app.py, requirements.txt, Dockerfile y render.yaml a la raíz.
4. Sube index.html dentro de la carpeta templates (conserva esa ruta).
5. Confirma con Commit changes en la rama main.

RENDER
El repositorio ya contiene render.yaml para un servicio Docker.
Después del commit, abre el servicio en Render y revisa Events/Logs.
Si Render no inicia un despliegue automático, usa Manual Deploy > Deploy latest commit.
No agregues Build Command ni Start Command personalizados: el Dockerfile ya los define.

PRUEBA
Abre:
https://zafrik-vectorize-pro-1.onrender.com/api/health
Debe devolver JSON con ok:true y engine:"VTracer".

NOTAS
- El backend procesa la imagen en el servidor de Render.
- El tamaño de entrada se limita a 25 MB y el lado mayor se reduce como máximo a 1800 px.
- El SVG contiene trazados vectoriales; no convierte letras en texto tipográfico editable.
- El modo poligonal favorece esquinas y líneas rectas, pero la vectorización es una aproximación.


NOVEDAD V5.1
- Eliminación automática del color predominante detectado en los bordes.
- Control de tolerancia para fondos de distintos colores.
- Opción para activar/desactivar la eliminación automática.
- La detección global también hace transparentes los huecos interiores
  que tengan el mismo color que el fondo detectado.
- Para mejores resultados, utiliza un fondo uniforme y evita que el diseño
  toque los bordes de la imagen.
