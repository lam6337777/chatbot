from Skills.Product_skill import ProductSkill
from Skills.Order_skill import OrderSkill
from Skills.Promotion_skill import PromotionSkill
from Skills.General_skill import GeneralSkill
from Skills.Fallback_skill import FallbackSkill

class SkillManager:
    def __init__(self):
        # Đăng ký các kỹ năng hiện có
        self.skills = {
            "product_related": ProductSkill(),
            "order_related": OrderSkill(),
            "promotion_related": PromotionSkill(),
            "pf_related": GeneralSkill(),
            "fallback": FallbackSkill()
        }

    def get_skill(self, skill_id: str):
        """Lấy instance của skill theo ID."""
        return self.skills.get(skill_id, self.skills["fallback"])

    def get_all_skills_info(self) -> str:
        """Tạo chuỗi mô tả tất cả các kỹ năng để dùng cho Classifier."""
        info = ""
        for skill_id, skill in self.skills.items():
            if skill_id != "fallback":
                info += f"- {skill_id}: {skill.description}\n"
        return info
