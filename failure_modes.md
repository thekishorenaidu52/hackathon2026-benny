# Failure Mode Analysis
## ShopWave Autonomous Support Agent

### Failure Mode 1: Tool Timeout
**Scenario:** `get_order` tool times out when looking up order details.

**How it happens:** 10% chance of timeout simulated in mock tools.

**How agent handles it:**
- Catches TimeoutError exception
- Retries the tool call once after 1 second
- If retry also fails, logs the error and escalates ticket to human agent
- Customer receives reply that case is being reviewed

**Example:** TKT-010 order lookup times out → retry → escalate with full context

---

### Failure Mode 2: Malformed Data Response
**Scenario:** `get_customer` returns corrupted/malformed data.

**How it happens:** 5% chance of malformed response simulated.

**How agent handles it:**
- Detects error key in response
- Does not crash — continues processing with available data
- Logs malformed response in audit log
- Escalates ticket with note about data issue

**Example:** Customer lookup returns malformed data → agent escalates with "data issue" note

---

### Failure Mode 3: Low Confidence Decision
**Scenario:** Gemini AI is not confident enough to make a decision.

**How it happens:** Ambiguous tickets like TKT-020 ("my thing is broken").

**How agent handles it:**
- Checks confidence score after every decision
- If confidence < 0.6 → automatically escalates regardless of original action
- Logs original intended action and actual action taken
- Sends empathetic reply to customer

**Example:** TKT-020 ambiguous ticket → confidence 0.4 → auto escalate to human

---

### Failure Mode 4: API Rate Limit
**Scenario:** Gemini API quota exceeded during concurrent processing.

**How it happens:** Free tier allows limited requests per minute.

**How agent handles it:**
- Catches 429 error from Gemini
- Falls back to ESCALATE action with reasoning loggeds
- Does not crash — all 20 tickets still processed
- Audit log records the API failure

---

### Failure Mode 5: Order Not Found
**Scenario:** Customer provides wrong or fake order ID (e.g. ORD-9999).

**How it happens:** TKT-017 customer provides non-existent order ID.

**How agent handles it:**
- get_order returns error: "Order not found"
- Agent detects missing order data
- Responds professionally asking for correct order details
- Flags threatening language if present
- Does not process refund without valid order