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

def multi_step_research_agent_task(client: LLMClient, store, agent_id: str, document: str) -> tuple[str, int]:
    """
    A multi-step task that reads a document, extracts keywords, and then summarizes it.
    It saves its progress to a Checkpoint so it can resume if crashed.
    """
    from agentos.core.checkpoint import Checkpoint
    from agentos.core.state import AgentState

    # Load existing checkpoint if it exists
    checkpoint = store.load_checkpoint(agent_id)
    if not checkpoint:
        checkpoint = Checkpoint(agent_id=agent_id, state=AgentState.RUNNING)

    total_tokens = 0

    # STEP 1: Extract Keywords
    if checkpoint.task_progress_marker == "init":
        prompt1 = f"Extract exactly 3 keywords from this document:\n\n{document}"
        keywords, tokens = client.generate(prompt1)
        total_tokens += tokens
        
        checkpoint.conversation_history.append(f"Keywords: {keywords}")
        checkpoint.task_progress_marker = "keywords_extracted"
        store.save_checkpoint(checkpoint)

    # Simulate a crash here during the test by raising an exception if specifically requested
    # (The test will handle this by injecting a poison document or checking history)
    if "CRASH_MIDWAY" in document and checkpoint.task_progress_marker == "keywords_extracted" and "Resumed" not in document:
        raise Exception("Simulated crash after step 1")

    # STEP 2: Summarize
    if checkpoint.task_progress_marker == "keywords_extracted":
        keywords = checkpoint.conversation_history[-1]
        prompt2 = f"Based on these keywords ({keywords}), summarize the original document:\n\n{document}"
        summary, tokens = client.generate(prompt2)
        total_tokens += tokens
        
        checkpoint.conversation_history.append(f"Summary: {summary}")
        checkpoint.task_progress_marker = "completed"
        store.save_checkpoint(checkpoint)
        
        return summary, total_tokens

    # If already completed
    return checkpoint.conversation_history[-1], total_tokens
