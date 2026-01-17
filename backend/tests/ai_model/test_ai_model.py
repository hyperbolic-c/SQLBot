from openai import OpenAI

client = OpenAI(
    base_url='https://api-inference.modelscope.cn/v1',
    api_key='ms-5f84f678-c565-4e9e-ab42-5244ce4ce74b', # ModelScope Token
)

response = client.chat.completions.create(
    model='Qwen/Qwen3-Coder-30B-A3B-Instruct', # ModelScope Model-Id
    messages=[
        {
            'role': 'system',
            'content': 'You are a helpful assistant.'
        },
        {
            'role': 'user',
            'content': '你好'
        }
    ],
    stream=True
)

for chunk in response:
    if chunk.choices:
        print(chunk.choices[0].delta.content, end='', flush=True)