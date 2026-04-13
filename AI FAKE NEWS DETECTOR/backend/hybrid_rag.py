import os
import json
import logging
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

import endee
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
import requests
from tavily import TavilyClient

# Load environment variables
load_dotenv()

# Initialize Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
CHROMA_DB_DIR = "./chroma_db"
COLLECTION_NAME = "news_facts"

# 1. Initialize Clients (Handle Missing Keys with Mock Fallbacks)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
SAFE_BROWSING_API_KEY = os.environ.get("GOOGLE_SAFE_BROWSING_API_KEY")

# Endee Vector Database (Local or Cloud Integration)
ENDEE_API_KEY = os.environ.get("ENDEE_API_KEY")
ENDEE_URL     = os.environ.get("ENDEE_URL", "http://localhost:8080")

try:
    if ENDEE_API_KEY and ENDEE_API_KEY != "your_endee_api_key_here":
        logger.info("Initializing Endee Vector Database cloud client...")
        endee_client = endee.Client(api_key=ENDEE_API_KEY)
        collection = endee_client.get_or_create_collection(name=COLLECTION_NAME)
    elif ENDEE_URL:
        logger.info(f"Initializing Local Endee Vector Database at {ENDEE_URL}...")
        endee_client = endee.Client(url=ENDEE_URL)
        collection = endee_client.get_or_create_collection(name=COLLECTION_NAME)
    else:
        logger.warning("No Endee API Key or local URL found. Operating in mock mode.")
        collection = None
except Exception as e:
    logger.error(f"Error initializing Endee DB: {e}")
    collection = None

# 2. Web Safety Layer
def check_safe_browsing(url: str) -> str:
    if not url:
        return "Safe"
        
    if not SAFE_BROWSING_API_KEY or SAFE_BROWSING_API_KEY == "your_safe_browsing_api_key_here":
        logger.warning("Mocking Safe Browsing API check. Missing key.")
        return "Suspicious" if "scam" in url.lower() or "free" in url.lower() else "Safe"
        
    api_url = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={SAFE_BROWSING_API_KEY}"
    payload = {
        "client": {"clientId": "fakenews-detector", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}]
        }
    }
    
    try:
        response = requests.post(api_url, json=payload, timeout=5)
        if response.status_code == 200:
            result = response.json()
            if result and "matches" in result:
                return "Dangerous"
        return "Safe"
    except Exception as e:
        logger.error(f"Safe Browsing API error: {e}")
        return "Unknown"

# 3. Vector DB Search
def search_vector_db(query: str) -> List[str]:
    if not collection:
        return []
    try:
        # Search the Endee Cloud Database using the Python SDK
        results = collection.search(
            query=query,
            top_k=2
        )
        if results and getattr(results, "documents", None):
            return results.documents
        return []
    except Exception as e:
        logger.error(f"Endee DB Search error: {e}")
        return []

# 3.5. Vector DB Store
def store_fact_in_endee(text: str, url: str) -> bool:
    if not collection:
        return False
    try:
        import hashlib, datetime
        doc_id = hashlib.md5(text.encode()).hexdigest()
        
        # Upsert into Endee Cloud
        collection.upsert(
            documents=[{
                "id": doc_id,
                "text": text,
                "metadata": {
                    "url": url,
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }
            }]
        )
        logger.info(f"Successfully stored fact in Endee DB: {doc_id}")
        return True
    except Exception as e:
        logger.error(f"Endee DB Store error: {e}")
        return False

# 4. Live Web Search
def perform_live_web_search(query: str) -> Dict[str, Any]:
    if not TAVILY_API_KEY or TAVILY_API_KEY == "your_tavily_api_key_here":
        logger.warning("Mocking Tavily Web Search. Missing key.")
        return {
            "context": "Recent reports highlight the complexities of this news story. Multiple sources provide conflicting information, but major outlets report details reflecting a measured truth.",
            "sources": ["https://news.mock.com/report1", "https://news.mock.com/report2"]
        }
        
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
        response = tavily.search(query=query, search_depth="basic", max_results=3)
        context = " ".join([result['content'] for result in response.get('results', [])])
        sources = [result['url'] for result in response.get('results', [])]
        return {"context": context, "sources": sources}
    except Exception as e:
        logger.error(f"Tavily API error: {e}")
        return {"context": "", "sources": []}

# 5. Core RAG Synthesizer
def synthesize_and_verify(text: str, url: str, vector_context: List[str], web_context: str) -> Dict[str, Any]:
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_gemini_api_key_here":
        # Mock LLM logic
        logger.warning("Mocking LLM Synthesis. Missing key.")
        content = (text + url).lower()
        if "shocking" in content or "conspiracy" in content:
            verdict = "Fake"
            confidence = 88.5
        elif "rumor" in content or "unconfirmed" in content:
            verdict = "Misleading"
            confidence = 65.0
        else:
            verdict = "Real"
            confidence = 92.0
            
        return {
            "verdict": verdict,
            "confidence": confidence,
            "explanation": "Based on simulated RAG pipeline analysis."
        }
        
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1)
    
    prompt = PromptTemplate(
        input_variables=["text", "url", "vector_context", "web_context"],
        template="""
        You are an expert Fake News verification system.
        Analyze the following input:
        Text: {text}
        URL: {url}
        
        Information from local vector DB validation:
        {vector_context}
        
        Information from Live Web Search:
        {web_context}
        
        Task: Cross-reference the input with the provided contexts. Determine if it's Real, Fake, or Misleading.
        Provide a confidence score between 0.0 and 100.0.
        
        Return exactly in JSON format:
        {{
            "verdict": "Real" | "Fake" | "Misleading",
            "confidence": float,
            "explanation": "Brief explanation of your finding."
        }}
        """
    )
    
    try:
        formatted_prompt = prompt.format(
            text=text or "None", 
            url=url or "None", 
            vector_context="; ".join(vector_context) if vector_context else "No local matches.", 
            web_context=web_context or "No web results."
        )
        response = llm.invoke(formatted_prompt)
        
        # Parse JSON
        result_str = response.content.strip().replace('```json', '').replace('```', '')
        result_json = json.loads(result_str)
        return result_json
        
    except Exception as e:
        logger.error(f"LLM Processing error: {e}")
        return {"verdict": "Misleading", "confidence": 50.0, "explanation": "Analysis failed due to LLM error."}

# Main Execution Function
def analyze_with_rag(text: str = "", url: str = "") -> Dict[str, Any]:
    # 1. Safety Check
    safety_status = check_safe_browsing(url) if url else "Safe"
    
    query_target = text if text else url
    
    # 2. Vector DB Sync
    v_context = search_vector_db(query_target)
    
    # 3. Web Search
    w_search_data = perform_live_web_search(query_target)
    
    # 4. Synthesize
    llm_result = synthesize_and_verify(text, url, v_context, w_search_data["context"])
    
    # Compile final result
    return {
        "prediction": llm_result.get("verdict", "Real"),
        "confidence": float(llm_result.get("confidence", 50.0)),
        "safety_status": safety_status,
        "sources": w_search_data.get("sources", []),
        "explanation": llm_result.get("explanation", "")
    }

if __name__ == "__main__":
    # Test block
    res = analyze_with_rag(text="The moon is made of cheese", url="")
    print(res)
