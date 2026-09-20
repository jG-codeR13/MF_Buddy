"""
Phase 5: User Interface (Custom HTML/JS + Flask API)
=====================================================
Flask backend serving the custom Mutual Fund FAQ Assistant UI.

Endpoints:
- / : Serves the index.html frontend.
- /api/chat : Accepts POST requests with user query, returns RAG JSON.
"""

import os
import sys
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

# Add src/ to path so we can import rag_engine
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from rag_engine import query_rag

app = Flask(__name__)
CORS(app)  # Allow frontend to make requests

@app.route("/")
def index():
    """Serve the main frontend UI."""
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Handle chat queries from the frontend.
    Expects JSON: {"query": "User's question"}
    Returns JSON: {"answer": "...", "source_url": "...", "is_refused": bool, "footer": "..."}
    """
    data = request.get_json()
    if not data or "query" not in data:
        return jsonify({"error": "Missing 'query' field in request body."}), 400
    
    user_query = data["query"]
    
    # Process through the RAG engine
    try:
        result = query_rag(user_query)
        return jsonify(result)
    except Exception as e:
        error_msg = f"An unexpected error occurred with the AI providers: {str(e)}"
        print(f"ERROR: {error_msg}")
        return jsonify({
            "answer": error_msg,
            "source_url": None,
            "is_refused": True,
            "footer": None
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
