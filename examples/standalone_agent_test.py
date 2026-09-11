import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Import our custom tools
from agentos.tools.math_tools import add, multiply
from agentos.tools.fs_tools import list_files, read_file, write_file
from agentos.tools.web_tools import search_web
from agentos.tools.weather_tools import get_weather

def run_standalone_agent(name: str, instructions: str, tools: list):
    print(f"\n{'='*50}\nStarting Agent: {name}\n{'='*50}")
    
    client = genai.Client() # Uses GEMINI_API_KEY from environment
    
    # We use the recommended 'chats' interface for automatic function calling (AFC)
    chat = client.chats.create(
        model="gemini-3.1-flash-lite",
        config=types.GenerateContentConfig(
            temperature=0,
            tools=tools
        )
    )
    
    print(f"Goal: {instructions}\n")
    
    try:
        response = chat.send_message(instructions)
        # With AFC, the SDK handles the loop! It will call the python functions 
        # locally and send results back until the final text is ready.
        
        # Let's print out what happened by inspecting the chat history
        print("--- Execution History ---")
        for message in chat.get_history():
            role = message.role
            
            # Print text parts
            for part in message.parts:
                if part.text:
                    print(f"[{role.upper()}]: {part.text.strip()}")
                elif part.function_call:
                    func = part.function_call
                    args = {k: v for k, v in func.args.items()}
                    print(f"[TOOL_CALL]: {func.name}({args})")
                elif part.function_response:
                    resp = part.function_response
                    result_dict = {k: v for k, v in resp.response.items()}
                    print(f"[TOOL_RESULT]: {resp.name} returned {result_dict}")
                    
        print(f"\nFinal Answer: {response.text}")
    except Exception as e:
        print(f"Error during execution: {e}")

if __name__ == "__main__":
    load_dotenv()
    
    print("WARNING: This standalone test uses the `google-genai` SDK's Automatic Function Calling (AFC).")
    print("AFC does the entire tool loop in one blocking call, which is great for standard apps,")
    print("but BAD for AgentOS because it prevents us from taking mid-loop Checkpoints.")
    print("If it crashes, we lose everything! (We will manually re-implement the loop in AgentOS later).")
    
    # 1. Math Agent
    run_standalone_agent(
        name="Calculator Agent",
        instructions="If John has 5 apples, buys 3 more, then multiplies his stash by 4, how many does he have? You MUST use the add and multiply tools.",
        tools=[add, multiply]
    )
    
    # 2. File System Agent
    # Setup a dummy file first
    with open("dummy_log.txt", "w") as f:
        f.write("System OK. Error: Network timeout on port 8080. System OK.")
        
    run_standalone_agent(
        name="File System Agent",
        instructions="List the files in the current directory ('.'). Find the file named 'dummy_log.txt', read it, summarize the error you find, and write that summary into a new file called 'report.txt'.",
        tools=[list_files, read_file, write_file]
    )
    
    # 3. Web & Weather Agent
    run_standalone_agent(
        name="Real-World Agent",
        instructions="What is the current weather in Tokyo? After finding out, search the web for 'things to do in Tokyo when it is [insert weather condition here]'.",
        tools=[get_weather, search_web]
    )
