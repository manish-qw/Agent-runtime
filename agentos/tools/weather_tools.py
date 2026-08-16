import os
import urllib.request
import urllib.parse
import json
from dotenv import load_dotenv

def get_weather(location: str) -> str:
    """Gets the current weather and temperature for a given location."""
    load_dotenv()
    api_key = os.environ.get("WEATHER_API_KEY")
    if not api_key:
        return "Error: WEATHER_API_KEY not found in environment variables. Weather lookup failed."
        
    encoded_loc = urllib.parse.quote(location)
    url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={encoded_loc}&aqi=no"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            temp = data["current"]["temp_c"]
            condition = data["current"]["condition"]["text"]
            return f"The current weather in {location} is {condition} and {temp}°C."
    except Exception as e:
        return f"Weather API error: {str(e)}"
