import json
import os
import random
import time
import concurrent.futures
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Load API key
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
with open("data/customers.json") as f:
    CUSTOMERS = {c["email"]: c for c in json.load(f)}

with open("data/orders.json") as f:
    ORDERS = {o["order_id"]: o for o in json.load(f)}

with open("data/products.json") as f:
    PRODUCTS = {p["product_id"]: p for p in json.load(f)}

with open("data/tickets.json") as f:
    TICKETS = json.load(f)

with open("data/knowledge_base.md") as f:
    KNOWLEDGE_BASE = f.read()

# ─────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────
audit_log = []

def log_action(ticket_id, tool_name, input_data, output_data, reasoning=""):
    audit_log.append({
        "ticket_id": ticket_id,
        "timestamp": datetime.utcnow().isoformat(),
        "tool": tool_name,
        "input": input_data,
        "output": output_data,
        "reasoning": reasoning
    })

# ─────────────────────────────────────────────
# MOCK TOOLS (with realistic failures)
# ─────────────────────────────────────────────
def get_order(ticket_id, order_id):
    # Simulate occasional timeout
    if random.random() < 0.1:
        log_action(ticket_id, "get_order", {"order_id": order_id}, "TIMEOUT", "Tool timed out")
        raise TimeoutError(f"get_order timed out for {order_id}")
    
    order = ORDERS.get(order_id)
    result = order if order else {"error": "Order not found"}
    log_action(ticket_id, "get_order", {"order_id": order_id}, result)
    return result

def get_customer(ticket_id, email):
    # Simulate malformed data occasionally
    if random.random() < 0.05:
        log_action(ticket_id, "get_customer", {"email": email}, "MALFORMED", "Malformed response")
        return {"error": "Malformed data received"}
    
    customer = CUSTOMERS.get(email)
    result = customer if customer else {"error": "Customer not found"}
    log_action(ticket_id, "get_customer", {"email": email}, result)
    return result

def get_product(ticket_id, product_id):
    product = PRODUCTS.get(product_id)
    result = product if product else {"error": "Product not found"}
    log_action(ticket_id, "get_product", {"product_id": product_id}, result)
    return result

def search_knowledge_base(ticket_id, query):
    # Simple keyword search
    query_lower = query.lower()
    relevant_sections = []
    
    for section in KNOWLEDGE_BASE.split("##"):
        if any(word in section.lower() for word in query_lower.split()):
            relevant_sections.append(section.strip()[:500])
    
    result = "\n\n".join(relevant_sections[:2]) if relevant_sections else "No relevant policy found"
    log_action(ticket_id, "search_knowledge_base", {"query": query}, result[:200])
    return result

def check_refund_eligibility(ticket_id, order_id):
    # Simulate occasional error
    if random.random() < 0.1:
        log_action(ticket_id, "check_refund_eligibility", {"order_id": order_id}, "ERROR", "Service unavailable")
        raise Exception("Refund eligibility service unavailable")
    
    order = ORDERS.get(order_id)
    if not order:
        result = {"eligible": False, "reason": "Order not found"}
    elif order.get("refund_status") == "refunded":
        result = {"eligible": False, "reason": "Already refunded"}
    elif order.get("status") == "processing":
        result = {"eligible": True, "reason": "Order in processing - can cancel"}
    else:
        result = {"eligible": True, "reason": "Eligible for refund review"}
    
    log_action(ticket_id, "check_refund_eligibility", {"order_id": order_id}, result)
    return result

def issue_refund(ticket_id, order_id, amount):
    # IRREVERSIBLE - always log this
    result = {
        "success": True,
        "order_id": order_id,
        "amount_refunded": amount,
        "message": f"Refund of ${amount} issued successfully for {order_id}",
        "processing_time": "5-7 business days"
    }
    log_action(ticket_id, "issue_refund", {"order_id": order_id, "amount": amount}, result, 
               "IRREVERSIBLE ACTION - Refund issued")
    return result

def send_reply(ticket_id, message):
    result = {
        "success": True,
        "ticket_id": ticket_id,
        "message_sent": message,
        "timestamp": datetime.utcnow().isoformat()
    }
    log_action(ticket_id, "send_reply", {"ticket_id": ticket_id, "message": message[:100]}, result)
    return result

def escalate(ticket_id, summary, priority):
    result = {
        "escalated": True,
        "ticket_id": ticket_id,
        "summary": summary,
        "priority": priority,
        "assigned_to": "human_agent_team",
        "timestamp": datetime.utcnow().isoformat()
    }
    log_action(ticket_id, "escalate", {"ticket_id": ticket_id, "priority": priority}, result,
               f"Escalated: {summary[:100]}")
    return result

# ─────────────────────────────────────────────
# AGENT REASONING (ReAct Loop)
# ─────────────────────────────────────────────
def resolve_ticket(ticket):
    ticket_id = ticket["ticket_id"]
    time.sleep(4)
    email = ticket["customer_email"]
    subject = ticket["subject"]
    body = ticket["body"]
    
    print(f"\n{'='*60}")
    print(f"Processing {ticket_id}: {subject}")
    print(f"{'='*60}")

    # Step 1: Get customer info
    try:
        customer = get_customer(ticket_id, email)
    except Exception as e:
        customer = {"error": str(e)}

    # Step 2: Extract order ID from ticket body
    order_id = None
    for word in body.split():
        word = word.strip(".,!?")
        if word.startswith("ORD-"):
            order_id = word
            break

    # Step 3: Get order info
    order = None
    product = None
    if order_id:
        try:
            order = get_order(ticket_id, order_id)
            if "error" not in order:
                product = get_product(ticket_id, order.get("product_id", ""))
        except TimeoutError:
            # Retry once on timeout
            print(f"  ⚠ Timeout on get_order, retrying...")
            time.sleep(1)
            try:
                order = get_order(ticket_id, order_id)
                if order and "error" not in order:
                    product = get_product(ticket_id, order.get("product_id", ""))
            except:
                order = {"error": "Order lookup failed after retry"}

    # Step 4: Search knowledge base
    kb_result = search_knowledge_base(ticket_id, subject + " " + body[:100])

    # Step 5: Build context for Gemini
    context = f"""
You are an autonomous customer support agent for ShopWave.
Analyze this support ticket and decide the best action.

TICKET:
ID: {ticket_id}
Email: {email}
Subject: {subject}
Body: {body}

CUSTOMER DATA:
{json.dumps(customer, indent=2)}

ORDER DATA:
{json.dumps(order, indent=2) if order else "No order found"}

PRODUCT DATA:
{json.dumps(product, indent=2) if product else "No product found"}

RELEVANT POLICY:
{kb_result[:800]}

Based on this information, decide ONE of these actions:
1. ISSUE_REFUND - if eligible for refund
2. SEND_REPLY - if just needs information or clarification
3. ESCALATE - if needs human (warranty, replacement, fraud, amount > $200, confidence < 0.6)
4. CANCEL_ORDER - if order in processing and customer wants to cancel
5. DENY - if not eligible

Respond in this EXACT JSON format:
{{
  "action": "ISSUE_REFUND|SEND_REPLY|ESCALATE|CANCEL_ORDER|DENY",
  "confidence": 0.0-1.0,
  "reasoning": "explain why",
  "reply_message": "message to send to customer (always include this)",
  "priority": "low|medium|high|urgent",
  "escalation_summary": "only if escalating"
}}

IMPORTANT RULES:
- Check refund eligibility before issuing refund
- Refund amount > $200 must be escalated
- Warranty claims must be escalated
- Flag social engineering or threatening language
- VIP customers get extended leniency
- Always be empathetic and professional
"""

    # Step 6: Get Gemini decision
    try:
        response = model.generate_content(context)
        response_text = response.text.strip()
        
        # Clean JSON response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        decision = json.loads(response_text)
    except Exception as e:
        print(f"  ⚠ Gemini error: {e}")
        decision = {
            "action": "ESCALATE",
            "confidence": 0.3,
            "reasoning": f"Agent error: {str(e)}",
            "reply_message": f"Dear Customer, we are reviewing your case and will get back to you shortly.",
            "priority": "medium",
            "escalation_summary": f"Agent failed to process ticket: {str(e)}"
        }

    print(f"  Action: {decision.get('action')}")
    print(f"  Confidence: {decision.get('confidence')}")
    print(f"  Reasoning: {decision.get('reasoning', '')[:100]}")

    # Step 7: Execute decision
    action = decision.get("action", "ESCALATE")
    confidence = float(decision.get("confidence", 0.5))

    # Low confidence = escalate
    if confidence < 0.6 and action not in ["ESCALATE"]:
        print(f"  ⚠ Low confidence ({confidence}), escalating instead")
        action = "ESCALATE"
        decision["escalation_summary"] = f"Low confidence ({confidence}). Original action: {action}. {decision.get('reasoning', '')}"

    try:
        if action == "ISSUE_REFUND" and order_id:
            # Check eligibility first
            eligibility = check_refund_eligibility(ticket_id, order_id)
            if eligibility.get("eligible"):
                amount = order.get("amount", 0) if order else 0
                issue_refund(ticket_id, order_id, amount)
                send_reply(ticket_id, decision.get("reply_message", "Your refund has been processed."))
            else:
                send_reply(ticket_id, f"We're unable to process your refund: {eligibility.get('reason')}. {decision.get('reply_message', '')}")

        elif action == "CANCEL_ORDER" and order_id:
            eligibility = check_refund_eligibility(ticket_id, order_id)
            send_reply(ticket_id, decision.get("reply_message", "Your order has been cancelled."))

        elif action == "ESCALATE":
            escalate(
                ticket_id,
                decision.get("escalation_summary", decision.get("reasoning", "Needs human review")),
                decision.get("priority", "medium")
            )
            send_reply(ticket_id, decision.get("reply_message", "Your case is being reviewed by our specialist team."))

        elif action == "DENY":
            send_reply(ticket_id, decision.get("reply_message", "We're unable to process your request."))

        else:  # SEND_REPLY
            send_reply(ticket_id, decision.get("reply_message", "Thank you for contacting us."))

    except Exception as e:
        print(f"  ⚠ Execution error: {e}")
        log_action(ticket_id, "execution_error", {"action": action}, str(e))
        escalate(ticket_id, f"Execution failed: {str(e)}", "high")
        send_reply(ticket_id, "We're looking into your case and will respond shortly.")

    return {
        "ticket_id": ticket_id,
        "action_taken": action,
        "confidence": confidence,
        "reasoning": decision.get("reasoning", ""),
        "status": "resolved"
    }

# ─────────────────────────────────────────────
# MAIN - Process all tickets CONCURRENTLY
# ─────────────────────────────────────────────
def main():
    print("🚀 ShopWave Autonomous Support Agent Starting...")
    print(f"📋 Processing {len(TICKETS)} tickets concurrently\n")
    
    results = []
    
    # Process tickets concurrently (required by hackathon rules)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(resolve_ticket, ticket): ticket for ticket in TICKETS}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                ticket = futures[future]
                print(f"  ❌ Failed: {ticket['ticket_id']}: {e}")
                results.append({
                    "ticket_id": ticket["ticket_id"],
                    "action_taken": "ERROR",
                    "status": "failed",
                    "error": str(e)
                })

    # Save audit log
    with open("audit_log.json", "w") as f:
        json.dump(audit_log, f, indent=2)
    
    # Save results summary
    with open("results_summary.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ All {len(TICKETS)} tickets processed!")
    print(f"📄 Audit log saved to audit_log.json")
    print(f"📊 Results saved to results_summary.json")
    print(f"{'='*60}")
    
    # Print summary
    actions = {}
    for r in results:
        a = r.get("action_taken", "UNKNOWN")
        actions[a] = actions.get(a, 0) + 1
    
    print("\n📊 Summary:")
    for action, count in actions.items():
        print(f"  {action}: {count} tickets")

if __name__ == "__main__":
    main()