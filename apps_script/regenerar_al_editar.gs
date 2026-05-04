/**
 * Apps Script para Bariloche Experiencias
 * 
 * Detecta cuando se inserta o edita una fila en el Sheet y dispara
 * GitHub Actions automáticamente para regenerar la web del anfitrión.
 * 
 * SETUP (una sola vez):
 * 1. Abrí el Google Sheet conectado a Tally
 * 2. Menú: Extensiones → Apps Script
 * 3. Borrá el código que esté ahí
 * 4. Pegá ESTE código completo
 * 5. Editá las DOS constantes de abajo (GITHUB_USUARIO, GITHUB_REPO, GITHUB_PAT)
 * 6. Guardá (💾 o Ctrl+S)
 * 7. Tab izquierdo → "Activadores" (reloj) → "+ Agregar activador"
 *    - Función: onChangeSheet
 *    - Implementación: Cabecera
 *    - Origen del evento: Desde una hoja de cálculo
 *    - Tipo: Al cambiar
 *    - Guardar (te va a pedir permisos, aceptá)
 * 8. Listo. Cada vez que un anfitrión completa Tally O vos editás
 *    una celda, en 30 segundos se regenera la web.
 */

// ⚠️ EDITAR ESTOS 3 VALORES ⚠️
const GITHUB_USUARIO = 'TU_USUARIO_DE_GITHUB';      // ej: 'pedrovolpa'
const GITHUB_REPO    = 'bariloche-experiences';      // nombre exacto del repo
const GITHUB_PAT     = 'ghp_xxxxxxxxxxxxxxxx';       // ver instrucciones abajo

/**
 * Cómo generar el GITHUB_PAT (Personal Access Token):
 * 1. github.com → tu foto arriba a la derecha → Settings
 * 2. Scroll abajo → Developer settings (último ítem)
 * 3. Personal access tokens → Tokens (classic) → Generate new token (classic)
 * 4. Note: "Bariloche Experiencias Sheet trigger"
 * 5. Expiration: No expiration (o 1 año, lo que prefieras)
 * 6. Scopes: tildá SOLO 'repo' (todo el grupo)
 * 7. Generate token → COPIALO (solo se ve una vez) y pegalo arriba en GITHUB_PAT
 */

function onChangeSheet(e) {
  // Solo dispara para inserciones de fila o ediciones (no para borrados)
  if (e && e.changeType && !['INSERT_ROW', 'EDIT', 'OTHER'].includes(e.changeType)) {
    console.log('Cambio ignorado:', e.changeType);
    return;
  }

  const url = `https://api.github.com/repos/${GITHUB_USUARIO}/${GITHUB_REPO}/dispatches`;
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'Authorization': 'token ' + GITHUB_PAT,
      'Accept': 'application/vnd.github+json'
    },
    payload: JSON.stringify({
      event_type: 'nueva_propiedad',
      client_payload: {
        change_type: e ? e.changeType : 'manual',
        timestamp: new Date().toISOString()
      }
    }),
    muteHttpExceptions: true
  };

  const response = UrlFetchApp.fetch(url, options);
  const code = response.getResponseCode();
  if (code === 204) {
    console.log('✓ GitHub Actions disparado correctamente');
  } else {
    console.error('✗ Error disparando GitHub Actions:', code, response.getContentText());
  }
}

/**
 * Función de testing manual: corré esta una vez después del setup
 * para verificar que GitHub Actions reciba el trigger correctamente.
 * 
 * Cómo: arriba selector de funciones → "testManualTrigger" → ▶ Ejecutar.
 * Andá a github.com/TU_USUARIO/bariloche-experiences/actions y debería
 * aparecer un workflow corriendo en 5-10 segundos.
 */
function testManualTrigger() {
  onChangeSheet({ changeType: 'EDIT' });
}
