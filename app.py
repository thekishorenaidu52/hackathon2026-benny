from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json
import os
import random
import time
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

app = Flask(__name__)
CORS(app)

# Load data
with open("data/customers.json") as f:
    CUSTOMERS = {c["email"]: c for c in json.load(f)}
with open("data/orders.json") as f:
    ORDERS = {o["order_id"]: o for o in json.load(f)}
with open("data/products.json") as f:
    PRODUCTS = {p["product_id"]: p for p in json.load(f)}
with open("data/knowledge_base.md") as f:
    KNOWLEDGE_BASE = f.read()

def get_order(order_id):
    if random.random() < 0.1:
        raise TimeoutError(f"get_order timed out for {order_id}")
    return ORDERS.get(order_id, {"error": "Order not found"})

def get_customer(email):
    return CUSTOMERS.get(email, {"error": "Customer not found"})

def get_product(product_id):
    return PRODUCTS.get(product_id, {"error": "Product not found"})

def search_knowledge_base(query):
    query_lower = query.lower()
    relevant = []
    for section in KNOWLEDGE_BASE.split("##"):
        if any(word in section.lower() for word in query_lower.split()):
            relevant.append(section.strip()[:500])
    return "\n\n".join(relevant[:2]) if relevant else "No relevant policy found"

def check_refund_eligibility(order_id):
    order = ORDERS.get(order_id)
    if not order:
        return {"eligible": False, "reason": "Order not found"}
    if order.get("refund_status") == "refunded":
        return {"eligible": False, "reason": "Already refunded"}
    return {"eligible": True, "reason": "Eligible for refund review"}

def resolve_single_ticket(email, subject, body):
    tool_calls = []
    
    # Tool 1: Get customer
    customer = get_customer(email)
    tool_calls.append({"tool": "get_customer", "result": customer})

    # Tool 2: Extract order ID
    order_id = None
    for word in body.split():
        word = word.strip(".,!?")
        if word.startswith("ORD-"):
            order_id = word
            break

    # Tool 3: Get order
    order = None
    product = None
    if order_id:
        try:
            order = get_order(order_id)
            tool_calls.append({"tool": "get_order", "result": order})
            if order and "error" not in order:
                product = get_product(order.get("product_id", ""))
                tool_calls.append({"tool": "get_product", "result": product})
        except TimeoutError:
            time.sleep(1)
            try:
                order = get_order(order_id)
                tool_calls.append({"tool": "get_order", "result": order})
            except:
                order = {"error": "Order lookup failed"}
                tool_calls.append({"tool": "get_order", "result": order})

    # Tool 4: Search knowledge base
    kb = search_knowledge_base(subject + " " + body[:100])
    tool_calls.append({"tool": "search_knowledge_base", "result": kb[:200]})

    # Gemini decision
    context = f"""
You are an autonomous customer support agent for ShopWave.

TICKET:
Email: {email}
Subject: {subject}
Body: {body}

CUSTOMER: {json.dumps(customer, indent=2)}
ORDER: {json.dumps(order, indent=2) if order else "No order found"}
PRODUCT: {json.dumps(product, indent=2) if product else "No product found"}
POLICY: {kb[:600]}

Decide the best action. Respond ONLY in this JSON format:
{{
  "action": "ISSUE_REFUND|SEND_REPLY|ESCALATE|CANCEL_ORDER|DENY",
  "confidence": 0.0-1.0,
  "reasoning": "explain why in 1-2 sentences",
  "reply_message": "professional reply to customer",
  "priority": "low|medium|high|urgent"
}}
"""
    try:
        response = model.generate_content(context)
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        decision = json.loads(text)
    except Exception as e:
        decision = {
            "action": "ESCALATE",
            "confidence": 0.3,
            "reasoning": f"Agent error: {str(e)}",
            "reply_message": "We are reviewing your case and will get back to you shortly.",
            "priority": "medium"
        }

    # Check refund eligibility
    if decision.get("action") == "ISSUE_REFUND" and order_id:
        eligibility = check_refund_eligibility(order_id)
        tool_calls.append({"tool": "check_refund_eligibility", "result": eligibility})
        if not eligibility.get("eligible"):
            decision["action"] = "DENY"
            decision["reply_message"] = f"Unable to process refund: {eligibility.get('reason')}"

    return {
        "action": decision.get("action"),
        "confidence": decision.get("confidence"),
        "reasoning": decision.get("reasoning"),
        "reply_message": decision.get("reply_message"),
        "priority": decision.get("priority"),
        "tool_calls": tool_calls
    }

# ── HTML UI ──
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ShopWave Support Agent</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f0f1a; color: #e0e0e0; min-height: 100vh; }
  
  .header { background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 24px 40px; border-bottom: 1px solid #2a2a4a; display: flex; align-items: center; gap: 16px; }
  .logo { width: 44px; height: 44px; background: linear-gradient(135deg, #6c63ff, #ff6584); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
  .header h1 { font-size: 22px; color: #fff; }
  .header p { font-size: 13px; color: #8888aa; }
  .badge { margin-left: auto; background: #1a3a2a; color: #4caf82; padding: 6px 14px; border-radius: 20px; font-size: 12px; border: 1px solid #2a5a3a; }

  .container { max-width: 1100px; margin: 0 auto; padding: 32px 24px; display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  
  .card { background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 16px; padding: 24px; }
  .card h2 { font-size: 16px; color: #aaaacc; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 1px; }
  
  label { display: block; font-size: 13px; color: #8888aa; margin-bottom: 6px; margin-top: 14px; }
  input, textarea, select { width: 100%; background: #0f0f1a; border: 1px solid #2a2a4a; border-radius: 8px; padding: 10px 14px; color: #e0e0e0; font-size: 14px; outline: none; transition: border 0.2s; }
  input:focus, textarea:focus { border-color: #6c63ff; }
  textarea { resize: vertical; min-height: 100px; }
  
  .btn { width: 100%; margin-top: 20px; padding: 14px; background: linear-gradient(135deg, #6c63ff, #5a54e0); color: white; border: none; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }
  .btn:hover { opacity: 0.9; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .quick-btn { background: #1a1a3a; border: 1px solid #3a3a5a; color: #aaaacc; padding: 8px 12px; border-radius: 8px; font-size: 12px; cursor: pointer; margin: 4px; transition: all 0.2s; }
  .quick-btn:hover { border-color: #6c63ff; color: #6c63ff; }

  .result { display: none; }
  .result.show { display: block; }
  
  .action-badge { display: inline-block; padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-bottom: 16px; }
  .ISSUE_REFUND { background: #1a3a2a; color: #4caf82; border: 1px solid #2a5a3a; }
  .ESCALATE { background: #3a1a1a; color: #f44336; border: 1px solid #5a2a2a; }
  .SEND_REPLY { background: #1a2a3a; color: #2196f3; border: 1px solid #2a3a5a; }
  .CANCEL_ORDER { background: #2a2a1a; color: #ff9800; border: 1px solid #4a3a1a; }
  .DENY { background: #2a1a2a; color: #9c27b0; border: 1px solid #4a2a4a; }

  .confidence-bar { background: #0f0f1a; border-radius: 20px; height: 8px; margin: 8px 0 16px; overflow: hidden; }
  .confidence-fill { height: 100%; background: linear-gradient(90deg, #6c63ff, #4caf82); border-radius: 20px; transition: width 0.5s; }

  .reply-box { background: #0f0f1a; border: 1px solid #2a2a4a; border-radius: 10px; padding: 16px; margin: 12px 0; font-size: 14px; line-height: 1.6; color: #ccccee; }
  
  .tool-call { background: #0f0f1a; border-left: 3px solid #6c63ff; padding: 10px 14px; margin: 8px 0; border-radius: 0 8px 8px 0; font-size: 12px; }
  .tool-name { color: #6c63ff; font-weight: 600; margin-bottom: 4px; }
  .tool-result { color: #8888aa; word-break: break-all; }

  .loading { display: none; text-align: center; padding: 40px; }
  .loading.show { display: block; }
  .spinner { width: 40px; height: 40px; border: 3px solid #2a2a4a; border-top-color: #6c63ff; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px; }
  .stat { background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 16px; text-align: center; }
  .stat-num { font-size: 28px; font-weight: 700; color: #6c63ff; }
  .stat-label { font-size: 12px; color: #8888aa; margin-top: 4px; }
</style>
</head>
<body>

<div class="header">
  <div class="logo">🤖</div>
  <div>
    <h1>ShopWave Autonomous Support Agent</h1>
    <p>Ksolves Agentic AI Hackathon 2026</p>
  </div>
  <div class="badge">● Live</div>
</div>

<div class="container">
  <!-- LEFT: Input -->
  <div>
    <div class="stats">
      <div class="stat"><div class="stat-num">20</div><div class="stat-label">Mock Tickets</div></div>
      <div class="stat"><div class="stat-num">8</div><div class="stat-label">Tools</div></div>
      <div class="stat"><div class="stat-num">100%</div><div class="stat-label">AI Powered</div></div>
    </div>

    <div class="card">
      <h2>Submit Support Ticket</h2>
      
      <div style="margin-bottom:16px">
        <div style="font-size:12px;color:#8888aa;margin-bottom:8px">Quick Load:</div>
        <button class="quick-btn" onclick="loadTicket('alice.turner@email.com','Refund request for headphones','Hi, I bought headphones last month but they stopped working after a week. Order ORD-1001. I want a full refund.')">Refund Request</button>
        <button class="quick-btn" onclick="loadTicket('bob.mendes@email.com','Return smart watch','I received my smart watch on March 4th (ORD-1002) but I dont like it. Can I return it?')">Return Request</button>
        <button class="quick-btn" onclick="loadTicket('frank.osei@email.com','Cancel my order','Hey I just placed an order and I want to cancel it.')">Cancel Order</button>
        <button class="quick-btn" onclick="loadTicket('henry.marsh@email.com','Lamp came broken','The desk lamp I ordered arrived with a cracked base. Order ORD-1008. I have photos.')">Damaged Item</button>
      </div>

      <label>Customer Email</label>
      <input type="email" id="email" placeholder="customer@email.com">
      
      <label>Subject</label>
      <input type="text" id="subject" placeholder="e.g. Refund request for headphones">
      
      <label>Message</label>
      <textarea id="body" placeholder="Describe the customer's issue..."></textarea>
      
      <button class="btn" onclick="submitTicket()" id="submitBtn">🚀 Process with AI Agent</button>
    </div>
  </div>

  <!-- RIGHT: Result -->
  <div>
    <div class="card">
      <h2>Agent Decision</h2>
      
      <div class="loading" id="loading">
        <div class="spinner"></div>
        <p style="color:#8888aa">Agent is reasoning...</p>
        <p style="font-size:12px;color:#555577;margin-top:8px">Calling tools → Analysing → Deciding</p>
      </div>

      <div class="result" id="result">
        <span class="action-badge" id="actionBadge">-</span>
        
        <div style="font-size:13px;color:#8888aa;margin-bottom:4px">Confidence</div>
        <div class="confidence-bar"><div class="confidence-fill" id="confBar" style="width:0%"></div></div>
        <div style="font-size:13px;color:#aaaacc;margin-bottom:16px" id="confText">0%</div>

        <div style="font-size:13px;color:#8888aa;margin-bottom:6px">Reasoning</div>
        <div class="reply-box" id="reasoning">-</div>

        <div style="font-size:13px;color:#8888aa;margin-bottom:6px">Reply to Customer</div>
        <div class="reply-box" id="replyMsg">-</div>

        <div style="font-size:13px;color:#8888aa;margin-bottom:8px;margin-top:16px">Tool Calls</div>
        <div id="toolCalls"></div>
      </div>

      <div id="placeholder" style="text-align:center;padding:60px 20px;color:#555577">
        <div style="font-size:48px;margin-bottom:16px">🤖</div>
        <p>Submit a ticket to see the agent in action</p>
      </div>
    </div>
  </div>
</div>

<script>
function loadTicket(email, subject, body) {
  document.getElementById('email').value = email;
  document.getElementById('subject').value = subject;
  document.getElementById('body').value = body;
}

async function submitTicket() {
  const email = document.getElementById('email').value;
  const subject = document.getElementById('subject').value;
  const body = document.getElementById('body').value;

  if (!email || !subject || !body) {
    alert('Please fill all fields!');
    return;
  }

  // Show loading
  document.getElementById('loading').classList.add('show');
  document.getElementById('result').classList.remove('show');
  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('submitBtn').disabled = true;

  try {
    const response = await fetch('/api/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, subject, body })
    });

    const data = await response.json();

    // Hide loading, show result
    document.getElementById('loading').classList.remove('show');
    document.getElementById('result').classList.add('show');

    // Action badge
    const badge = document.getElementById('actionBadge');
    badge.textContent = data.action;
    badge.className = 'action-badge ' + data.action;

    // Confidence
    const conf = Math.round(data.confidence * 100);
    document.getElementById('confBar').style.width = conf + '%';
    document.getElementById('confText').textContent = conf + '%';

    // Reasoning & reply
    document.getElementById('reasoning').textContent = data.reasoning;
    document.getElementById('replyMsg').textContent = data.reply_message;

    // Tool calls
    const tc = document.getElementById('toolCalls');
    tc.innerHTML = data.tool_calls.map(t => `
      <div class="tool-call">
        <div class="tool-name">🔧 ${t.tool}</div>
        <div class="tool-result">${JSON.stringify(t.result).substring(0, 150)}...</div>
      </div>
    `).join('');

  } catch (err) {
    document.getElementById('loading').classList.remove('show');
    alert('Error: ' + err.message);
  }

  document.getElementById('submitBtn').disabled = false;
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/resolve", methods=["POST"])
def resolve():
    data = request.json
    email = data.get("email", "")
    subject = data.get("subject", "")
    body = data.get("body", "")
    
    result = resolve_single_ticket(email, subject, body)
    return jsonify(result)

if __name__ == "__main__":
    print("🚀 ShopWave Agent UI running at http://localhost:5000")
    app.run(debug=True, port=5000)