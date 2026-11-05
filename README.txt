ZAFRIK STUDIO - VECTORIZE PRO V5.2 (LOW MEMORY)

CAMBIO PRINCIPAL
Esta versión está optimizada para el límite de 512 MB de RAM de Render Free.
- VTracer 0.6.15 se mantiene como motor.
- El tamaño máximo de trazado interno es 1200 px por lado.
- La eliminación automática de fondo usa operaciones Pillow nativas en vez de recorrer todos los píxeles con Python.
- Gunicorn usa un único worker y un único hilo.
- Los PNG se renderizan directamente a disco.
- Los resultados temporales antiguos se limpian automáticamente.

ARCHIVOS
- app.py
- requirements.txt
- Dockerfile
- render.yaml
- templates/index.html

SUBIR A GITHUB
1. Abre https://github.com/Zafrikstudio/zafrik-vectorize-pro
2. Entra a la rama main.
3. Reemplaza app.py, requirements.txt, Dockerfile y render.yaml en la raíz.
4. Reemplaza templates/index.html dentro de la carpeta templates.
5. Confirma con Commit changes.

RENDER
1. Abre el servicio zafrik-vectorize-pro-1.
2. Espera a que termine el despliegue automático.
3. En Events debe aparecer Live.
4. Comprueba:
   https://zafrik-vectorize-pro-1.onrender.com/api/health
5. Debe responder con ok:true, engine:"VTracer", version:"0.6.15" y profile:"low-memory-v5.2".

IMPORTANTE SOBRE TAMAÑOS
La imagen se reduce internamente a un máximo de 1200 px por lado para evitar que Render Free se quede sin RAM.
El SVG conserva la proporción de la imagen procesada y se puede escalar sin pérdida como vector.
Los PNG de 3000, 3600 y 4800 px se generan desde el SVG. Esos tamaños no recuperan detalle raster que no estuviera en la imagen fuente.

PRUEBA RECOMENDADA
Empieza con una imagen de 1000 a 2000 px de lado y activa/desactiva la eliminación de fondo según corresponda.
Si se usa una imagen muy compleja con muchos colores o miles de detalles, el trazado puede seguir necesitando más memoria que el plan gratuito.
