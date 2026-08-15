import time
import threading

shutdown_event = threading.Event()

def sleep_agent(duration: int):
    """A dummy agent that sleeps for a given duration and succeeds."""
    time.sleep(duration)
    return f"Slept for {duration} seconds."

def exception_agent():
    """A dummy agent that immediately crashes."""
    raise RuntimeError("Intentional agent crash.")

def sleep_forever_agent():
    """A dummy agent that simulates a hung task.
    Literally loops forever, but safely breaks when pytest triggers the shutdown event."""
    while not shutdown_event.is_set():
        time.sleep(1)

class MultiStepAgent:
    """A stateful dummy agent that yields after each step."""
    def __init__(self, steps: int = 3):
        self.total_steps = steps
        self.current_step = 0
        
    def __call__(self):
        self.current_step += 1
        if self.current_step < self.total_steps:
            return "YIELD"
        return "COMPLETED"
