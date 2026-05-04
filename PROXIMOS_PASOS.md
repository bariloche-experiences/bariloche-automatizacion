# PRÓXIMOS PASOS — Pedro

Esta es tu guía personal para terminar de poner el sistema en producción.
Léelo en orden, no saltees pasos.

## 1️⃣ Recuperar los secrets de GitHub

Antes de cualquier cosa, asegurate de que estos 9 secrets están cargados en
**github.com/USUARIO/REPO → Settings → Secrets and variables → Actions**:

```
✓ GOOGLE_CREDENTIALS_JSON     (contenido completo del credentials.json)
✓ SHEET_ID                    (ID del Google Sheet)
✓ WORKSHEET_NAME              (Sheet1 o el nombre que tenga)
✓ GOOGLE_MAPS_API_KEY         (de Google Cloud Console)
✓ GEMINI_API_KEY              (de Google AI Studio)
✓ EMAIL_USER                  (tu Gmail)
✓ EMAIL_PASS                  (App Password de Gmail, 16 caracteres)
✓ GITHUB_PAGES_BASE           (https://USUARIO.github.io/REPO)
✓ PEDRO_WHATSAPP              (+5491131952798)
```

**Si te faltan algunos**, así los recuperás:

| Secret | Dónde encontrarlo |
|---|---|
| `GOOGLE_CREDENTIALS_JSON` | Google Cloud Console → IAM → Service Accounts → tu cuenta → Keys → "Add Key" → JSON. Descargás el archivo y pegás todo el contenido como secret. |
| `SHEET_ID` | URL del Sheet: `docs.google.com/spreadsheets/d/[ESTO_ES_EL_ID]/edit` |
| `WORKSHEET_NAME` | El nombre de la pestaña del Sheet (abajo). Generalmente `Sheet1` u `Hoja 1`. |
| `GOOGLE_MAPS_API_KEY` | Google Cloud Console → APIs & Services → Credentials. Si no la ves, podés generarla nueva ("Create Credentials" → "API Key"). |
| `GEMINI_API_KEY` | aistudio.google.com → "Get API key" → "Create API key". Es gratis. |
| `EMAIL_USER` | Tu mail de Gmail completo. |
| `EMAIL_PASS` | gmail.com → cuenta → seguridad → 2FA → App Passwords → "Mail" → generar. Son 16 caracteres sin espacios. |
| `GITHUB_PAGES_BASE` | `https://TU_USUARIO.github.io/NOMBRE_REPO` (sin `/` al final) |
| `PEDRO_WHATSAPP` | `+5491131952798` |

---

## 2️⃣ Bajar el ZIP nuevo y descomprimir

Ya descargaste `bariloche-experiencias.zip` a `~/Downloads/`.

Si todavía no lo descomprimiste, doble-click en el ZIP en Finder, o desde
terminal:

```bash
cd ~/Downloads
unzip -o bariloche-experiencias.zip
```

---

## 3️⃣ Abrir Claude Code y pegarle este prompt

Abrí Claude Code en tu Mac y pegale el prompt que está al final de este archivo.

Te va a guiar paso a paso para reemplazar archivos, testear local, pushear a
GitHub, y configurar el Apps Script para regeneración automática.

**Tiempo estimado:** 30-45 minutos si todo va bien.

---

## 4️⃣ Después del deploy: configurar Tally

En tu Tally form (tally.so):

- ❌ **Borrar el campo** "Links de Recomendados" (ya no se usa, Places API
  encuentra los lugares solos).
- ❌ **Borrar el campo** del video o dejarlo, pero en cualquier caso vos lo
  cargás manual después.
- ⚪ **Sacar "Required"** del campo "Usuario de Instagram" (es opcional).

Lo demás dejalo como está.

---

## 5️⃣ Tu workflow día a día (cuando llegue un anfitrión nuevo)

```
1. Anfitrión completa Tally
   ↓ (automático)
2. Sheet recibe la fila → Apps Script trigger
   ↓ (automático, 1 minuto)
3. Web publicada con placeholder "Video disponible pronto"
4. Email automático al anfitrión con:
   - Link de la web
   - Tu WhatsApp clickeable
   - Instrucciones de los 5 pasos del video
   ↓
5. El anfitrión te manda video por WhatsApp
   ↓ (vos, 5 minutos desde el celu)
6. Bajás video del WhatsApp
7. Subís a YouTube como "No listado"
8. Pegás link en Sheet, celda video_checkin_d1
   ↓ (automático, 1 minuto)
9. Web actualizada con video real
```

Ver detalles en `COMO_USAR_EL_SISTEMA.md` y `COMO_CARGAR_VIDEO.md`.

---

# 🤖 PROMPT PARA CLAUDE CODE

Copiá todo lo que está abajo del separator y pegalo en Claude Code:

---

Hola! Soy Pedro. Tengo un proyecto de generación automática de webs para
anfitriones de Airbnb que está casi terminado. Necesito que me ayudes con el
deploy final. Trabajá en modo extendido (deep thinking), pensá antes de
actuar, y consultame si encontrás algo crítico.

**Contexto:** sistema que recibe respuestas de un Tally form (vía Google Sheet),
geocodifica la dirección, y publica una web personalizada en GitHub Pages. Tiene
dos modos: si la ciudad es Bariloche usa template con mi contenido propio
(Cervecería Patagonia, Refugio Frey, Juani Rent, Cerro Catedral); cualquier otra
ciudad usa template genérico data-driven con Places API + Gemini AI.

**TAREAS EN ORDEN. Si algo falla, parar y reportarme.**

---

**PASO 1 — Encontrar el repo y el ZIP**

1. Buscá en `~/Documents/`, `~/`, y `~/Desktop/` la carpeta del repo
   (probablemente `bariloche-experiences` o similar).
2. Buscá `bariloche-experiencias.zip` y/o la carpeta descomprimida en
   `~/Downloads/`.
3. Si el ZIP no está descomprimido:
   ```bash
   cd ~/Downloads && unzip -o bariloche-experiencias.zip
   ```
4. Confirmame los dos paths antes de seguir.

---

**PASO 2 — Backup del repo actual**

```bash
cd <ruta-del-repo>
cp main.py main.py.backup 2>/dev/null
cp template_maestro.html template_maestro.html.backup 2>/dev/null
```

---

**PASO 3 — Reemplazar archivos del repo**

Copiá estos desde `~/Downloads/bariloche-experiencias/`:

```
main.py
template_bariloche.html       (nuevo)
template_generico.html        (nuevo)
requirements.txt
test_local.py                 (nuevo)
README.md
.github/workflows/deploy.yml
.env.example
.gitignore
apps_script/regenerar_al_editar.gs    (carpeta + archivo nuevos)
COMO_CARGAR_VIDEO.md          (nuevo)
COMO_USAR_EL_SISTEMA.md       (nuevo)
PROXIMOS_PASOS.md             (nuevo)
```

**Si en el repo viejo existe `template_maestro.html`, BORRALO.**

Mostrame `git status` después.

---

**PASO 4 — Verificar configuración local**

1. ¿Existe `.env` en el repo?
   - Si no: copiá `.env.example` a `.env` y pedime las API keys.
   - Si sí: chequeá que tenga `PEDRO_WHATSAPP=+5491131952798`. Si no, agregalo.

2. ¿Existe `credentials.json` en la raíz? Si no, pedímelo.

3. Confirmá que `.env` y `credentials.json` están en `.gitignore`.

4. Instalá deps: `pip install -r requirements.txt` (si tira error de permisos:
   `pip install --user -r requirements.txt`).

---

**PASO 4.5 — Recordatorio: secret PEDRO_WHATSAPP en GitHub**

Recordame que tengo que ir a `github.com/USUARIO/REPO/settings/secrets/actions`
y agregar/verificar el secret:
- Nombre: `PEDRO_WHATSAPP`
- Valor: `+5491131952798`

---

**PASO 5 — Test local con tres direcciones reales**

Corré uno por uno y mostrame el output completo:

```bash
python test_local.py "Av. Bustillo 5000, Bariloche"
python test_local.py "Av. Colón 1500, Mar del Plata"
python test_local.py "Calle Centauro Sur 12, Tulum, Mexico"
```

Después de cada uno: `open sites/test/index.html` y validá visualmente:

**Bariloche**: aparece Cerro Catedral, Juani Rent, Cervecería Patagonia, Refugio
Frey. Welcome dice algo de Bustillo (no de "La Florida 3566"). Placeholder
violeta "Video disponible pronto".

**Mar del Plata**: theme playa, sección "🍽️ Comer, beber, comprar" con pestañas
Restaurantes/Cervecerías/Cafés/Salir/Panaderías/Supermercados. Tab Autos con
alquileres reales y teléfonos. NO hay nada de Bariloche.

**Tulum**: similar pero con info México (Pemex, MXN, 911).

Mostrame especialmente: qué cervecerías y restaurantes encontró Places, qué dijo
Gemini sobre transporte público de cada ciudad, si alguna categoría salió vacía.

---

**PASO 6 — Si algo falla, parar y reportarme**

NO pushees a GitHub si los tests locales no pasan.

---

**PASO 7 — Solo si los 3 tests pasaron, push**

Mostrame `git diff --stat`. Esperá mi confirmación antes de pushear:

```bash
git add -A
git commit -m "Sistema final: dual templates + placeholder video + Apps Script + email rico con WhatsApp"
git push
```

---

**PASO 8 — Verificar GitHub Actions**

Esperá 2-3 minutos y abrí:
```bash
open https://github.com/USUARIO/REPO/actions
```

Decime el status del último workflow run.

---

**PASO 9 — Configurar Apps Script (vos guiás, yo ejecuto en navegador)**

Mostrame el contenido de `apps_script/regenerar_al_editar.gs` y guiame paso a
paso para:
1. Pegar el código en el editor de Apps Script del Sheet
2. Editar las 3 constantes
3. Generar el GitHub PAT
4. Configurar el trigger "On change"
5. Correr `testManualTrigger()` para validar

---

**PASO 10 — Test end-to-end real**

1. Cargo una propiedad de prueba en Tally
2. Espero 1-2 minutos
3. Verifico email recibido con WhatsApp clickeable + 5 pasos del video
4. Abro la web → debería tener placeholder violeta del video
5. Pego un link de YouTube de prueba en `video_checkin_d1` del Sheet
6. Espero 1-2 minutos
7. Refresco la web → placeholder reemplazado por video real

---

**PASO 11 — Limpieza**

```bash
rm main.py.backup template_maestro.html.backup 2>/dev/null
```

---

**REGLAS:**

- Trabajá en modo extendido
- Si una API key falla, NO inventes valores — pedímela
- Si encontrás algo distinto al plan, parame y consultame
- Tiempo estimado: 30-45 minutos
