from ai.gemini import Gemini
import json

exhausted_models = set()

def generate_comments(title: str, description: str, goal: str = ""):
    prompt = f"""
You are an expert attendee at a professional livestream/webinar. Your goal is to write 3 engaging, highly specific comments or questions to post in the livestream chat. 
You must sound like a real human professional, NOT an AI bot.

CRITICAL RULES:
1. NO GENERIC PHRASES: Do not use phrases like "Fascinating topic", "Great point", "I'm looking forward to", "Thanks for sharing", or "Can you expand on this".
2. BE SPECIFIC: Your comment MUST mention specific concepts, problems, or details mentioned in the Title or Description. If the topic is about "AI in HR", ask a very specific question about "bias in AI screening" or "adoption resistance", rather than a general "how does AI help HR?".
3. HUMAN TONE: Write casually but professionally, exactly as someone typing in a live chat. Keep it concise (1-2 sentences). You can use slight abbreviations or conversational transitions.
4. MATCH LANGUAGE: Write the comments in the same language as the Livestream Title and Description.
5. GOAL ALIGNMENT: Subtly align with the user's networking goal if provided, but prioritize relevance to the livestream topic.

User's Networking Goal: {goal if goal else 'Learn specific actionable insights and connect with experts'}

Livestream Title:
{title}

Livestream Description:
{description}

Return ONLY valid JSON in the following format:
{{
  "suggestions": [
    "Comment/Question 1",
    "Comment/Question 2",
    "Comment/Question 3"
  ]
}}
"""
    
    gemini_models = ["gemini-2.5-flash"]
    
    for model in gemini_models:
        if model in exhausted_models:
            continue
            
        try:
            print(f"[AI Comments] Gemini: {model}")
            gemini = Gemini(model)
            response = gemini.generate(prompt)
            
            text = response.text.strip()
            if text.startswith("```json"):
                text = text.replace("```json", "", 1)
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            result = json.loads(text)
            return result.get("suggestions", [])
            
        except Exception as e:
            error = str(e)
            if "RESOURCE_EXHAUSTED" in error or "429" in error:
                print(f"[AI Comments] Warning: Quota exhausted on {model}")
                exhausted_models.add(model)
                break
            print(f"[AI Comments] Gemini Error: {error}")
            
    # Fallback
    return [
        "Thấy chủ đề này khá thú vị, không biết thực tế triển khai có hay gặp rào cản gì không mọi người?",
        "Góc nhìn rất thực tế. Cho mình hỏi thêm về case study cụ thể ở mảng này được không?",
        "Phần này mình cũng đang quan tâm. Mọi người thường dùng công cụ gì để giải quyết bài toán này?"
    ]
