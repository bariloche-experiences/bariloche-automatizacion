# Cómo cargar el video de check-in (5 minutos desde el celular)

Este es **tu** workflow cuando llega un anfitrión nuevo y todavía no tiene el video.

## El flujo completo

```
1. Anfitrión completa Tally (sin video)
   └─→ Sheet recibe la fila
   └─→ Apps Script dispara GitHub Actions
   └─→ Web se genera con placeholder "Video disponible pronto"
   └─→ Email automático al anfitrión con el link de la web

2. Anfitrión te manda el video por WhatsApp

3. VOS hacés esto desde el celular (5 minutos):
   ├─ Bajás el video del WhatsApp (1 toque)
   ├─ Subís a YouTube (3 minutos)
   ├─ Editás el Sheet con el link (1 minuto)
   └─→ Apps Script dispara GitHub Actions de nuevo
   └─→ Web se actualiza con el video real
```

## Paso a paso desde el celular

### A) Bajar el video del WhatsApp
1. Abrí el chat con el anfitrión
2. Tap en el video → flecha de descarga (↓) o tap largo → "Guardar"
3. El video queda en tu galería del celu

### B) Subir a YouTube como "No listado"
1. Abrí la **app oficial de YouTube** (la que ya tenés instalada)
2. Tap en el botón **"+"** (abajo en el centro)
3. Elegí **"Subir un video"**
4. Seleccioná el video de la galería
5. **Título**: poné algo identificable, ej: `Check-in Lake View - María García`
6. **Descripción**: opcional, dejala vacía
7. Tap en "Siguiente"
8. **MUY IMPORTANTE — Visibilidad**: tocá donde dice "Público" y cambialo a **"No listado"**
   - Esto hace que solo se vea con el link directo (no aparece en búsquedas)
9. Tap "**Subir**"
10. Esperá que termine de subir (1-3 min según el tamaño)

### C) Copiar el link
1. Cuando terminó, tap en tu video subido
2. Tap en "Compartir"
3. Tap en "Copiar enlace"

### D) Pegar el link en el Sheet
1. Abrí la app **Google Sheets** en el celu
2. Abrí el Sheet de Bariloche Experiencias
3. Buscá la fila del anfitrión (la última generalmente)
4. Tocá la celda **`video_checkin_d1`** (o `_d2`, `_d3` según el depto)
5. Pegá el link
6. Tocá la palomita verde para confirmar

### E) Listo
- En 30 segundos, Apps Script dispara GitHub Actions
- En 1-2 minutos más, la web del anfitrión se actualiza con el video real
- El placeholder "Video disponible pronto" desaparece
- Si querés podés mandarle un WhatsApp al anfitrión: "¡Listo! Tu web ya tiene el video"

## Si tiene varios deptos

Repetís el proceso para cada uno:
- Video del depto 1 → celda `video_checkin_d1`
- Video del depto 2 → celda `video_checkin_d2`
- Video del depto 3 → celda `video_checkin_d3`
- (hasta 10)

Cada vez que pegás un link, GitHub Actions se dispara y regenera la web. 
**No hace falta hacer nada más.**

## Tips

- **YouTube acepta videos verticales** (filmados con celu en posición normal). 
  Se ven bien en el embed, no te preocupes por la orientación.
- **Tamaño máximo**: 256 GB o 12 horas — más que suficiente.
- **Calidad**: subí lo que mande el anfitrión, YouTube re-comprime solo.
- **Si subiste un video equivocado**: borralo de YouTube, subí el correcto, 
  copiá el link nuevo, reemplazá la celda del Sheet.
- **Si querés cambiar a otro video más adelante**: simplemente reemplazá el link 
  en el Sheet. La web se regenera automáticamente.

## Mi recomendación de organización

Creá una **playlist privada en YouTube** llamada "Bariloche Experiencias" 
y agregá ahí todos los videos a medida que los subís. Así los tenés ordenados 
por si necesitás reusarlos o reemplazarlos.

---

**Tiempo total**: 3-5 minutos por video desde el celular, donde estés.
