from abc import ABC, abstractmethod
import os

class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> tuple[str, int]:
        """
        Takes a prompt and returns a tuple of (response_text, token_usage).
        """
        pass

class MockLLMClient(LLMClient):
    """A deterministic client for testing. Returns fixed responses and token counts."""
    def __init__(self, fixed_response: str = "This is a mocked response.", fixed_tokens: int = 150):
        self.fixed_response = fixed_response
        self.fixed_tokens = fixed_tokens
        
    def generate(self, prompt: str) -> tuple[str, int]:
        return self.fixed_response, self.fixed_tokens

class GeminiLLMClient(LLMClient):
    """Real implementation for Gemini using google-genai (supports both Vertex AI and Developer API)."""
    def __init__(self, api_key: str = None, model: str = None):
        # Universally fetch model name, no hardcoding
        self.model = model or os.environ.get("GEMINI_MODEL_NAME")
        if not self.model:
            raise ValueError("GEMINI_MODEL_NAME must be provided in environment variables.")
            
        try:
            from google import genai
            from google.genai import types
            
            project = os.environ.get("GOOGLE_CLOUD_PROJECT")
            location = os.environ.get("GOOGLE_CLOUD_LOCATION")
            
            if project:
                # If Vertex AI credentials are provided, use Enterprise Vertex AI
                self.client = genai.Client(
                    vertexai=True,
                    project=project,
                    location=location,
                    http_options=types.HttpOptions(timeout=60000)
                )
            else:
                # Fallback to standard Developer API
                self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
                if not self.api_key:
                    raise ValueError("Either Vertex AI credentials (GOOGLE_CLOUD_PROJECT) or GEMINI_API_KEY must be provided.")
                
                self.client = genai.Client(
                    api_key=self.api_key, 
                    http_options=types.HttpOptions(timeout=60000)
                )
                
        except ImportError:
            raise ImportError("Please install google-genai: pip install google-genai")

    def generate(self, prompt: str) -> tuple[str, int]:
        from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception
        from google.genai.errors import APIError
        
        def is_retryable_api_error(exception):
            """Only retry on 429 (Rate Limit) or 503 (Service Unavailable)"""
            if isinstance(exception, APIError):
                if exception.code in (429, 503):
                    return True
            return False

        @retry(
            wait=wait_random_exponential(multiplier=1, min=2, max=60),
            stop=stop_after_attempt(5),
            retry=retry_if_exception(is_retryable_api_error),
            reraise=True
        )
        def _call_api():
            return self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            
        response = _call_api()
        text = response.text
        # Extract token usage from the response metadata
        token_usage = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            token_usage = response.usage_metadata.total_token_count
            
        return text, token_usage
