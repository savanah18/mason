import os

DEFAULT_PERSONA = "chat"
DEFAULT_AGENT_MODE = "dev"

def get_persona():
    return os.getenv("PERSONA",DEFAULT_PERSONA)

def get_agent_mode():
    return os.getenv("AGENT_MODE",DEFAULT_AGENT_MODE)