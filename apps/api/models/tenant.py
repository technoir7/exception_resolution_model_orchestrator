"""
Tenant model for multi-tenancy support.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.models.base import Base


class Tenant(Base):
    """
    Tenant represents an organization using the system.
    
    All business data is scoped to a tenant for isolation.
    """
    
    __tablename__ = "tenants"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    
    # Settings
    daily_llm_budget: Mapped[float] = mapped_column(default=100.0, nullable=False)
    
    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name})>"
