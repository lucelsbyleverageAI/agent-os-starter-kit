from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI


def get_default_model():
    # Avoid passing temperature for gpt-5; rely on provider defaults
    # return ChatOpenAI(model_name="gpt-5", max_tokens=None, timeout=None, max_retries=3)
    return ChatAnthropic(model_name="claude-sonnet-4-20250514", max_tokens=64000)