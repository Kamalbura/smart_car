import os
from openai import AzureOpenAI


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"").strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        return

_load_dotenv()

endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://1602--mkvc2jiy-eastus2.cognitiveservices.azure.com/")
deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")
api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

if not api_key:
    raise RuntimeError("AZURE_OPENAI_API_KEY is not set")

client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=api_key,
)

completion = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"},
    ],
    max_completion_tokens=256,
)

print(completion.choices[0].message.content)