# Setup del Tally del anfitrión + flujo de uso

## 1. Cómo modificar el Tally del anfitrión

Andá a tu Tally form (tally.so → tu form). Hacé estos cambios:

### Quitar el campo "Links de Recomendados"
1. Tap en el campo "Links de Recomendados (Nombre y Google Maps)"
2. Click en el ícono de la basura (🗑️) o "Delete this question"
3. Guardá / Publish

**¿Por qué quitarlo?** El sistema ahora genera recomendaciones automáticamente
con Google Places (las que vio: Hartwood, Honorio, Sian Ka'an, etc. en Tulum).
No hace falta que el anfitrión las cargue.

### Hacer "Usuario de Instagram" opcional
1. Tap en el campo "Usuario de Instagram de la propiedad"
2. Encontrá el toggle "Required" (o el asterisco rojo *)
3. Apagalo (toggle OFF)
4. Guardá

### Lo que SÍ tiene que pedir el Tally (mínimo)
Estos son los únicos campos obligatorios reales:

- **Nombre de la propiedad** (ej: "Lake View Apt", "Casa Selva")
- **Nombre del anfitrión** (ej: "Pedro Volpacchio")
- **WhatsApp de Contacto** (con +código país, ej: +5491131952798)
- **Cantidad de propiedades** (1 a 10)
- **Dirección** ← LA MÁS IMPORTANTE (con esto se geocodifica todo)
- **Horario Check-in** (ej: 15:00)
- **Horario Check-out** (ej: 11:00)
- **Nombre Wi-Fi**
- **Contraseña Wi-Fi**
- **Email del anfitrión** (donde recibe el link de la web)

### Lo que NO tiene que pedir (porque lo cargás vos después)
- ❌ Video de Check-in (lo cargás vos después con YouTube)
- ❌ Links de Recomendados (Google Places lo hace solo)
- ❌ Usuario de Instagram (opcional, no obligatorio)

---

## 2. Cómo funciona el Sheet (no desaparece nada)

Cada vez que un anfitrión completa el Tally, esa respuesta se guarda como
**una fila** en tu Google Sheet. Esa fila **queda ahí para siempre**.
Vos podés:

- ✅ Verla cuando quieras (desde celu o PC)
- ✅ Editar cualquier celda en cualquier momento
- ✅ Cuando editás, el sistema regenera la web automáticamente

**No hay que buscar nada raro**. Cada anfitrión = una fila. Los anfitriones
viejos quedan en filas viejas, los nuevos se agregan abajo.

---

## 3. Tu workflow cuando llega un anfitrión nuevo

### Paso 1 — Te llega notificación de Tally al mail
"Nueva respuesta en tu Tally form"

### Paso 2 — La web ya se generó automáticamente (no hacés nada)
- En 1 minuto, GitHub Actions corre solo
- Le manda email al anfitrión con el link de su web
- Esa web tiene un placeholder violeta que dice "Video disponible pronto"

### Paso 3 — Le decís al anfitrión por WhatsApp
> "¡Hola! Tu web ya está lista en [link]. Mandame por acá un video corto
> mostrando cómo entrar y dónde estacionar (1-2 minutos), y te lo agrego
> a la web."

### Paso 4 — El anfitrión te manda el video por WhatsApp
Recibís el video.

### Paso 5 — Subís el video desde el celu (3-5 minutos)
1. Bajás el video de WhatsApp (tap en el video → ↓ download)
2. Abrís app de YouTube → botón "+"  → Subir video
3. Elegís el video de la galería
4. **Visibilidad: "No listado"** (importante — solo se ve con link, no es público)
5. Click "Subir"
6. Cuando termina, click en el video → "Compartir" → "Copiar enlace"

### Paso 6 — Pegás el link en el Sheet (1 minuto)
1. Abrís Google Sheets app en el celu
2. Abrís tu Sheet
3. Buscás la fila del anfitrión
4. Tocás la celda **`video_checkin_d1`** → pegás el link
5. (si tiene varios deptos: cargás `_d2`, `_d3`, etc.)

### Paso 7 — Listo, automágico
- En 30 segundos GitHub Actions detecta el cambio (gracias al Apps Script)
- En 1 minuto más la web se regenera con el video real
- Le mandás un WhatsApp al anfitrión: "¡Listo! Ya está el video en tu web"

---

## 4. Resumen visual del flujo

```
Anfitrión completa Tally
        ↓ (automático)
Sheet recibe fila nueva
        ↓ (automático, 30 seg)
GitHub Actions corre
        ↓ (1 min)
Web publicada con placeholder "Video pronto"
Email al anfitrión con link de web

[Mientras tanto... vos]
        ↓
Anfitrión te manda video por WhatsApp
        ↓
Subís a YouTube como "No listado" (3 min)
        ↓
Pegás link en Sheet, celda video_checkin_d1 (1 min)
        ↓ (automático, 30 seg)
GitHub Actions detecta el cambio
        ↓ (1 min)
Web se actualiza con el video real
```

**Tu trabajo total por anfitrión: 5 minutos. El resto es todo automático.**
