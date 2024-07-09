import openai
import os
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPAENAI_API_KEY")

def analyze_achievement(text):
    try:
        response = openai.Completion.create(
            engine='text-davinci-003',
            prompt=text,
            max_tokens=150,
        )
        return response.choices[0].text.strip()
    except Exception as e:
        return f'Error: {e}'
