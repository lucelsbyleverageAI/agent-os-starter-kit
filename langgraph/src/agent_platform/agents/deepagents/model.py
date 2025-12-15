from langchain_openai import ChatOpenAI
from agent_platform.utils.model_utils import init_model_simple


def get_default_model():
    """Get default model instance via OpenRouter.

    Uses the centralized model initialization to ensure proper settings.
    Default is Claude Sonnet 4 via OpenRouter.
    """
    return init_model_simple()