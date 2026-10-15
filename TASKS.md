# Reparto de Tareas — Intelligent Game Validation (Betsson Challenge)

> **Instrucciones para los agentes de IA:** este documento define 4 ramas de trabajo **totalmente disjuntas**.
> Cada integrante (y su agente de IA) solo trabajará en **su rama** y en **los archivos listados como suyos**.
> **PROHIBIDO editar archivos de otro integrante.** Si necesitas un cambio en un archivo ajeno, anótalo en la
> sección *"Peticiones entre ramas"* al final de tu rama y avísalo en el chat del grupo.
> El objetivo es hacer **merge sin ningún merge conflict**.

---

## Contexto del proyecto (leer antes de empezar)

Sistema de validación E2E que navega el lobby de Betsson, abre un juego de Pragmatic Play en **Real Play**
y valida lo que ve el jugador usando **visión por computadora + Gemini** (sin DOM del juego; el DOM del
lobby/cabecera sí está permitido). Ejecuta **2 escenarios × 2 mercados = 4 subagentes en paralelo**:

| Subagente | Mercado | Idioma / Moneda | Cuenta | Misión |
|---|---|---|---|---|
| `agent_com_s1` | betsson.com | EN / EUR (€) | `BETSSON_COM_S1_USER/PASS` | Escenario 1: Spin real + reconciliación |
| `agent_com_s2` | betsson.com | EN / EUR (€) | `BETSSON_COM_S2_USER/PASS` | Escenario 2: saldo insuficiente, msg EN |
| `agent_pe_s1` | betsson.pe | ES / PEN (S/) | `BETSSON_PE_S1_USER/PASS` | Escenario 1: Spin real + reconciliación |
| `agent_pe_s2` | betsson.pe | ES / PEN (S/) | `BETSSON_PE_S2_USER/PASS` | Escenario 2: saldo insuficiente, msg ES |

**Reglas de oro del proyecto (del blueprint v3):**
1. **Dinaro siempre en `Decimal`, nunca `float`.** Fórmula: `saldo_después = saldo_antes − apuesta + premio` (tolerancia ±0.01). El giro no tiene que ganar.
2. **Soft checks**: cada check se registra como PASS/FAIL con detalle; nunca un `assert` que corte la ejecución del resto de checks.
3. **Sin secretos** en repo, informes, capturas ni vídeo. Login en contexto Playwright **sin grabación**; la grabación solo cubre el juego.
4. **Sin `sleep` fijos** salvo pausas de asentamiento; esperas por polling dinámico.
5. **Spike antes que código**: nada de selectores inventados; verificar contra el sitio real.
6. Python 3.11+, tipado completo, módulos < 400 líneas, sin placeholders vacíos.
7. Cada subagente tiene su propio directorio de artefactos: `artifacts/{agent_id}/`.

**Estado actual del repo:** estructura de carpetas vacía (archivos `__init__.py`, `config/`, etc. sin implementar),
más `pytest.ini`, `requirements.txt`, `README.md` y `.env.example`. No hay código todavía. **No crees la estructura de carpetas: ya existe.**

---

## Reglas para evitar merge conflicts

1. **Cada rama nace de `main`**: `git checkout -b agente-X/main` desde `main` actualizada.
2. **Propiedad exclusiva de archivos** (ver tabla por integrante). Si un archivo no aparece en tu lista, no lo toques.
3. **Archivos compartidos** (`requirements.txt`, `pytest.ini`, `config/markets.json`, `.env.example`, `README.md`):
   tienen **un único dueño por archivo** (indicado abajo). Los demás piden cambios por escrito en su sección de
   *"Peticiones entre ramas"*; el dueño los aplica.
4. **Commits pequeños y atómicos** con prefijo de rama: `[core]`, `[browser]`, `[vision]`, `[e2e]`.
5. **No hacer `main` mergeable a mano**; los merges los hace el coordinador en este orden (ver Fase de integración).
6. **Imports cruzados**: si necesitas un módulo de otra rama que aún no existe, define un **Protocol/TypedDict local**
   o pasa los datos por contrato Pydantic (ver Contratos compartidos). No importes código de otra rama hasta la integración.

---

## Contratos compartidos (definidos en `src/models/schemas.py` — rama `core`)

La rama `core` es la **primera en integrarse** porque define los contratos Pydantic que usan todos:
`CheckResult` (id, nombre, esperado, obtenido, detalle, status PASS/FAIL/INFO), `SubAgentReport`,
`MasterReport`, contratos de respuesta de Gemini (texto crudo + campos opcionales + indicador de legibilidad),
`MarketConfig` (url, idioma, moneda, símbolo, palabras clave de aviso, juegos candidatos).
Las demás ramas deben diseñar sus APIs contra estos nombres **asumiendo que existirán** (aunque aún no estén en su rama).

---

## Reparto por integrante

### 👤 Integrante 1 — Rama `core` — *"Contratos y lógica pura"*
**Rama:** `core/main` · **Prefijo de commit:** `[core]`

**Archivos que posee (y NADIE más toca):**
- `src/models/schemas.py` ← contratos compartidos del proyecto
- `src/core/money.py`
- `src/core/checks.py`
- `config/settings.py`
- `config/__init__.py`, `src/models/__init__.py`, `src/core/__init__.py`
- `tests/unit/test_money.py`, `tests/unit/test_checks.py`, `tests/unit/test_schemas.py`

**Tareas:**
1. **`src/models/schemas.py`** — Define y exporta:
   - `CheckStatus` (enum: PASS / FAIL / INFO / ERROR / SKIP)
   - `CheckResult`: `id: str`, `name: str`, `expected: str | None`, `observed: str | None`, `detail: str | None`, `status: CheckStatus`
   - `AgentId` (enum o Literal: `agent_com_s1`, `agent_com_s2`, `agent_pe_s1`, `agent_pe_s2`)
   - `Market` (enum: COM / PE)
   - `SubAgentReport`: `agent_id`, `market`, `scenario` (1|2), `checks: list[CheckResult]`, `evidence_dir: Path`, `video_path: Path | None`, `started_at`, `finished_at`, `overall: CheckStatus` (propiedad derivada)
   - `MasterReport`: `reports: list[SubAgentReport]` + propiedades agregadas (totales PASS/FAIL, flag `all_passed`)
   - Contratos de Gemini: `GeminiBalanceReading`, `GeminiHudReading`, `GeminiMessageReading` — todos con `raw_text: str`, campos opcionales parseados y `legible: bool`. Usa `pydantic` v2 con `temperature=0` en mente (el modelo devuelve JSON estructurado).
2. **`src/core/money.py`** — Parseo de dinero **siempre `Decimal`**:
   - `parse_money(raw: str, currency_hint: str | None) -> Decimal` — soporta `1.234,56` (ES) y `1,234.56` (EN), símbolos `€`, `S/`, `PEN`, `EUR`, espacios, NBSP.
   - `format_money(value: Decimal, market: Market) -> str`
   - `reconcile(before: Decimal, bet: Decimal, prize: Decimal, after: Decimal, tolerance: Decimal = Decimal("0.01")) -> tuple[bool, str]` — implementa `saldo_después = saldo_antes − apuesta + premio`.
   - `currency_for_market(market) -> str` (€ vs S/) y detección de símbolo en texto.
3. **`src/core/checks.py`** — Motor de soft checks:
   - `CheckRunner` que acumula `CheckResult` sin cortar la ejecución (`run(check_id, name, fn)` captura excepciones → status ERROR y sigue).
   - Helpers de reconciliación que emiten checks S1.09, S1.10, S2.06, S2.07.
   - Detección de palabras clave de idioma: EN (`insufficient`, `funds`, `balance`) / ES (`insuficiente`, `fondos`, `saldo`) — consumirá las listas desde `MarketConfig`.
4. **`config/settings.py`** — `pydantic-settings` con `BETSSON_{COM|PE}_S{1|2}_{USER|PASS}` y `GEMINI_API_KEY`; método `get_credentials(agent_id)`. Nunca imprimir secretos.
5. **Formateo y exportación de logs de tests (`test_run.log`)**:
   - En `src/models/schemas.py`:
     - Métodos `to_log_text()` en `SubAgentReport` y `MasterReport` que generan el informe legible en texto plano.
     - Indicador explícito `[PASSED]` o `[FAILED]` / `[ERROR]` a nivel de agente y global.
     - Bloque de detalles para cada fallo (`FAIL` o `ERROR`): ID del check, nombre, valores esperados vs observados, explicación detallada del fallo y ruta a la evidencia/captura.
     - Método `write_log(path: Path | str = "artifacts/test_run.log") -> Path` en `MasterReport` para escribirlo en disco.
6. **Tests unitarios TDD** en `tests/unit/` para money (ambos locales de número), checks, schemas y generación de logs. Sin red, sin credenciales. Deben pasar con `pytest tests/unit`.

**Definición de hecho:** `pytest tests/unit` en verde, tipado completo, sin floats en lógica de dinero, generación de `test_run.log` testeada con casos exitosos y fallidos.

---

### 👤 Integrante 2 — Rama `browser` — *"Spike + capa de navegador y flujos"*
**Rama:** `browser/main` · **Prefijo de commit:** `[browser]`

**Archivos que posee:**
- `src/browser/selectors.py`
- `src/browser/lobby_page.py`
- `src/browser/game_canvas.py`
- `src/flows/game_flow.py`
- `config/markets.json` ← **único dueño** (resultado del spike)
- `src/browser/__init__.py`, `src/flows/__init__.py`
- `tests/unit/test_selectors.py` (lógica pura de combinadores de selectores, si aplica)

**Tareas:**
1. **SPIKE (hacer PRIMERO, antes de código)** — Con las credenciales del `.env` y Playwright en local, verificar contra el sitio real y documentar en `config/markets.json`:
   - URLs reales de `betsson.com` y `betsson.pe` (¿misma estructura? ¿redirecciones? ¿geobloqueo desde nuestra IP?).
   - Cómo es el login (selectores del formulario — **nunca capturar la pantalla de login**).
   - Cómo navegar al lobby, filtrar/buscar juegos de **Pragmatic Play** y elegir uno simple, apuesta mínima, sin turbo/autoplay ni free spins (evitar R8).
   - Cómo se lanza el juego en **Real Play** (¿modal? ¿nueva página? ¿iframe cross-origin? ¿selector del iframe? ¿offset del iframe para convertir coordenadas? — R9).
   - Dónde se lee el **saldo de Betsson** en el lobby/cabecera (DOM permitido) y su moneda.
   - Estructura del HUD in-game (CREDIT/BET/WIN) — solo observación, la lectura es de la rama `vision`.
   - Resultado del spike en `config/markets.json`: por mercado → `url`, `locale`, `currency`, `currency_symbol`, `keywords_insufficient` (EN/ES), `game_candidates` (lista de títulos Pragmatic ordenada por idoneidad), `selectors` (lobby, iframe, saldo, botón de juego), y notas/riesgos observados.
2. **`src/browser/selectors.py`** — Selectores centralizados (data-testid, roles, textos) con fallbacks; nada de selectores mágicos inline.
3. **`src/browser/lobby_page.py`** — `LobbyPage`: login (contexto sin grabación), navegación al juego candidato, **lectura estabilizada del saldo Betsson** (polling hasta estabilidad con timeout — R10), lectura de moneda del header.
4. **`src/browser/game_canvas.py`** — `GameCanvas`: localizar iframe y su rectángulo, hacer clic en coordenadas relativas→absolutas (R9), posicionar/apuntar el botón Spin **vía coordenadas** (la posición se la pasará `vision`; aquí solo el mecanismo de clic), capturar screenshots, cerrar intros/popups del wrapper de Betsson.
5. **`src/flows/game_flow.py`** — Orquestación del flujo de un subagente en alto nivel: preparar juego (cerrar intros), **dos contextos de Playwright** (A: login sin grabación → guardar `auth_state_{agent_id}.json` en carpeta gitignored; B: contexto con `record_video_dir` a `artifacts/{agent_id}/video/` — R1), lecturas estabilizadas, detección del aviso de saldo insuficiente en sus **tres ubicaciones posibles** (al abrir, en el wrapper, tras el clic — R11) registrando cuál ocurrió.
   - Define la interfaz `SpinOutcome` / callbacks que la rama `e2e` usará, pero **no importes** `src/agents/*`.
6. Fallback WebGL: helpers para lanzar Chromium con `--use-gl=angle` / SwiftShader y viewport 1280×720 (R14).

**Definición de hecho:** spike documentado en `markets.json` con selectores verificados contra el sitio real; login + apertura de juego + lectura de saldo funcionando en local con un script mínimo de prueba manual.

---

### 👤 Integrante 3 — Rama `vision` — *"Inspección visual (Gemini + OpenCV)"*
**Rama:** `vision/main` · **Prefijo de commit:** `[vision]`

**Archivos que posee:**
- `src/vision/gemini_inspector.py`
- `src/vision/motion_detector.py`
- `src/vision/image_utils.py`
- `src/vision/__init__.py`
- `tests/unit/test_motion_detector.py`, `tests/unit/test_image_utils.py`
- `tests/fixtures/` (capturas de prueba **propia** sin datos personales — crear si hace falta)

**Tareas:**
1. **`src/vision/image_utils.py`** — Carga/recorte/annotación de imágenes (Pillow + numpy): recortar región de rodillos, anotar cajas en capturas de evidencia, enmascarado de datos personales si aparecen (R15), conversión BGR/RGB.
2. **`src/vision/motion_detector.py`** — Detección de movimiento sin `sleep` fijos:
   - Línea base de movimiento en **reposo** antes del clic, y derivación de umbrales (R7).
   - `motion_level(frame_a, frame_b) -> float` (dif de píxeles normalizada), `wait_until_stable(stream, ...)` por polling.
   - Señales combinadas para "giro empezó" (movimiento en zona de rodillos) y "giro terminó" (estabilización + HUD estable).
   - Bonus si sobra tiempo: integración local de OCR (consenso OCR + Gemini — R6), pero **no bloqueante**.
3. **`src/vision/gemini_inspector.py`** — Cliente de `google-genai` con `gemini-2.5-flash` (primario) y `gemini-2.5-pro` solo por **baja legibilidad o discrepancia entre lecturas** (nunca por fallo de reconciliación — R6):
   - `temperature=0`, salida JSON estructurado validado contra los contratos de `src/models/schemas.py` (importa los nombres; si la rama `core` aún no está integrada, define los Pydantic locales temporales **en tu propio archivo** y elimínalos al integrar — anota la petición en *"Peticiones entre ramas"*).
   - Prompts que devuelvan **texto crudo** para parseo posterior en código (R5): lectura de HUD (CREDIT/BET/WIN, moneda), extracción de mensaje de error (texto exacto + idioma detectado), localización del botón Spin (coordenadas relativas a la captura — R9), indicador `legible`.
   - **Rate limiting y reintentos** (R12): semáforo/limitador compartido para 4 agentes en paralelo, exponential backoff + jitter ante 429, caché de posición del Spin por mercado.
   - Escalado Flash→Pro por baja confianza de legibilidad.
4. **Tests unitarios** con imágenes fixture propias (sin capturas reales del reto con datos personales).

**Definición de hecho:** con capturas fixture, el inspector devuelve contratos válidos y el motion detector detecta bien "empezó/terminó" en un vídeo de prueba sintético o grabado propio.

---

### 👤 Integrante 4 — Rama `e2e` — *"Orquestación, tests E2E, informes y CI"*
**Rama:** `e2e/main` · **Prefijo de commit:** `[e2e]`

**Archivos que posee:**
- `src/agents/orchestrator.py`
- `src/agents/sub_agent.py`
- `src/report/` (evidencias + agregador)
- `scripts/summary.py`
- `tests/conft.py` → `tests/conftest.py`
- `tests/test_scenario_1_spin.py`
- `tests/test_scenario_2_no_funds.py`
- `.github/workflows/e2e-validation.yml`
- `pytest.ini` ← **único dueño**
- `requirements.txt` ← **único dueño** (otros piden adiciones por escrito)
- `tests/unit/test_orchestrator.py` (lógica pura del agregador/locks)

**Tareas:**
1. **`src/agents/sub_agent.py`** — `SubAgentWorker`: ciclo de vida aislado de un (mercado, escenario):
   - Recibe `agent_id`, cuenta, directorio `artifacts/{agent_id}/`.
   - Ejecuta los checks de su escenario como **soft checks** (S1.01–S1.11 + info, o S2.01–S2.07) usando el motor de checks de `core`, el flujo de `browser` y el inspector de `vision`.
   - Genera `result_{agent_id}.json` (`SubAgentReport`), capturas anotadas y vídeo.
   - Escenario 1: lee saldos antes, giro, estabiliza, lee premio, reconcilia ambos saldos.
   - Escenario 2: verifica precondición saldo<apuesta, giro, aviso, idioma, saldos sin cambio (S2.02: el movimiento de píxeles es **dato**, no criterio único — un modal también altera píxeles).
   - Detección de bonus/free spins (S1.07): si ocurre, **reintentar el giro**, no es FAIL del producto (R8).
   - **Importante:** como las ramas `core`/`browser`/`vision` pueden no estar integradas aún, define al inicio **interfaces `Protocol` propias** en `src/agents/` que repliquen las firmas necesarias, para poder desarrollar en paralelo y sustituirlas en la integración.
2. **`src/agents/orchestrator.py`** — `MasterOrchestrator`:
   - Lanza los 4 `SubAgentWorker` en paralelo (`pytest-xdist -n 4 --dist loadscope` o `ThreadPoolExecutor`/`asyncio`), cada uno con su instancia de Playwright.
   - Semáforo de rate-limit Gemini compartido (o delegado a `vision`).
   - `FileLock` por username **solo** si dos escenarios compartieran cuenta (fallback — R2/R12).
   - Agrega los 4 `SubAgentReport` → `MasterReport` → `report.html` + Markdown.
3. **`src/report/`** — Generación de evidencias por subagente (capturas anotadas en `artifacts/{agent_id}/evidence/`), `report.html` autónomo (inline, sin CDNs externos si es posible), resumen Markdown.
4. **`scripts/summary.py`** — Consolida los JSON de los 4 subagentes → Markdown para `$GITHUB_STEP_SUMMARY`.
5. **`tests/conftest.py`** — Fixtures por worker/subagente: parámetros `agent_id`, credenciales desde settings, creación de directorio de artefactos, hook de informe al finalizar, **skip condicional** si faltan credenciales o hay geobloqueo.
6. **`tests/test_scenario_1_spin.py` / `test_scenario_2_no_funds.py`** — Parametrizados por mercado (4 combinaciones), cada uno delegando en su `SubAgentWorker`. Un test fallido de CI no debe cortar la recolección de resultados de los otros.
7. **`.github/workflows/e2e-validation.yml`** — **Solo `workflow_dispatch`** (nunca `push`) porque cada ejecución gasta saldo real (R2); `concurrency` para no solapar; Python 3.12 en CI; secretos desde GitHub Secrets con el esquema `BETSSON_{COM|PE}_S{1|2}_{USER|PASS}` + `GEMINI_API_KEY`; artefactos subidos (informe + evidencias **sin** auth_state); paso final `scripts/summary.py` al step summary. **Plan B por geobloqueo (R3):** documentar en un comentario del workflow la opción de runner self-hosted/proxy y fallback a ejecución local.
8. **`pytest.ini`** — marcadores (`unit`, `e2e`, `slow`), `addopts` por defecto.

**Definición de hecho:** `pytest -m e2e --collect-only` funciona con las 4 combinaciones; el workflow existe y es manual; el agregador genera informe desde JSONs fixture.

---

## Fase de integración (orden de merges — lo hace el coordinador)

1. **`core/main` → `main`** primero (define los contratos).
2. **`browser/main` → main**, **`vision/main` → main** en paralelo (no se solapan archivos).
3. **`e2e/main` → main** al final (consume todo).
4. Tras cada merge: `git pull` de las ramas restantes restantes y resolver **solo** en la rama receptoraa los imports que ahora sí existen (sustituir los `Protocol` temporales por imports reales).
5. Ejecución conjunta en local: `pytest tests/unit` y luego `pytest -m e2e` (una vez, con cuidado de saldo).

---

## Peticiones entre ramas (log)

Cada integrante añade aquí (al final de su rama, y luego lo replica en un PR/commit de solo lectura o en el chat)
cualquier cambio que necesite en un archivo ajeno:

- _(vacío)_

---

## Checklist de seguridad (todos los integrantes)

- [ ] Nada de credenciales en código, logs, capturas ni vídeo (login siempre en contexto sin grabación).
- [ ] `.env`, `auth_state_*.json` y `artifacts/` están en `.gitignore`.
- [ ] Ninguna captura del formulario de login; nombres/emails enmascarados si aparecen.
- [ ] El workflow solo se dispara manualmente (gasta saldo real).
