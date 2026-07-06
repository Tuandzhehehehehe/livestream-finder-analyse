import time
import json
import os
import sys

def main():
    log_file = os.path.join(os.path.dirname(__file__), "data", "token_usage.log")
    
    print("="*80)
    print("🚀 ĐANG THEO DÕI LƯỢNG TOKEN AI SỬ DỤNG THEO THỜI GIAN THỰC...")
    print("Nhấn Ctrl+C để dừng lại.")
    print("="*80)
    print(f"{'Thời gian':<12} | {'Model':<20} | {'Prompt':<10} | {'Candidate':<10} | {'Total':<10}")
    print("-" * 80)
    
    if not os.path.exists(log_file):
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        open(log_file, "a").close()

    total_prompt = 0
    total_candidate = 0
    total = 0

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # Nhảy đến cuối file để chỉ đọc dữ liệu mới
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
                    p_tokens = data.get('prompt_tokens', 0)
                    c_tokens = data.get('candidate_tokens', 0)
                    t_tokens = data.get('total_tokens', 0)
                    
                    total_prompt += p_tokens
                    total_candidate += c_tokens
                    total += t_tokens
                    
                    print(f"{t_str:<12} | {model:<20} | {p_tokens:<10} | {c_tokens:<10} | {t_tokens:<10}")
                    # Xoá dòng cũ và in đè dòng tổng lên
                    sys.stdout.write(f"\r\033[K>> TỔNG CỘNG: {total_prompt} prompt | {total_candidate} candidate | {total} tokens")
                    sys.stdout.flush()
                    print("\n", end="") # Nhích xuống một dòng để chờ in kết quả tiếp theo
                    
                except json.JSONDecodeError:
                    pass
    except KeyboardInterrupt:
        print("\n\n🛑 Đã dừng theo dõi.")
        print("="*80)
        print(f"TỔNG KẾT: {total_prompt} prompt | {total_candidate} candidate | {total} tokens")
        print("="*80)

if __name__ == "__main__":
    main()
