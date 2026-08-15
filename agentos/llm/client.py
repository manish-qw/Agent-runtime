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
    """Real implementation for Gemini 2.5 Flash Lite using google-genai."""
    def __init__(self, api_key: str = None, model: str = "gemini-3.1-flash-lite"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be provided or set in environment variables.")
        self.model = model
        
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
        except ImportError:
            raise ImportError("Please install google-genai: pip install google-genai")

    def generate(self, prompt: str) -> tuple[str, int]:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        text = response.text
        # Extract token usage from the response metadata
        token_usage = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            token_usage = response.usage_metadata.total_token_count
            
        return text, token_usage
