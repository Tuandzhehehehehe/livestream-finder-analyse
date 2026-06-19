import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

if not API_KEY:
    raise Exception(
        "GEMINI_API_KEY not found in .env"
    )


class Gemini:

    def __init__(
        self,
        model="gemini-2.5-flash"
    ):

        self.model = model

        self.client = genai.Client(
            api_key=API_KEY
        )

    def generate(
        self,
        prompt: str
    ):

        return self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )