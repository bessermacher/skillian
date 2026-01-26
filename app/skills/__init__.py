"""Skills module - domain-specific capabilities."""

from app.skills.business import BusinessSkill
from app.skills.financial import FinancialSkill

__all__ = ["BusinessSkill", "FinancialSkill"]