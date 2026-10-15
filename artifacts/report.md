# 🎰 Betsson Intelligent Game Validation — E2E Master Report

**Overall Status:** ❌ **FAILED**  
**Sub-Agents Executed:** `2` | **Total Passed Checks:** `7` | **Total Failed Checks:** `0`  

---

## 📊 Sub-Agents Execution Summary

| Sub-Agent | Market | Scenario | Overall | Total Checks | Pass | Fail | Video |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| `agent_com_s1` | **COM** | **S1** | 🟠 ERROR | 1 | 0 | 0 | `page@7c5f9374b43cd0ede35e4ef303928d26.webm` |
| `agent_com_s2` | **COM** | **S2** | 🟢 PASS | 7 | 7 | 0 | _None_ |

---

## 🔍 Detailed Checks Breakdown

### 🤖 `agent_com_s1` — COM (Scenario 1 (Real Play Spin & Math Reconciliation))

| Check ID | Name | Status | Expected | Observed | Detail |
|:---|:---|:---:|:---|:---|:---|
| **CRITICAL_ERROR** | Ejecución de SubAgente sin excepciones críticas | ⚠️ ERROR | `Ejecución limpia` | `RuntimeError: [agent_com_s1] Logged-in header (balance) not found with the saved session: it may be expired/rejected, or the 'balance_display' selector in config/markets.json does not match this site. Re-save the session with: python scripts/save_session.py agent_com_s1. Detail: Page.evaluate: Target page, context or browser has been closed. Header screenshot: <screenshot unavailable> | Recent events (oldest first):
NAVIGATED www.betsson.es/
NAVIGATED www.betsson.es/
GET 401 www.betsson.es/api/v1/current-single-sign-on-session
GET 401 www.betsson.es/api/v1/gaming/dgoj/Session/GetSummary
GET 401 www.betsson.es/api/v1/gaming/dgoj/Session/Check
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
GET 401 www.betsson.es/api/v1/gaming/dgoj/Session/GetSummary
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
NAVIGATED www.betsson.es/
NAVIGATED www.betsson.es/inicio
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/v2/authentication-transaction
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate
NAVIGATED www.betsson.es/
CHECKPOINT failure: logged in | On screen: {'error': 'Page.evaluate: Target page, context or browser has been closed', 'iframes': [], 'dialogs': [], 'buttons': []} | Screenshot: <screenshot unavailable>` | RuntimeError: [agent_com_s1] Logged-in header (balance) not found with the saved session: it may be expired/rejected, or the 'balance_display' selector in config/markets.json does not match this site. Re-save the session with: python scripts/save_session.py agent_com_s1. Detail: Page.evaluate: Target page, context or browser has been closed. Header screenshot: <screenshot unavailable> \| Recent events (oldest first): NAVIGATED www.betsson.es/ NAVIGATED www.betsson.es/ GET 401 www.betsson.es/api/v1/current-single-sign-on-session GET 401 www.betsson.es/api/v1/gaming/dgoj/Session/GetSummary GET 401 www.betsson.es/api/v1/gaming/dgoj/Session/Check POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate GET 401 www.betsson.es/api/v1/gaming/dgoj/Session/GetSummary POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate NAVIGATED www.betsson.es/ NAVIGATED www.betsson.es/inicio POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/v2/authentication-transaction POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate POST 403 www.betsson.es/api/fraud/v1/groupib/tokens/generate NAVIGATED www.betsson.es/ CHECKPOINT failure: logged in \| On screen: {'error': 'Page.evaluate: Target page, context or browser has been closed', 'iframes': [], 'dialogs': [], 'buttons': []} \| Screenshot: <screenshot unavailable> |

### 🤖 `agent_com_s2` — COM (Scenario 2 (Insufficient Funds Rejection & Language))

| Check ID | Name | Status | Expected | Observed | Detail |
|:---|:---|:---:|:---|:---|:---|
| **S2.01** | Precondición: saldo < apuesta | ✅ PASS | `saldo < apuesta` | `saldo=0.05, apuesta=0.20` | Cuenta preparada para validar saldo insuficiente |
| **S2.02** | El giro es rechazado (no hay giro pagado) | ✅ PASS | `True` | `True` | Saldo no descontado y aviso presente. Movimiento en pantalla=True (dato informativo de modal) |
| **S2.03** | Mensaje de saldo insuficiente visible | ✅ PASS | `Texto de mensaje no vacío` | `Insufficient funds to place bet. Please deposit.` | Mensaje extraído: 'Insufficient funds to place bet. Please deposit.' |
| **S2.04** | Mensaje en el idioma del mercado | ✅ PASS | `any of: ['insufficient', 'funds', 'balance']` | `matched: ['insufficient', 'funds']` | Found keyword(s) ['insufficient', 'funds'] in message: 'Insufficient funds to place bet. Please deposit.' |
| **S2.05** | Moneda mostrada = mercado | ✅ PASS | `€` | `€` | Moneda en interfaz de alerta: € |
| **S2.06** | Saldo in-game sin cambios | ✅ PASS | `0.05` | `0.05` | Balance unchanged: 0.05 |
| **S2.07** | Saldo Betsson sin cambios | ✅ PASS | `0.05` | `0.05` | Balance unchanged: 0.05 |

---
*Report generated automatically by Antigravity Betsson Intelligent Game Validation E2E Orchestrator.*