# Kasa AI 🚀
### Autonomous AI Negotiation & Instant On-Chain Settlement

**A submission for the Pro Hackathon 2026 Genesis Track · Rise In × Stellar**

---

## 🌟 Overview
**Kasa AI** is a next-generation autonomous payment orchestrator designed to eliminate the friction of financial disputes and invoice reconciliation. By leveraging **Gemini 1.5 Flash** agents and the **Stellar Network**, Kasa AI automates complex negotiations for both B2B procurement and B2C customer returns.

The system doesn't just talk—it settles. Every successful negotiation culminates in an automated on-chain transaction via **Stellar SEP-6**, ensuring that once agents agree on a price, the money moves instantly and transparently.

---

## ✨ Key Features

### 🤝 Dual-Agent Negotiation Protocol
Watch in real-time as a "Buyer Agent" and a "Seller Agent" negotiate terms over WebSockets. They analyze budgets, rules, and market conditions to reach a fair "Deal" without human intervention.

### 🧠 RAG-Driven Corporate Memory
Our agents aren't just smart; they have memory. Using **Retrieval-Augmented Generation (RAG)**, agents consult past invoices and supplier history to detect price gouging or favorable loyalty terms.

### 🛡️ Multi-Sig CFO Safeguards
For high-value transactions or suspicious anomalies, Kasa AI triggers a **Multi-Sig sequence**. The payment is frozen on the Stellar ledger until a human administrator (CFO) provides the second signature via a secure dashboard.

### 💸 Autonomous Split Refunds (B2C)
Kasa AI introduces the **Karma İade (Split Refund)** logic. If a customer wants a partial cash refund and partial store credit, the agents calculate the split, verify return shipping requirements, and execute the SEP-6 offramp for the cash portion automatically.

### 🌍 Fully Bilingual (TR/EN)
A unified interface and backend that supports seamless switching between Turkish and English. The AI agents dynamically adjust their negotiation tone, language, and cultural nuances based on the user's preference.

---

## 🏗️ Architecture & Tech Stack

- **Backend:** Python / FastAPI (High-performance asynchronous API)
- **AI Engine:** Gemini 1.5 Flash (Optimized for speed and complex reasoning)
- **Blockchain:** Stellar SDK (SEP-6 Offramps, SEP-10 Authentication, Multi-Sig Transactions)
- **Frontend:** React / Vite / Tailwind CSS (Real-time agent console via WebSockets)
- **Storage:** In-memory store with persistent RAG vectors for invoice history.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.9+
- Node.js 18+
- A Google AI (Gemini) API Key

### 2. Environment Configuration
Create a `.env` file in the `backend/` directory:
```env
GEMINI_API_KEY=your_gemini_key_here
STELLAR_NETWORK=TESTNET
```

### 3. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m app.main
```
*The backend will run on `http://127.0.0.1:8000`*

### 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
*The frontend will run on `http://127.0.0.1:5173`*

---

## 🛠️ Usage Flow
1. **Onboarding:** Connect your Stellar wallet or let the system auto-generate a funded Testnet account for you.
2. **Define Rules:** Set your corporate spending limits (e.g., "Max 500 TL for office supplies").
3. **Trigger Negotiation:** Submit a B2B invoice or start a B2C return request.
4. **The Console:** Open the **Agent Console** to see the agents battle it out for the best price.
5. **Settlement:** Once a "DEAL" is reached, verify the transaction on the Stellar Expert explorer.

---

**Developed with ❤️ for the Stellar Community.**
