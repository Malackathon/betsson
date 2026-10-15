> ⚠️ **SIMULACIÓN — DATOS FICTICIOS (no son resultados reales de Betsson)**

# 🎰 Betsson Intelligent Game Validation — E2E Master Report

**Overall Status:** ❌ **FAILED**  
**Sub-Agents Executed:** `4` | **Total Passed Checks:** `40` | **Total Failed Checks:** `2`  

---

## 📊 Sub-Agents Execution Summary

| Sub-Agent | Market | Scenario | Overall | Total Checks | Pass | Fail | Video |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| `agent_com_s1` | **COM** | **S1** | 🟢 PASS | 13 | 13 | 0 | _None_ |
| `agent_com_s2` | **COM** | **S2** | 🟢 PASS | 8 | 8 | 0 | _None_ |
| `agent_pe_s1` | **PE** | **S1** | 🔴 FAIL | 13 | 11 | 2 | _None_ |
| `agent_pe_s2` | **PE** | **S2** | 🟢 PASS | 8 | 8 | 0 | _None_ |

---

## 🔍 Detailed Checks Breakdown

### 🤖 `agent_com_s1` — COM (Scenario 1 (Real Play Spin & Math Reconciliation))

| Check ID | Name | Status | Expected | Observed | Detail |
|:---|:---|:---:|:---|:---|:---|
| **S1.01** | Saldo Betsson antes legible | ✅ PASS | `Decimal > 0` | `100.00` | Saldo en cabecera (DOM): 100.00 |
| **S1.02** | Juego Pragmatic abierto en Real Play | ✅ PASS | `HUD visible con CREDIT/BET/WIN` | `HUD legible` | Lectura visual de la captura tomada al liquidarse la ronda |
| **S1.03** | Moneda mostrada = mercado | ✅ PASS | `currency` | `screen currency '€', expected '€'` | screen currency '€', expected '€' |
| **S1.04** | Apuesta y saldo in-game legibles | ✅ PASS | `credit y bet legibles en pantalla` | `legibles` | balance: screen 99.80 == server 99.80 \| bet: screen 0.20 == server 0.20 |
| **S1.08** | Apuesta mostrada = apuesta usada | ✅ PASS | `apuesta en pantalla == apuesta cobrada por el servidor` | `screen 0.20 == server 0.20` | screen 0.20 == server 0.20 |
| **S1.05** | El giro empezó | ✅ PASS | `True` | `True` | La petición de giro llegó al servidor del juego (red) |
| **S1.06** | El giro terminó | ✅ PASS | `True` | `True` | El servidor liquidó la ronda (na=s) |
| **S1.05v** | El juego reaccionó en pantalla | ✅ PASS | `cambio visual >= 0.003` | `0.0134` | Diferencia entre la captura previa al giro y la tomada al liquidarse la ronda (sin IA) |
| **S1.07** | No se disparó bonus/free spins | ✅ PASS | `False` | `False` | Giro base estándar (0 reintento(s) por bonus) |
| **S1.09n** | Servidor: saldo reconcilia (red) | ✅ PASS | `saldo_después = antes − apuesta + premio` | `True` | antes=100.00, apuesta=0.20, premio=0.00, después=99.80 |
| **S1.09** | Saldo in-game reconcilia | ✅ PASS | `99.80` | `99.80` | Reconciliation PASSED: expected = before (100.00) - bet (0.20) + prize (0.00) = 99.80; observed after = 99.80; diff = 0.00 (tolerance = 0.01) |
| **S1.10** | Saldo Betsson reconcilia | ✅ PASS | `99.80` | `99.80` | Reconciliation PASSED: expected = before (100.00) - bet (0.20) + prize (0) = 99.80; observed after = 99.80; diff = 0.00 (tolerance = 0.01) |
| **S1.11** | Moneda de Betsson = mercado | ✅ PASS | `€` | `€` | Moneda en cabecera Betsson (DOM): '€' |

### 🤖 `agent_com_s2` — COM (Scenario 2 (Insufficient Funds Rejection & Language))

| Check ID | Name | Status | Expected | Observed | Detail |
|:---|:---|:---:|:---|:---|:---|
| **S2.01** | Precondición: saldo < apuesta | ✅ PASS | `saldo < apuesta` | `saldo=0.05, apuesta=0.20` | Cuenta preparada (saldo según el servidor) |
| **S2.02** | El giro es rechazado (no hay giro pagado) | ✅ PASS | `True` | `True` | estado del giro=no_traffic; saldo servidor antes=0.05, después=0.05 |
| **S2.03** | Mensaje de saldo insuficiente visible | ✅ PASS | `Texto de mensaje no vacío` | `Insufficient funds. Please deposit.` | Mensaje leído en pantalla: 'Insufficient funds. Please deposit.' |
| **S2.04** | Mensaje en el idioma del mercado | ✅ PASS | `any of: ['insufficient', 'funds']` | `matched: ['insufficient', 'funds']` | Found keyword(s) ['insufficient', 'funds'] in message: 'Insufficient funds. Please deposit.' |
| **S2.05** | Moneda mostrada = mercado | ✅ PASS | `€` | `screen currency '€', expected '€'` | screen currency '€', expected '€' |
| **S2.06** | Saldo in-game sin cambios | ✅ PASS | `0.05` | `0.05` | Balance unchanged: 0.05 |
| **S2.06v** | Saldo visible == saldo del servidor | ✅ PASS | `pantalla == servidor` | `screen 0.05 == server 0.05` | screen 0.05 == server 0.05 |
| **S2.07** | Saldo Betsson sin cambios | ✅ PASS | `0.05` | `0.05` | Balance unchanged: 0.05 |

### 🤖 `agent_pe_s1` — PE (Scenario 1 (Real Play Spin & Math Reconciliation))

| Check ID | Name | Status | Expected | Observed | Detail |
|:---|:---|:---:|:---|:---|:---|
| **S1.01** | Saldo Betsson antes legible | ✅ PASS | `Decimal > 0` | `100.00` | Saldo en cabecera (DOM): 100.00 |
| **S1.02** | Juego Pragmatic abierto en Real Play | ✅ PASS | `HUD visible con CREDIT/BET/WIN` | `HUD legible` | Lectura visual de la captura tomada al liquidarse la ronda |
| **S1.03** | Moneda mostrada = mercado | ✅ PASS | `currency` | `screen currency 'S/', expected 'S/'` | screen currency 'S/', expected 'S/' |
| **S1.04** | Apuesta y saldo in-game legibles | ✅ PASS | `credit y bet legibles en pantalla` | `legibles` | balance: screen shows 100.00, server says 99.80 \| bet: screen 0.20 == server 0.20 |
| **S1.08** | Apuesta mostrada = apuesta usada | ✅ PASS | `apuesta en pantalla == apuesta cobrada por el servidor` | `screen 0.20 == server 0.20` | screen 0.20 == server 0.20 |
| **S1.05** | El giro empezó | ✅ PASS | `True` | `True` | La petición de giro llegó al servidor del juego (red) |
| **S1.06** | El giro terminó | ✅ PASS | `True` | `True` | El servidor liquidó la ronda (na=s) |
| **S1.05v** | El juego reaccionó en pantalla | ✅ PASS | `cambio visual >= 0.003` | `0.0132` | Diferencia entre la captura previa al giro y la tomada al liquidarse la ronda (sin IA) |
| **S1.07** | No se disparó bonus/free spins | ✅ PASS | `False` | `False` | Giro base estándar (0 reintento(s) por bonus) |
| **S1.09n** | Servidor: saldo reconcilia (red) | ✅ PASS | `saldo_después = antes − apuesta + premio` | `True` | antes=100.00, apuesta=0.20, premio=0.00, después=99.80 |
| **S1.09** | Saldo in-game reconcilia | ❌ FAIL | `99.80` | `100.00` | Reconciliation FAILED: expected = before (100.00) - bet (0.20) + prize (0.00) = 99.80; observed after = 100.00; diff = 0.20 (tolerance = 0.01) |
| **S1.10** | Saldo Betsson reconcilia | ❌ FAIL | `99.80` | `100.00` | Reconciliation FAILED: expected = before (100.00) - bet (0.20) + prize (0) = 99.80; observed after = 100.00; diff = 0.20 (tolerance = 0.01) |
| **S1.11** | Moneda de Betsson = mercado | ✅ PASS | `S/` | `S/` | Moneda en cabecera Betsson (DOM): 'S/' |

### 🤖 `agent_pe_s2` — PE (Scenario 2 (Insufficient Funds Rejection & Language))

| Check ID | Name | Status | Expected | Observed | Detail |
|:---|:---|:---:|:---|:---|:---|
| **S2.01** | Precondición: saldo < apuesta | ✅ PASS | `saldo < apuesta` | `saldo=0.05, apuesta=0.20` | Cuenta preparada (saldo según el servidor) |
| **S2.02** | El giro es rechazado (no hay giro pagado) | ✅ PASS | `True` | `True` | estado del giro=no_traffic; saldo servidor antes=0.05, después=0.05 |
| **S2.03** | Mensaje de saldo insuficiente visible | ✅ PASS | `Texto de mensaje no vacío` | `Saldo insuficiente. Por favor, recarga.` | Mensaje leído en pantalla: 'Saldo insuficiente. Por favor, recarga.' |
| **S2.04** | Mensaje en el idioma del mercado | ✅ PASS | `any of: ['insuficiente', 'fondos', 'saldo']` | `matched: ['insuficiente', 'saldo']` | Found keyword(s) ['insuficiente', 'saldo'] in message: 'Saldo insuficiente. Por favor, recarga.' |
| **S2.05** | Moneda mostrada = mercado | ✅ PASS | `S/` | `screen currency 'S/', expected 'S/'` | screen currency 'S/', expected 'S/' |
| **S2.06** | Saldo in-game sin cambios | ✅ PASS | `0.05` | `0.05` | Balance unchanged: 0.05 |
| **S2.06v** | Saldo visible == saldo del servidor | ✅ PASS | `pantalla == servidor` | `screen 0.05 == server 0.05` | screen 0.05 == server 0.05 |
| **S2.07** | Saldo Betsson sin cambios | ✅ PASS | `0.05` | `0.05` | Balance unchanged: 0.05 |

---
*Report generated automatically by Antigravity Betsson Intelligent Game Validation E2E Orchestrator.*