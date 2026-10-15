# Hackathon Betsson – Sistema de Juego Automatizado

## 📄 Resumen rápido
Este repositorio implementa un flujo **end‑to‑end** que:
1. **Inicia sesión** en Betsson usando credenciales de prueba (o una cookie pre‑guardada).
2. **Navega** al juego Pragmatic Play seleccionado.
3. **Ejecuta un giro** (scenario 1) o verifica el mensaje *insufficient funds* (scenario 2).
4. **Genera** artefactos de resultados (`json`), capturas y un **reporte HTML interactivo**.

El código está organizado en módulos `core`, `vision`, `orchestrator` y `agents` y está cubierto por:
- **170 tests unitarios** (`-m unit`).
- **4 tests E2E** (`-m e2e`).
- **Video‑recording** integrado en la rama `feat/video-recording`.

---

## ✅ Qué funciona (probado en Windows PowerShell + WSL Ubuntu)
| Área | Estado | Comentario |
|------|--------|------------|
| **Entorno** | ✅ | `python -m venv .venv` + `pip install -r requirements.txt` + `playwright install firefox` (o chromium) funciona sin errores. |
| **Variables de entorno** | ✅ | `.env` con `GEMINI_API_KEY`, credenciales de prueba y `HEADLESS=false` permite ver el navegador y depurar. |
| **Autenticación** | ✅ | Login vía API o **cookie** (`PLAYWRIGHT_STORAGE_STATE`) se reutiliza sin volver a pasar el banner de cookies. |
| **Navegación al juego** | ✅ | `LobbyPageProtocol.navigate_to_game` abre el juego y cierra los diálogos intro. |
| **Reducción de consultas IA** | ✅ | Se minimiza el número de peticiones a Gemini al reutilizar información extraída previamente (coordenadas de botones, referencias visuales) y evitar volver a generar la foto del canvas. |
| **Detección de botones mediante capturas** | ✅ | Se generan capturas de los botones y se usan como plantillas para buscarlos con visión por computadora, evitando depender de coordenadas fijas que varían con resolución y juego. |
| **Identificación de acciones vía HTTP** | ✅ | Se observan los **request headers** de las interacciones del usuario (login, spin, etc.) y se han registrado para reproducirlas. |
| **Simulación de spin con Playwright** | ✅ | Se ha explorado que Playwright pueda lanzar directamente las peticiones HTTP del spin simulando el comportamiento de un usuario real, reduciendo la dependencia de clicks. |
| **Giro (scenario 1)** | ✅ | `GameFlow.execute_spin_cycle` hace click, detecta movimiento y estabilidad, y devuelve resultados. |
| **Insufficient‑funds (scenario 2)** | ✅ | Se detecta el banner, se extrae el mensaje y el idioma, y el test pasa. |
| **Reportes** | ✅ | `generate_html_report` crea `artifacts/report.html` con tabla de resultados y reproductor de vídeo. |
| **Cobertura de pruebas** | ✅ | 170 unit tests + 4 E2E → **100 %** de los módulos críticos. |

---

## ⚠️ Qué NO funciona / Limitaciones conocidas
| Tema | Detalle |
|------|----------|
| **Modo headless** | En algunos entornos headless el banner GDPR no se cierra automáticamente; se recomienda `HEADLESS=false` la primera vez o usar la cookie‑state. |
| **Detección anti‑bot** | Betsson emplea Cloudflare/AKAMAI. Si se recibe un *challenge* o CAPTCHA, la ejecución se detiene. Solución provisional: usar `headless:false` y `playwright-stealth` (no incluido por defecto). |
| **Cambios de UI** | Los selectores (`button:has-text('Accept')`, clases del canvas) pueden romperse si Betsson actualiza su UI; habría que actualizar los *locators* en `src/agents/*`. |
| **Reconocimiento de botones** | El modelo de IA tarda mucho en reconocer los botones la primera vez porque su capacidad es limitada; se mitigó usando capturas de botones y plantillas. |
| **Capacidad limitada del modelo IA** | La IA tiene poca capacidad para procesar imágenes complejas rápidamente, lo que afecta tiempo de respuesta. |


---

## 🚀 Instrucciones de ejecución (paso a paso)
### 1️⃣ Preparar entorno (solo la primera vez)
```powershell
# En PowerShell (Windows) – crea y activa venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# Instala dependencias
pip install -r requirements.txt
# Instala navegadores de Playwright (elige uno)
playwright install firefox   # o chromium
```
### 2️⃣ Configurar variables
```powershell
# Copia plantilla y edita
copy .env.example .env
# Edita .env con tu GEMINI_API_KEY y credenciales de prueba
# Opcional: HEADLESS=false  (para ver el navegador)
```
### 3️⃣ (Opcional) Guardar cookie

El login automático lo bloquea el antifraude de Betsson, así que se reutiliza una sesión iniciada a mano.

1. Inicia sesión en Betsson (`betsson.es`) con el navegador normal y **no cierres sesión**.
2. Exporta **todas** las cookies de Betsson a `cookies.json` (en la raíz del repo; está ignorado por git) con una extensión como *Cookie-Editor* → *Export → JSON*.
3. En esa misma pestaña abre la consola del navegador (`F12` → *Console*) y ejecuta:

   ```js
   copy(JSON.stringify({origin: location.origin, localStorage: {...localStorage}, sessionStorage: {...sessionStorage}}))
   ```

   Pega el resultado del portapapeles en un archivo `storage.json` (raíz del repo, también ignorado por git).
4. Importa la sesión y comprueba que está fresca:

   ```bash
   python scripts/import_cookies.py agent_com_s1 cookies.json storage.json
   python scripts/check_session.py agent_com_s1
   ```

5. Lanza el test enseguida (las cookies de login caducan en ~45-60 min):

   ```bash
   python -m pytest tests/test_scenario_1_spin.py -k com_s1 -o addopts="" -s -o log_cli=true -o log_cli_level=INFO
   ```

> ⚠️ `cookies.json` y `storage.json` equivalen a tu contraseña de sesión: no los subas ni los compartas, y bórralos al terminar.

### 4️⃣ Ejecutar los tests
| Acción | Comando | Qué hace |
|--------|---------|----------|
| **Unitarios** (sin abrir navegador) | `py -m pytest -m unit -v` | Verifica lógica interna. |
| **Check de recolección E2E** | `py -m pytest -m e2e --collect-only` | Lista los 4 escenarios. |
| **Scenario 2 – sin gasto** | `py -m pytest tests/test_scenario_2_no_funds.py -k "com_s2" -s` | Verifica mensaje *insufficient funds*. |
| **Scenario 1 – giro real** | `py -m pytest tests/test_scenario_1_spin.py -k "com_s1" -s` | Ejecuta un spin que consume saldo. |
| **Todos los agentes en paralelo** | `py -m pytest -m e2e -n 4 -s` | Lanza los 4 sub‑agentes simultáneamente. |
### 5️⃣ Encontrar los resultados

**Ejecución real** (se generan en `artifacts/`, que git ignora):

| Qué | Dónde |
|-----|-------|
| Reporte HTML (tabla de checks, abrir en cualquier navegador) | `artifacts/report.html` |
| Resumen en Markdown | `artifacts/report.md` |
| Resultado consolidado de los 4 agentes | `artifacts/master_report.json` |
| Resultado de un agente | `artifacts/<agent_id>/result_<agent_id>.json` |
| Capturas de evidencia | `artifacts/<agent_id>/evidence/` |
| Vídeo de la sesión | `artifacts/<agent_id>/video/` |
| Tráfico de red del juego (sin cookies ni tokens) | `artifacts/<agent_id>/network/game_transactions.json` |

**Reporte de ejemplo (SIMULADO, datos ficticios)** — está versionado en el repositorio para ver cómo se ve un informe con aciertos y un fallo detectado:

| Qué | Dónde |
|-----|-------|
| Reporte HTML de ejemplo | [`docs/demo_report_SIMULADO/report.html`](docs/demo_report_SIMULADO/report.html) |
| Resumen en Markdown | [`docs/demo_report_SIMULADO/report.md`](docs/demo_report_SIMULADO/report.md) |
| Log con el diagnóstico del fallo | [`docs/demo_report_SIMULADO/test_run.log`](docs/demo_report_SIMULADO/test_run.log) |

> ⚠️ Es una **simulación**: los datos son ficticios (no son resultados reales de Betsson). Lo real es la lógica de comprobación (S1.xx / S2.xx). En el ejemplo, `agent_pe_s1` falla en S1.09 y S1.10 a propósito, para demostrar que el sistema detecta errores. Para regenerarlo:
>
> ```bash
> python scripts/simulate_report.py docs/demo_report_SIMULADO
> ```

### 6️⃣ Logs de la ejecución

| Log | Dónde | Cuándo es útil |
|-----|-------|----------------|
| **Log en vivo** (cada paso del bot: sesión, juego, clic, saldo) | Terminal | Seguir la ejecución y ver dónde se queda. |
| **Log a archivo** | `artifacts/run.log` (si lo pides, ver abajo) | Guardar el log completo para compartirlo o revisarlo después. |
| **Diagnóstico por agente** (resumen + detalle de cada fallo) | `artifacts/test_run.log` (se escribe al terminar cada ejecución de pytest) | Entender qué check falló y por qué. |
| **Tráfico de red del juego** (qué peticiones hizo, sin cookies ni tokens) | `artifacts/<agent_id>/network/game_transactions.json` y `traffic_overview.json` | Si el giro no se reconoce, ver a qué servidor habla el juego. |
| **Captura de dónde falló** | `artifacts/<agent_id>/evidence/game_phase_failure.png` y `header_balance_not_found.png` | Ver qué había en pantalla cuando falló. |

**Log en vivo en la terminal:**

```bash
python -m pytest tests/test_scenario_1_spin.py -k com_s1 -o addopts="" -s -o log_cli=true -o log_cli_level=INFO
```

**Guardarlo además en un archivo** (las mismas opciones, más `log_file`):

```bash
python -m pytest tests/test_scenario_1_spin.py -k com_s1 -o addopts="" -s -o log_cli=true -o log_cli_level=INFO -o log_file=artifacts/run.log -o log_file_level=INFO
```

**Qué buscar en el log:**

| Línea | Qué significa |
|-------|---------------|
| `Reusing saved session ... (automated login skipped)` | Está usando la sesión importada. |
| `Session checkpoint '...': logged in` | La sesión sigue activa. `SESSION LOST` indica que se perdió en ese punto. |
| `Balance stable at ... (3 reads)` | Leyó el saldo de Betsson. |
| `Click N produced no spin request; re-locating the Spin button` | El clic no generó un giro y se vuelve a buscar el botón. |
| `Using the stored, previously verified Spin location (no AI call)` | Usa la posición del botón guardada de una ejecución anterior. |
| `No spin request recognised. The game's recent requests were: [...]` | No se detectó el giro; la lista dice a qué habla el juego. |
| `Game phase failed. Recent events ...` | Fallo al abrir el juego, con las últimas navegaciones y errores HTTP. |

> 🔒 **Privacidad:** los errores sustituyen el usuario y la contraseña por `***`, y los logs de red guardan solo `host/ruta` (nunca parámetros, cookies ni tokens). Aun así, `cookies.json` y `storage.json` no se comparten nunca.
>
> Ejemplo de `test_run.log` (de la simulación, datos ficticios): [`docs/demo_report_SIMULADO/test_run.log`](docs/demo_report_SIMULADO/test_run.log)

## 📦 Artefactos generados por cada ejecución
```
artifacts/
├─ report.html               # reporte interactivo con tabla y video embed
├─ report.md                 # resumen markdown del reporte
├─ test_run.log              # diagnóstico por agente y detalle de cada fallo
├─ run.log                   # (opcional) log completo si usas -o log_file=artifacts/run.log
├─ agent_com_s1/
│   ├─ result_agent_com_s1.json
│   ├─ evidence/ …
│   ├─ video/ …
│   └─ network/ …
├─ agent_pe_s2/ …
└─ … (otros agentes)
```

---




*Documentado y probado en Windows PowerShell + WSL Ubuntu 22.04, Python 3.14, Playwright 1.47*.
