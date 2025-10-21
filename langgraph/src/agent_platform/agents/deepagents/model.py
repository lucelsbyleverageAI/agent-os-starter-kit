from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from agent_platform.utils.model_utils import init_model_simple


def get_default_model():
    # Use the centralized model initialization to ensure proper settings
    # This will use the default STANDARD tier model (Claude Sonnet 4.5) with correct max_tokens
    return init_model_simple()