from agentos.llm.client import LLMClient

def research_agent_task(client: LLMClient, document: str) -> tuple[str, int]:
    """
    Reads a document and returns a summary using the provided LLM client.
    Returns (summary, token_count).
    """
    prompt = f"Please read the following document and provide a concise summary:\n\n{document}"
    return client.generate(prompt)

def coding_agent_task(client: LLMClient, question: str) -> tuple[str, int]:
    """
    Takes a coding question and returns a code solution using the provided LLM client.
    Returns (solution, token_count).
    """
    prompt = f"You are an expert programmer. Please write a clean, well-structured code solution for the following question:\n\n{question}"
    return client.generate(prompt)
