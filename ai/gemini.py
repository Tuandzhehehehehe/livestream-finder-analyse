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
        model=None
    ):
        # Danh sách các model để luân phiên (Fallback Models)
        self.models = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite-preview-02-05",
            "gemini-2.5-pro"
        ]
        if model:
            if model in self.models:
                self.models.remove(model)
            self.models.insert(0, model)

        self.client = genai.Client(
            api_key=API_KEY
        )

    def generate(
        self,
        prompt: str
    ):
        import time
        import re
        
        last_exception = None
        
        # Thử luân phiên các model khác nhau
        for current_model in self.models:
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    return self.client.models.generate_content(
                        model=current_model,
                        contents=prompt
                    )
                except Exception as e:
                    last_exception = e
                    error_msg = str(e)
                    
                    if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                        # Nếu hết quota model này, lập tức break vòng lặp attempt để chuyển sang model khác
                        print(f"[Gemini] Quota exceeded on {current_model}. Switching to next model...")
                        break 
                    elif "NOT_FOUND" in error_msg or "404" in error_msg:
                        print(f"[Gemini] Model {current_model} not found/supported. Switching to next model...")
                        break
                    else:
                        # Lỗi khác thì raise luôn
                        raise e
            
            # Nếu vòng lặp trên bị break do 429, vòng lặp model sẽ tiếp tục với model tiếp theo.
            
        # Nếu đã thử hết tất cả các models mà vẫn lỗi, thì bắt đầu chờ (sleep)
        wait_time = 15
        match = re.search(r"retry in ([0-9.]+)s", str(last_exception))
        if match:
            try:
                wait_time = float(match.group(1)) + 1.0
            except:
                pass
        print(f"[Gemini] ALL models exhausted! Must sleep for {wait_time:.1f}s...")
        time.sleep(wait_time)
        
        # Thử lại lần cuối với model nhẹ nhất
        return self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )