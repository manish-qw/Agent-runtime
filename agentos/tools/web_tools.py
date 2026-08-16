import os
import urllib.request
import json
from dotenv import load_dotenv

def search_web(query: str) -> str:
    """Searches the web for a query and returns snippet results."""
    load_dotenv()
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        return "Error: SERPER_API_KEY not found in environment variables. Web search failed."
        
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query}).encode("utf-8")
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    try:
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            
            snippets = []
            for item in data.get("organic", [])[:3]:
                snippets.append(f"Title: {item.get('title')} | Snippet: {item.get('snippet')}")
            
            if not snippets:
                return "No results found."
            return "\n".join(snippets)
    except Exception as e:
        return f"Web search API error: {str(e)}"
