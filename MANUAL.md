# Manual de Procedimientos — Sistema de Webs Automáticas

## ¿Qué hace este sistema?

Cuando un anfitrión llena un formulario de Tally, el sistema:
1. Detecta la ciudad de la propiedad
2. Genera una web personalizada con info local (restaurantes, transporte, clima, etc.)
3. Sube la web a internet automáticamente
4. Envía un email a vos con el link de la web
5. Envía un email al anfitrión pidiéndole el video de check-in por WhatsApp

---

## Flujo completo

```
Anfitrión llena Tally
        ↓
Google Sheets recibe la respuesta
        ↓
Apps Script detecta la nueva fila → avisa a GitHub
        ↓
GitHub Actions corre main.py (genera la web)
        ↓
Web sube a GitHub Pages (sitio público)
        ↓
Email a vos (Pedro) con el link
Email al anfitrión pidiendo el video
```

---

## Archivos importantes

| Archivo | Para qué sirve |
|---|---|
| `main.py` | Motor principal. Lee el Sheet, genera el HTML, manda emails |
| `template_bariloche.html` | Template visual para propiedades en Bariloche |
| `template_generico.html` | Template visual para cualquier otra ciudad |
| `requirements.txt` | Dependencias de Python (no tocar) |
| `.github/workflows/deploy.yml` | Instrucciones para GitHub Actions (no tocar) |

---

## Dónde está cada cosa

**Formulario Tally:** El form que llenan los anfitriones  
**Google Sheets:** `Registro de Nueva Propiedad - Bariloche Experiencias` → pestaña `Sheet1`  
**Apps Script:** Dentro del Sheet → Extensiones → Apps Script  
**GitHub:** `github.com/bariloche-experiences/bariloche-automatizacion`  
**Web generada:** `bariloche-experiences.github.io/bariloche-automatizacion/sites/<nombre-anfitrion>/`

---

## Columnas clave del Sheet (Tally las genera automáticamente)

| Columna | Qué contiene |
|---|---|
| `Email del anfitrion` | Email para enviarle las instrucciones del video |
| `maps_d1` / `maps_d2` | Link de Google Maps de cada propiedad |
| `nombre_d1` / `nombre_d2` | Nombre de cada depto |
| `video_checkin_d1` / `video_checkin_d2` | Link de YouTube del video (**lo cargás vos manualmente**) |
| `wifi_ssid_d1`, `wifi_pass_d1` | Datos del WiFi |
| `instagram_d1` | Instagram del anfitrión |

---

## Cómo agregar el video de check-in

1. Anfitrión te manda el video por WhatsApp
2. Subís el video a YouTube (puede ser "No listado")
3. Abrís el Google Sheet
4. Buscás la fila del anfitrión
5. Pegás el link de YouTube en la columna `video_checkin_d1`
6. Esperás hasta 1 hora (el cron corre cada hora) o entrás a GitHub Actions → **Run workflow** para regenerar al toque

---

## Cómo corre la automatización

**Automático:** Cada vez que alguien llena Tally, el Apps Script lo detecta y lanza la generación en ~30 segundos.

**Manual (para regenerar o testear):**
1. Ir a `github.com/bariloche-experiences/bariloche-automatizacion/actions`
2. Click en **"Generar y desplegar webs"**
3. Click en **"Run workflow"** → **"Run workflow"**

**Cron de seguridad:** Corre automáticamente cada hora aunque nadie llene el form.

---

## Cuánto tarda el workflow

- **Bariloche:** ~30 segundos (contenido hardcodeado)
- **Otras ciudades:** 1-3 minutos (busca lugares con Google Maps API y genera textos con Gemini)

---

## Secrets en GitHub (contraseñas del sistema)

Están guardados en `github.com/bariloche-experiences/bariloche-automatizacion/settings/secrets/actions`. **No los toques** a menos que cambies alguna API key o contraseña.

| Secret | Para qué |
|---|---|
| `GEMINI_API_KEY` | IA para generar textos |
| `GOOGLE_MAPS_API_KEY` | Buscar lugares cercanos y geocodear |
| `GOOGLE_CREDENTIALS_JSON_B64` | Acceso al Google Sheet |
| `SPREADSHEET_ID` | ID del Sheet de Tally |
| `WORKSHEET_NAME` | Nombre de la pestaña (Sheet1) |
| `EMAIL_USER` / `EMAIL_PASS` | Cuenta Gmail para mandar emails |
| `PEDRO_WHATSAPP` | Tu número de WhatsApp (aparece en los emails) |
| `SITE_BASE_URL` | URL base de GitHub Pages |

---

## Qué hacer si algo falla

**El workflow falla (X rojo en GitHub Actions):**
→ Click en el workflow fallido → Click en "build" → leer el error al final del log

**El anfitrión no recibe el email:**
→ Verificar que llenó el campo "Email del anfitrión" en Tally
→ Ver en el log del workflow si dice "Email al anfitrión no enviado"

**La web muestra Bariloche en vez de la ciudad correcta:**
→ El link de Google Maps del anfitrión probablemente es un link corto que no se pudo expandir
→ Solución: pedir al anfitrión el link largo (con @ y coordenadas en la URL)

**El workflow tarda más de 5 minutos:**
→ Es normal con el plan gratuito de Gemini (límite de 20 requests/minuto)
→ Solución definitiva: activar billing en Google AI Studio

---

## Contacto técnico

El sistema fue desarrollado con Claude Code (Anthropic).
Para continuar el desarrollo, abrí una sesión nueva y decí: *"Continuá el desarrollo del sistema de webs automáticas para anfitriones Airbnb"* — Claude tiene el contexto guardado.
