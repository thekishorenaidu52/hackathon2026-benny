## ShopWave Autonomous Support Agent
## Ksolves Agentic AI Hackathon 2026
An autonomous customer support agent that resolves ShopWave support tickets without human intervention. Not a demo. Not a toy. Something real.

## Tech Stack
Python 3.12
Google Gemini 2.5 Flash (LLM)
concurrent.futures (concurrency)
python-dotenv (config)

## Setup & Run
1. Clone the repo
git clone https://github.com/thekishorenaidu52/hackathon2026-benny
cd hackathon2026-benny
2. Install dependencies
py -m pip install google-generativeai python-dotenv
3. Add API Key
Create a .env file in root folder:
GEMINI_API_KEY=your_gemini_api_key_here
4. Run the agent
py agent.py

## Project Structure
hackathon2026-benny/
├── agent.py              # Main agent - single entry point
├── README.md             # This file
├── architecture.png      # Agent loop diagram
├── failure_modes.md      # Failure scenarios
├── audit_log.json        # Auto-generated after run
├── results_summary.json  # Auto-generated after run
└── data/
    ├── tickets.json       # 20 mock support tickets
    ├── orders.json        # Order database
    ├── customers.json     # Customer database
    ├── products.json      # Product database
    └── knowledge_base.md  # ShopWave policies
    
## How The Agent Works
Agent Loop

Reads all 20 support tickets concurrently (ThreadPoolExecutor)
For each ticket runs a ReAct reasoning loop:

get_customer → fetch customer profile and tier
get_order → fetch order details
get_product → fetch product info
search_knowledge_base → find relevant policies
Gemini AI decides action based on all context


Executes the decision (refund / reply / escalate / cancel)
Logs every tool call, reasoning and outcome to audit_log.json

## Tools Available
ToolTypeDescriptionget_orderREADOrder details, status, timestampsget_customerREADCustomer profile, tier, historyget_productREADProduct metadata, warranty, return windowsearch_knowledge_baseREADPolicy and FAQ searchcheck_refund_eligibilityWRITEReturns eligibility + reasonissue_refundWRITEIRREVERSIBLE - issues refundsend_replyWRITESends response to customerescalateWRITERoutes to human with full context
Decisions The Agent Makes

ISSUE_REFUND - Customer eligible, amount under $200
ESCALATE - Warranty claim, replacement request, fraud, amount over $200, low confidence
SEND_REPLY - General questions, policy info, clarification needed
CANCEL_ORDER - Order in processing status
DENY - Not eligible per policy

Agent Constraints Met

Chain: Minimum 3 tool calls per ticket (get_customer → get_order → get_product → search_kb)
Concurrency: All tickets processed in parallel using ThreadPoolExecutor
Recovery: Handles timeouts with retry, malformed data gracefully, API failures with fallback
Explainability: Every decision logged with full reasoning, confidence score, and tool call history

## Biggest Challenge
Getting the agent to handle concurrent processing while respecting API rate limits. Solved by limiting max_workers to 2 and adding delays between requests.
## Author
Benny (thekishorenaidu52)
Ksolves Agentic AI Hackathon 2026