# 🎰 Betsson E2E Game Validation

Sistema automatizado de pruebas End-to-End (E2E) con **Playwright** e **Intercepción de Tráfico de Red HTTP (RGS / API)** para validar juegos de casino en Betsson.

El sistema verifica la correcta apertura de juegos de slots (Pragmatic Play), la ejecución de apuestas, la reconciliación matemática estricta de saldos (`Decimal`), la validación de respuestas del servidor y la detección de posibles fallos de renderizado (pantallas en negro o canvas congelado).

---

## 🏛️ Enfoque y Arquitectura

Debido a que el juego corre dentro de un `<iframe>` de terceros (Pragmatic Play), el DOM interno del juego no es accesible directamente. Para garantizar la compatibilidad con el mayor número de juegos posible y evitar la fragilidad de la visión por computador, el sistema basa su lógica en:

1. **Intercepción de Tráfico de Red (Fuente de Verdad):**  
   Playwright monitoriza e intercepta las peticiones y respuestas HTTP/WebSocket del Remote Gaming Server (RGS) (`src/network/`). Extrae directamente:
   - Importe apostado (`c` * `l` = `bet`)
   - Importe ganado (`w` = `win`)
   - Saldo final tras la jugada (`balance`)
   - Estado de la ronda (`na=s` para rondas completadas)
   
   Esto proporciona una precisión matemática del 100% sin depender de OCR ni visión artificial.

2. **Detección de Pantalla Negra / Fallos de Renderizado:**  
   Para cubrir situaciones donde las peticiones de red responden correctamente pero el usuario ve una pantalla negra o el canvas se queda colgado, el sistema incluye una verificación ligera de salud visual (`src/vision/image_utils.py`) analizando la varianza y luminosidad del canvas del juego para alertar si se produce una "apuesta a ciegas" (*blind betting*).

---

## 📋 Requisitos Previos

- **Python 3.11+** o **Python 3.12+**
- Navegadores de Playwright instalados:
  ```bash
  playwright install firefox chromium
  ```
- Entorno virtual activo con las dependencias instaladas:
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

---

## 🚀 Guía de Ejecución de Tests E2E

Debido a los sistemas de protección antifraude y antibot de Betsson en producción, la automatización del formulario de login es bloqueada. Para ejecutar los tests de forma 100% fiable y sin bloqueos, **se reutiliza la sesión activa del navegador** importando las cookies y el almacenamiento local.

Sigue estos pasos para ejecutar las pruebas:

---

### Paso 1: Iniciar sesión manualmente en el navegador
1. Abre tu navegador habitual (Chrome, Firefox, Brave, etc.).
2. Accede a Betsson e inicia sesión con la cuenta a testear:
   - Para el **Escenario 1** (giro real): usa una cuenta con saldo disponible.
   - Para el **Escenario 2** (fondos insuficientes): usa una cuenta sin saldo.

---

### Paso 2: Exportar Cookies
1. En la pestaña con la sesión activa de Betsson, abre tu extensión de gestión de cookies (por ejemplo, **Cookie-Editor**).
2. Selecciona **Export** → **Export as JSON**.
3. Guarda o pega el archivo con el nombre `cookies.json` en la **raíz del proyecto**.

---

### Paso 3: Exportar el Almacenamiento Web (`sessionStorage` y `localStorage`)
1. En la misma pestaña de Betsson donde estás autenticado, abre las herramientas de desarrollo pulsando `F12` (o `Ctrl + Shift + I`).
2. Ve a la pestaña **Console**.
3. Si el navegador bloquea el pegado de código, escribe en la consola:
   ```text
   allow paste
   ```
   *(o `permitir pegar` según el idioma configurado)* y pulsa `Enter`.
4. Copia y ejecuta en la consola el siguiente comando:
   ```javascript
   copy(JSON.stringify({origin: location.origin, localStorage: {...localStorage}, sessionStorage: {...sessionStorage}}))
   ```
5. Crea un archivo llamado `storage.json` en la **raíz del proyecto** y pega el contenido copiado en el portapapeles.

---

### Paso 4: Importar Cookies y Storage al Proyecto

Ejecuta el script de importación indicando el agente correspondiente (`agent_com_s1` para cuenta con saldo o `agent_com_s2` para cuenta sin saldo):

```bash
# Para el Escenario 1 (cuenta con saldo):
python scripts/import_cookies.py agent_com_s1 cookies.json storage.json

# Para el Escenario 2 (cuenta sin saldo):
python scripts/import_cookies.py agent_com_s2 cookies.json storage.json
```

Verás una confirmación en consola indicando el número de cookies y claves de almacenamiento importadas hacia `artifacts/auth_state/`.

---

### Paso 5: Ejecutar los Tests E2E

Una vez importada la sesión, lanza la ejecución del test:

#### Escenario 1: Giro Real y Reconciliación por Red
Realiza el flujo del juego, efectúa un giro, intercepta las respuestas HTTP del RGS y valida la reconciliación matemática estricta:
```bash
python -m pytest tests/test_scenario_1_spin.py -k com_s1 -o addopts=""
```

#### Escenario 2: Saldo Insuficiente y Rechazo de Apuesta
Verifica que al no tener saldo suficiente el servidor y la interfaz rechazan la apuesta sin deducir fondos:
```bash
python -m pytest tests/test_scenario_2_no_funds.py -k com_s2 -o addopts=""
```

---

### Paso 6: Limpieza de Archivos Temporales (Opcional)
Para evitar mantener credenciales activas en archivos planos una vez terminada la sesión de testing:
```bash
rm cookies.json storage.json
```

---

## 🧪 Ejecución de Tests Unitarios (Offline)

El proyecto incluye tests unitarios para verificar el monitor de red, parseadores y la lógica sin necesidad de abrir el navegador ni consumir saldo:

```bash
# Ejecutar suite unitaria completa
pytest tests/unit/

# Validar monitor de red y parser de Pragmatic Play
pytest tests/unit/test_network_monitor.py tests/unit/test_network_parser.py
```

---

## 📊 Reportes y Evidencias

Tras la ejecución, las evidencias se generan en el directorio `artifacts/`:
- 📸 **`artifacts/<agent_id>/evidence/`**: Capturas de pantalla del estado del juego y encabezado.
- 🎥 **`artifacts/<agent_id>/video/`**: Grabaciones en vídeo `.webm` de la interacción del navegador.
- 🧾 **`artifacts/master_report.json`**: Resumen estructurado del resultado de los checks ejecutados.
