import sys
import io
import time
import json
from guard import ChatbotGuard
from classifier import ChatbotClassifier
from Skills.Skill_manager import SkillManager
from llm_client import llm_client

# Đảm bảo đầu ra UTF-8
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except:
    pass

class ChatbotOrchestrator:
    def __init__(self):
        self.guard = ChatbotGuard()
        self.classifier = ChatbotClassifier()
        self.skill_manager = SkillManager()

    def handle_request(self, user_query: str, history: str = ""):
        print(f"\n{'='*50}")
        print(f"PF CHATBOT (AGENT SKILL) PROCESSING: {user_query}")
        print(f"{'='*50}")
        
        t0 = time.time()
        
        # 1. Guard (Bảo mật)
        print(" [Guard] Đang kiểm tra bảo mật...")
        t_guard_start = time.time()
        guard_res = self.guard.check(user_query, history)
        t_guard = time.time() - t_guard_start
        
        if guard_res.get("allow") == "not_allow":
            print(f" BLOCK: {guard_res.get('reason')}")
            print(f"\n PHẢN HỒI:")
            print(f"{'-'*30}")
            print(guard_res.get("public_response", "Yêu cầu không được phép vì lý do an toàn."))
            print(f"{'-'*30}\n")
            return
        
        # 2. Classifier (Định hướng kỹ năng)
        print(" [Classifier] Đang phân loại kỹ năng...")
        t_class_start = time.time()
        
        # Lấy thông tin các skill để classifier chọn động
        skills_info = self.skill_manager.get_all_skills_info()
        class_res = self.classifier.classify(user_query, skills_info, history)
        
        intent = class_res.get("class", "fallback")
        t_class = time.time() - t_class_start
        print(f" -> Kỹ năng được chọn: {intent} ({t_class:.2f}s)")
        
        # 3. Execution (Thực thi kỹ năng)
        skill = self.skill_manager.get_skill(intent)
        print(f" [Skill] Đang chuyển hướng đến {skill.__class__.__name__}...")
        
        t_skill_start = time.time()
        skill_res = skill.handle_query(user_query, history)
        t_skill = time.time() - t_skill_start
        
        # Hiển thị dữ liệu thô nếu có (để debug)
        raw_data = skill_res.get("raw_data", [])
        if raw_data:
            print(f"\n [Data] DỮ LIỆU TRÍCH XUẤT:")
            for item in raw_data:
                print(f"  - Tool: {item.get('tool')}")
        
        dt_total = time.time() - t0
        
        # Hiển thị thời gian chi tiết
        print(f"\n [Timing] CHI TIẾT:")
        print(f"  - Guard:      {t_guard:.2f}s")
        print(f"  - Classifier: {t_class:.2f}s")
        print(f"  - Skill:      {t_skill:.2f}s")
        
        sub_timings = skill_res.get("timings", {})
        if sub_timings:
            for step, duration in sub_timings.items():
                print(f"    * {step}: {duration:.2f}s")
        
        print(f"  - Tổng cộng:  {dt_total:.2f}s")

        print(f"\n PHẢN HỒI:")
        print(f"{'-'*30}")
        print(skill_res.get("text", "Không có phản hồi nào được tạo."))
        print(f"{'-'*30}\n")

    def handle_request_api(self, user_query: str, history: str = ""):
        """
        Xử lý yêu cầu và trả về dictionary cho API.
        """
        # 1. Guard
        guard_res = self.guard.check(user_query, history)
        if guard_res.get("allow") == "not_allow":
            return {
                "text": guard_res.get("public_response", "Yêu cầu bị chặn."),
                "intent": "blocked",
                "handoff": True, # Luôn cho phép handoff nếu bị block
                "raw_data": []
            }
        
        # 2. Classifier
        skills_info = self.skill_manager.get_all_skills_info()
        class_res = self.classifier.classify(user_query, skills_info, history)
        intent = class_res.get("class", "fallback")
        
        # 3. Execution
        skill = self.skill_manager.get_skill(intent)
        skill_res = skill.handle_query(user_query, history)
        
        # Xác định xem có cần handoff không
        # Handoff nếu là fallback hoặc skill không trả về kết quả tốt
        handoff_needed = (intent == "fallback")
        
        return {
            "text": skill_res.get("text", "Không có phản hồi nào được tạo."),
            "intent": intent,
            "handoff": handoff_needed,
            "raw_data": skill_res.get("raw_data", [])
        }

    def handle_request_stream(self, user_query: str, history: str = ""):
        """
        Xử lý yêu cầu và trả về generator cho streaming API.
        """
        # 1. Guard
        guard_res = self.guard.check(user_query, history)
        if guard_res.get("allow") == "not_allow":
            yield {
                "text": guard_res.get("public_response", "Yêu cầu bị chặn."),
                "intent": "blocked",
                "handoff": True,
                "finish": True
            }
            return
        
        # 2. Classifier
        skills_info = self.skill_manager.get_all_skills_info()
        class_res = self.classifier.classify(user_query, skills_info, history)
        intent = class_res.get("class", "fallback")
        
        # 3. Execution
        skill = self.skill_manager.get_skill(intent)
        
        # Stream from skill
        for chunk in skill.handle_query_stream(user_query, history):
            chunk["intent"] = intent
            yield chunk

if __name__ == "__main__":
    orchestrator = ChatbotOrchestrator()
    print(f" PF Chatbot (Agent Skill) Ready ({llm_client.backend_name}: {llm_client.model}). Nhập 'exit' để thoát.")
    while True:
        try:
            query = input("Bạn: ").strip()
            if not query: continue
            if query.lower() in ['exit', 'quit']: break
            orchestrator.handle_request(query)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Lỗi: {e}")
