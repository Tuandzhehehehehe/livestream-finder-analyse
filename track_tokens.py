import time
import json
import os
import sys

def main():
    log_file = os.path.join(os.path.dirname(__file__), "data", "token_usage.log")
    
    print("="*95)
    print("🚀 ĐANG THEO DÕI LƯỢNG TOKEN AI SỬ DỤNG THEO THỜI GIAN THỰC...")
    print("Nhấn Ctrl+C để dừng lại.")
    print("="*95)
    print(f"{'Thời gian':<10} | {'Category':<15} | {'Model':<22} | {'Prompt':<9} | {'Candidate':<9} | {'Total':<9}")
    print("-" * 95)
    
    if not os.path.exists(log_file):
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        open(log_file, "a").close()

    total_prompt = 0
    total_candidate = 0
    total = 0
    category_totals = {}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                    
                try:
                    data = json.loads(line)
                    t_str = time.strftime('%H:%M:%S', time.localtime(data.get('timestamp')))
                    model = data.get('model', 'unknown')
                    category = data.get('category', 'general')
                    p_tokens = data.get('prompt_tokens', 0)
                    c_tokens = data.get('candidate_tokens', 0)
                    t_tokens = data.get('total_tokens', 0)
                    
                    total_prompt += p_tokens
                    total_candidate += c_tokens
                    total += t_tokens
                    category_totals[category] = category_totals.get(category, 0) + t_tokens
                    
                    print(f"{t_str:<10} | {category:<15} | {model:<22} | {p_tokens:<9} | {c_tokens:<9} | {t_tokens:<9}")
                    sys.stdout.write(f"\r\033[K>> TỔNG CỘNG: {total_prompt} prompt | {total_candidate} candidate | {total} tokens")
                    sys.stdout.flush()
                    print("\n", end="")
                    
                except json.JSONDecodeError:
                    pass
    except KeyboardInterrupt:
        print("\n\n🛑 Đã dừng theo dõi.")
        print("="*95)
        print(f"TỔNG KẾT: {total_prompt} prompt | {total_candidate} candidate | {total} tokens")
        if category_totals:
            print("Phân bố theo mục đích (Category):")
            for cat, count in category_totals.items():
                print(f"  - {cat:<15}: {count:,} tokens ({(count/total*100):.1f}%)")
        print("="*95)

if __name__ == "__main__":
    main()

