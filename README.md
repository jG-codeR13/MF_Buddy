# Mutual Fund AI Assistant (RAG Pipeline) 🚀

A real-time Retrieval-Augmented Generation (RAG) chatbot designed to accurately answer mutual fund queries based strictly on scraped data from verified sources.

**🔗 Prototype Link:** [https://mutual-fund-assistant-t3vv.onrender.com/](https://mutual-fund-assistant-t3vv.onrender.com/)

This project features a modern glassmorphism UI and a robust Flask backend that processes queries against a local ChromaDB vector database using `fastembed`.

---

## 🎯 Project Scope

This assistant is designed to answer factual queries regarding the following **5 specific Mutual Funds** from 4 different AMCs:
1. **Bandhan AMC:** Bandhan Small Cap Fund
2. **PPFAS AMC:** Parag Parikh Long Term Value Fund (Flexi Cap)
3. **HDFC AMC:** HDFC Mid-Cap Opportunities Fund
4. **HDFC AMC:** HDFC Flexi Cap Fund
5. **Nippon India AMC:** Nippon India Large Cap Fund

## 🚧 Known Limits
- **Data Freshness:** The knowledge base is updated daily at 10:30 AM IST via a GitHub Actions cron job. Real-time intraday NAV fluctuations are not captured.
- **Cold Starts:** Hosted on Render's Free Tier. If the app hasn't been used in 15 minutes, the first query may take ~50 seconds to respond as the server spins up.
- **Memory Constraint:** Uses the lightweight `fastembed` library to perform on-device embeddings without exceeding Render's 512MB free RAM limit.

---

## 🌟 Features
- **Facts-Only Guardrails**: The LLM uses a two-layer classification system (Regex + LLM Intent Detection) to strictly refuse speculative investment advice or performance predictions.
- **Automated Data Pipeline**: A GitHub Actions workflow runs every day to scrape the latest data, update the vector database (`/chroma_db`), and commit the fresh data as "Database-as-Code".
- **Local Embeddings**: Uses `fastembed` (ONNX) to generate high-quality embeddings entirely locally, bypassing third-party API rate limits and DNS errors.

## 🛠️ Architecture

1. **Scraper (`src/ingestion.py`)**: Fetches live mutual fund scheme pages from Groww.
2. **Chunker (`src/chunking.py`)**: Parses the raw HTML to Markdown, extracting key financial metrics.
3. **Embedder (`src/embed_and_store.py`)**: Uses `fastembed` to convert text into vectors stored in ChromaDB.
4. **Backend (`app.py`)**: A Flask API that queries ChromaDB and routes context to a Groq LLM (Llama-3.3-70b-versatile).
5. **Frontend (`templates/index.html`)**: A beautiful, vanilla JS & Tailwind CSS interface.

---

## 📋 Source List (URLs Used)

| # | Fund Name | Source URL |
|---|-----------|-----------|
| 1 | Bandhan Small Cap Fund | https://groww.in/mutual-funds/bandhan-small-cap-fund-direct-growth |
| 2 | Parag Parikh Long Term Value Fund | https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth |
| 3 | HDFC Mid-Cap Opportunities Fund | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| 4 | HDFC Flexi Cap Fund | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 5 | Nippon India Large Cap Fund | https://groww.in/mutual-funds/nippon-india-large-cap-fund-direct-growth |

---

## 💬 Sample Q&A

Sample queries showcasing the assistant's ability to extract facts with accurate citations, while strictly refusing advisory or speculative questions with polite safe-refusals.

### Factual Queries (Answered)

**Q: What is the expense ratio of HDFC Flexi Cap Fund?**
> **A:** The expense ratio of the HDFC Flexi Cap Fund is 0.77% for the Direct Plan.
> 
> Source: https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth
> _Last updated from sources: 2026-07-11_

**Q: Who is the fund manager of Bandhan Small Cap Fund?**
> **A:** The fund manager for the Bandhan Small Cap Fund is Mr. Manish Gunwani.
> 
> Source: https://groww.in/mutual-funds/bandhan-small-cap-fund-direct-growth
> _Last updated from sources: 2026-07-11_

**Q: What is the minimum SIP amount for Nippon India Large Cap Fund?**
> **A:** The minimum SIP investment for the Nippon India Large Cap Fund is ₹100.
> 
> Source: https://groww.in/mutual-funds/nippon-india-large-cap-fund-direct-growth
> _Last updated from sources: 2026-07-11_

**Q: Is there a lock-in period for Parag Parikh Long Term Value Fund?**
> **A:** No, there is no lock-in period for the Parag Parikh Long Term Value Fund (Flexi Cap Fund).
> 
> Source: https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth
> _Last updated from sources: 2026-07-11_

### Advisory & Speculative Queries (Safely Refused)

**Q: Should I invest in HDFC Mid-Cap Opportunities Fund?**
> **A:** I'm a facts-only assistant and cannot provide investment advice, opinions, or recommendations. For guidance on investing, please consult a SEBI-registered investment advisor or visit:
> - AMFI: https://www.amfiindia.com/investor-corner/knowledge-center.html
> - SEBI Investor Education: https://investor.sebi.gov.in/

**Q: Which fund is better, HDFC Flexi Cap or Nippon India Large Cap?**
> **A:** I'm a facts-only assistant and cannot provide investment advice, opinions, or recommendations. For guidance on investing, please consult a SEBI-registered investment advisor or visit:
> - AMFI: https://www.amfiindia.com/investor-corner/knowledge-center.html
> - SEBI Investor Education: https://investor.sebi.gov.in/

**Q: Will small cap funds give me 20% returns next year?**
> **A:** I'm a facts-only assistant and cannot provide investment advice, opinions, or recommendations. For guidance on investing, please consult a SEBI-registered investment advisor or visit:
> - AMFI: https://www.amfiindia.com/investor-corner/knowledge-center.html
> - SEBI Investor Education: https://investor.sebi.gov.in/

---

## 🚀 Setup & Local Deployment

### Prerequisites
- Python 3.9+
- A [Groq API Key](https://console.groq.com/keys)

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/SPSahoo007/MF-RAG_Chatbot.git
   cd MF-RAG_Chatbot
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables:
   Copy `.env.example` to `.env` and insert your API key:
   ```env
   GROQ_API_KEY=gsk_your_groq_key_here
   ```

### Running the App
Start the Flask server:
```bash
python app.py
```
Then navigate to `http://127.0.0.1:7860` in your browser.

---

## ☁️ Cloud Deployment (Render.com)
This app is heavily optimized for a standard web server on **Render.com** using `fastembed` to bypass memory limitations.
1. Create a free account on [Render](https://render.com/).
2. Click **New +** and select **Web Service**.
3. Connect your GitHub account and select this repository.
4. Set the Start Command to: `gunicorn app:app`
5. Add your `GROQ_API_KEY` to the Environment Variables.
6. Click **Deploy Web Service**!

---

## ⚠️ Disclaimer
This tool is for **educational purposes only**. It is strictly built to demonstrate Retrieval-Augmented Generation (RAG) techniques and **does not constitute financial advice**. The assistant provides factual data extracted from publicly available web pages and refuses to offer investment recommendations, performance predictions, or opinions. Always consult a SEBI-registered financial advisor before making investment decisions.

**UI Disclaimer (shown to users):**
```
AI-GENERATED CONTENT. STRICTLY FOR EDUCATIONAL PURPOSES. CONSULT A SEBI-REGISTERED FINANCIAL ADVISOR BEFORE INVESTING.
```

## 📄 License
This project is licensed under the MIT License.
