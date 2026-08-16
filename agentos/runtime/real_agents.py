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

def tool_calling_agent_task(store, agent_id: str, instructions: str, tools: list, simulate_crash: bool = False) -> tuple[str, int]:
    """
    A "True Agent" that executes a ReAct loop with manual tool calling and SQLite Checkpoints.
    It takes a Checkpoint snapshot AFTER EVERY SINGLE TOOL CALL.
    If it crashes, it will reload the history, reconstruct the Gemini Chat, and resume the loop.
    """
    from agentos.core.checkpoint import Checkpoint
    from agentos.core.state import AgentState
    from google import genai
    from google.genai import types
    import json
    
    # Initialize the raw genai client with hard socket timeout
    genai_client = genai.Client(http_options=types.HttpOptions(timeout=60000))
    
    checkpoint = store.load_checkpoint(agent_id)
    if not checkpoint:
        checkpoint = Checkpoint(agent_id=agent_id, state=AgentState.RUNNING)
        checkpoint.conversation_history = [{"role": "user", "text": instructions}]
        checkpoint.task_progress_marker = "running"
        store.save_checkpoint(checkpoint)
        
    total_tokens = 0
    
    while True:
        # 1. Reconstruct API Content Objects from Checkpoint History
        contents = []
        for msg in checkpoint.conversation_history:
            if "role" in msg and "parts" in msg:
                # Direct serialization format from SDK
                contents.append(types.Content.model_validate(msg))
            else:
                # Legacy fallback format
                if "text" in msg:
                    contents.append(types.Content(role=msg["role"], parts=[types.Part.from_text(text=msg["text"])]))
                elif "function_call" in msg:
                    call_data = msg["function_call"]
                    contents.append(types.Content(role=msg["role"], parts=[types.Part.from_function_call(name=call_data["name"], args=call_data["args"])]))
                elif "function_response" in msg:
                    resp_data = msg["function_response"]
                    contents.append(types.Content(role=msg["role"], parts=[types.Part.from_function_response(name=resp_data["name"], response=resp_data["response"])]))
                
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
            import os
            model_name = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
            return genai_client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=tools, 
                    temperature=0,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                )
            )
            
        # 2. Call the LLM with exponential jittered backoff
        response = _call_api()
        
        if response.usage_metadata:
            total_tokens += response.usage_metadata.total_token_count

        # 3. Process the Response Content
        if response.candidates and response.candidates[0].content:
            model_content = response.candidates[0].content
            
            # Save the exact model content (preserves thought_signatures and internal IDs)
            checkpoint.conversation_history.append(model_content.model_dump(exclude_none=True, mode='json'))
            store.save_checkpoint(checkpoint)
            
            has_calls = any(part.function_call for part in model_content.parts if part.function_call)
            
            if has_calls:
                # Execute all tools and collect their response parts
                response_parts = []
                for part in model_content.parts:
                    if part.function_call:
                        call = part.function_call
                        func_to_call = next((f for f in tools if f.__name__ == call.name), None)
                        
                        if not func_to_call:
                            result = {"error": f"Tool {call.name} not found"}
                        else:
                            try:
                                args = {k: v for k, v in call.args.items()} if call.args else {}
                                result = func_to_call(**args)
                                if not isinstance(result, dict):
                                    result = {"result": result}
                            except Exception as e:
                                result = {"error": str(e)}
                                
                        resp_part = types.Part.from_function_response(name=call.name, response=result)
                        # Gemini requires the response to have the same ID as the call
                        if hasattr(call, 'id') and call.id:
                            resp_part.function_response.id = call.id
                        response_parts.append(resp_part)
                
                # Append the combined user tool responses
                user_content = types.Content(role="user", parts=response_parts)
                checkpoint.conversation_history.append(user_content.model_dump(exclude_none=True, mode='json'))
                store.save_checkpoint(checkpoint)
                
                # SIMULATE A CRASH AFTER FIRST BATCH OF TOOL CALLS
                if simulate_crash and checkpoint.task_progress_marker == "running":
                    checkpoint.task_progress_marker = "crashed_once"
                    store.save_checkpoint(checkpoint)
                    raise Exception(f"Simulated crash after executing tools")
                
                # Loop back to API to pass the tool responses
                continue
            
            # 4. Handle Final Text Answer
            else:
                final_text = "".join([p.text for p in model_content.parts if p.text])
                checkpoint.task_progress_marker = "completed"
                checkpoint.state = AgentState.COMPLETED
                store.save_checkpoint(checkpoint)
                return final_text, total_tokens
                
        # Fallback if the LLM returns nothing
        return "Failed to complete (no text or function calls returned)", total_tokens
