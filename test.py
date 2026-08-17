import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

key = os.getenv("OPENAI_API_KEY")
# print("key loaded:", bool(key), "length:", len(key) if key else 0)
# print("from .env length:", len(key) if key else None)
# print("hardcoded length:", len(hard))
# print("equal?:", key == hard)
# print("repr from .env:", repr(key))   # <-- this reveals hidden characters

client = OpenAI(
    base_url="https://bedrock-mantle.us-east-1.api.aws/v1",
    api_key=os.getenv("OPENAI_API_KEY"),
    default_headers={"OpenAI-Project": "proj_45u4rhzxyqx5ho7xdgpk"},
)

response = client.chat.completions.create(
    model="openai.gpt-oss-120b",
    messages=[
        {
            "role": "user",
            "content": "What is Amazon Bedrock?",
        },
    ],
    max_tokens=1024,
    reasoning_effort="low",
)

print(response.choices[0].message.content)

msg = response.choices[0].message
print("content:", msg.content)
# gpt-oss puts its thinking in a separate reasoning field; print it if content is empty
if hasattr(msg, "reasoning"):
    print("reasoning:", msg.reasoning)