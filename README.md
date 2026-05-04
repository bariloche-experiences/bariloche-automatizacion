# Bariloche Experiencias · Generador agnóstico de ciudad

Sistema que toma la **dirección** que carga un anfitrión en Tally y genera una
web personalizada con:

- Geocoding → ciudad + barrio reales
- Lugares cercanos por categoría (Google Places)
- Welcome message + tip local + descripciones (Gemini)
- Clima en tiempo real (Open-Meteo, sin API key)
- WiFi con QR
- Recomendaciones del propio anfitrión
- Multi-idioma (ES / EN / PT)

Funciona igual para Bariloche, San Isidro, Mar del Plata o cualquier ciudad.

```
Tally → Google Sheet → main.py (Geocoding+Places+Gemini) → Jinja2 → sites/<anfitrion>/index.html
                                                                          ↓
                                                              GitHub Pages + Email
```

## Estructura

```
bx/
├── main.py                       # generador
├── template_maestro.html         # template Jinja2 (NO modificar diseño)
├── requirements.txt
├── .github/workflows/deploy.yml  # CI: corre main.py y publica
├── sites/                        # output (carpeta por anfitrión)
├── .env.example
└── .gitignore
```

## Schema del Google Sheet

**Globales** (una vez por fila/anfitrión):

| columna                | descripción                                  |
| ---------------------- | -------------------------------------------- |
| `nombre_anfitrion`     | "Pedro Volpacchio"                           |
| `email_dueno`          | a dónde llega la notificación                |
| `whatsapp_contacto`    | con + país (ej `+5491131952798`)             |
| `cantidad_propiedades` | 1–10                                         |
| `checkin`              | `15:00` (default si no está)                 |
| `checkout`             | `11:00` (default)                            |

**Por propiedad** (replicar para `_d1`, `_d2`, … hasta `_d10`):

| columna                  | obligatorio | descripción                                    |
| ------------------------ | ----------- | ---------------------------------------------- |
| `nombre_propiedad_dN`    | sí          | activa la propiedad si está presente           |
| `direccion_dN`           | sí          | la magia depende de esto                       |
| `video_checkin_dN`       | no          | YouTube / Drive / Google Photos                |
| `wifi_ssid_dN`           | no          |                                                |
| `wifi_pass_dN`           | no          |                                                |
| `usuario_instagram_dN`   | no          | sin `@`                                        |
| `recomendaciones_dN`     | no          | text-area: una recomendación por línea         |
| `maps_link_dN`           | no          | si no, se arma desde la dirección              |

**Formato de `recomendaciones_dN`** — texto libre, una línea por lugar. El parser
acepta cualquiera de estos formatos:

```
Heladería Bianchi https://maps.google.com/?cid=12345
Panadería La Argentina  -  https://goo.gl/maps/abc
La Pasiva
```

(Se extrae el URL con regex; el resto es el nombre.)

## APIs habilitadas en Google Cloud

Para la service account que vas a compartir con el Sheet:

- Google Sheets API
- Google Drive API
- **Geocoding API**
- **Places API (New o Legacy, indistinto)**

Nota: la API key de Maps puede ser distinta a las credenciales de la service
account. La service account es solo para leer el Sheet; Maps y Gemini usan API
keys.

## Setup en GitHub

1. **Habilitar Pages**: *Settings → Pages → Source: GitHub Actions*

2. **Secrets** (en *Settings → Secrets and variables → Actions*):

   | Secret                     | Contenido                                              |
   | -------------------------- | ------------------------------------------------------ |
   | `GOOGLE_CREDENTIALS_JSON`  | Pegá el contenido **completo** de `credentials.json`   |
   | `SHEET_ID`                 | El ID entre `/d/` y `/edit` de la URL del Sheet        |
   | `WORKSHEET_NAME`           | `Sheet1` (o el nombre real de la hoja)                 |
   | `GOOGLE_MAPS_API_KEY`      | API key de Google Maps Platform                         |
   | `GEMINI_API_KEY`           | API key de Google AI Studio (gemini.google.com)         |
   | `EMAIL_USER`               | tu cuenta de Gmail                                      |
   | `EMAIL_PASS`               | App Password de Gmail (16 caracteres, sin espacios)     |
   | `GITHUB_PAGES_BASE`        | `https://<usuario>.github.io/<repo>` (sin `/` final)    |
   | `PEDRO_WHATSAPP`           | Tu número de WhatsApp con +código país (ej `+5491131952798`) |

3. **Compartir el Sheet** con el `client_email` de la service account
   (lo encontrás dentro del JSON de credenciales). Permiso: solo lectura.

4. **App Password de Gmail**:
   - Activá 2FA en la cuenta.
   - *Google Account → Security → App passwords → Mail → Generate*.
   - Pegá los 16 caracteres en el secret `EMAIL_PASS`.

## Trigger desde Tally

Lo más limpio: webhook post-submit que dispare el workflow.

**Opción A — GitHub repository_dispatch directo** (si Tally permite headers):

```
POST https://api.github.com/repos/<usuario>/<repo>/dispatches
Authorization: token <PAT con scope repo>
Accept: application/vnd.github+json
Body: { "event_type": "nueva_propiedad" }
```

**Opción B — Apps Script en el Sheet** (más fácil):

```javascript
function onChange(e){
  if (e.changeType !== 'INSERT_ROW') return;
  UrlFetchApp.fetch('https://api.github.com/repos/USUARIO/REPO/dispatches', {
    method: 'post',
    headers: {Authorization: 'token PAT_AQUI', Accept: 'application/vnd.github+json'},
    payload: JSON.stringify({event_type: 'nueva_propiedad'}),
    contentType: 'application/json'
  });
}
```

Trigger: *Extensions → Apps Script → Triggers → onChange*.

Independientemente, el cron horario funciona como red de seguridad.

## Test local

```bash
pip install -r requirements.txt
cp .env.example .env  # completar
export $(cat .env | xargs)
python main.py
# Output: sites/<slug-anfitrion>/index.html
```

## Diferencias con la web original

El template usa el **mismo CSS** y la misma estructura visual de la web original
(dashboard mobile-first oscuro, tabs por idioma/depto, weather card, mapa,
QR de WiFi, sección de lugares con tabs).

**Comportamiento por ciudad:**

- ✅ **Si `ciudad ∈ {bariloche, san carlos de bariloche}`** se inyectan automáticamente:
  Juani Rent A Car (con WhatsApp pre-armado), Airbnb Experience 6936309 (Gemas
  ocultas de la Patagonia) y la card de Cerro Catedral.
- ✅ **Para cualquier otra ciudad** (San Isidro, Mar del Plata, etc.): no aparecen
  esas promos. La web se enfoca 100% en la zona del anfitrión.

**Secciones generadas dinámicamente por la zona:**

- 🆘 **Esenciales** — farmacia, cajero, hospital y estación de servicio más
  cercanos (Places API con `rank_by=distance`).
- 👗 **Outfit recommendations** — Gemini genera 4 actividades **típicas de la
  zona** (no fijas "lago/montaña/ski"). Cada una con outfit adaptado a frío,
  templado, cálido y un tip local.
- 🧠 **Tips locales** — 4 tips concretos generados por Gemini específicos para
  la ciudad (transporte, costumbres, horarios, gastronomía).
- 🗺️ **Lugares por categoría** — atracciones, restaurantes, cafés, cervecerías,
  salir, supermercados, panaderías. Ordenados por rating × log(reseñas) y con
  descripciones generadas por Gemini en ES/EN/PT.
- 💬 **Welcome contextual** — Gemini ya no inventa, recibe los lugares cercanos
  reales y menciona UNO concreto: "El Museo Pueyrredón a la vuelta" en lugar
  de "En el corazón del barrio".

## Sobre los videos de check-in

El sistema acepta **YouTube**, **Google Drive** y **Google Photos**:

- ✅ **YouTube** (recomendado) — embebe perfecto, sin límites de tamaño. Subilo
  como **No listado** si no querés que sea público. Acepta links normales,
  `youtu.be` y Shorts.
- ✅ **Google Drive** — embebe vía iframe `/preview`. El archivo tiene que estar
  compartido con "Cualquier persona con el enlace".
- ⚠️ **Google Photos** — Photos NO permite embeds (bloqueado por Google con
  X-Frame-Options). El sistema muestra un placeholder grande con botón
  "▶️ Reproducir video" que abre el video en una pestaña aparte. Funciona,
  pero **YouTube Unlisted da mejor experiencia.**
