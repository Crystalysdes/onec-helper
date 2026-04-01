import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, BigInteger, Float, Boolean,
    DateTime, ForeignKey, Text, JSON, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.database.connection import Base
import enum


class UserRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    manager = "manager"


class SubscriptionStatus(str, enum.Enum):
    trial = "trial"
    active = "active"
    expired = "expired"
    cancelled = "cancelled"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    cancelled = "cancelled"
    refunded = "refunded"


class IntegrationStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    error = "error"


class LogLevel(str, enum.Enum):
    info = "info"
    warning = "warning"
    error = "error"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username = Column(String(255), nullable=True)
    telegram_first_name = Column(String(255), nullable=True)
    telegram_last_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    stores = relationship("Store", back_populates="owner", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    referral_code = relationship("ReferralCode", back_populates="user", uselist=False, cascade="all, delete-orphan")
    referral_uses_given = relationship("ReferralUse", back_populates="code_owner", foreign_keys="ReferralUse.referrer_id")
    referral_use_received = relationship("ReferralUse", back_populates="referee", foreign_keys="ReferralUse.referee_id", uselist=False)

    def __repr__(self):
        return f"<User {self.telegram_id} ({self.telegram_username})>"


class Store(Base):
    __tablename__ = "stores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="stores")
    integrations = relationship("Integration", back_populates="store", cascade="all, delete-orphan")
    products = relationship("ProductCache", back_populates="store", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Store {self.name}>"


class Integration(Base):
    __tablename__ = "integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False, default="1C Integration")
    integration_type = Column(String(50), nullable=False, default='onec', server_default='onec')
    onec_url = Column(String(1000), nullable=True)
    onec_username = Column(String(255), nullable=True)
    onec_password_encrypted = Column(Text, nullable=False)
    status = Column(SAEnum(IntegrationStatus), default=IntegrationStatus.inactive)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    settings = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    store = relationship("Store", back_populates="integrations")

    def __repr__(self):
        return f"<Integration {self.name} ({self.status})>"


class ProductCache(Base):
    __tablename__ = "products_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    onec_id = Column(String(255), nullable=True, index=True)
    kontur_id = Column(String(255), nullable=True, index=True)
    name = Column(String(1000), nullable=False)
    barcode = Column(String(255), nullable=True, index=True)
    article = Column(String(255), nullable=True)
    category = Column(String(500), nullable=True)
    price = Column(Float, nullable=True)
    purchase_price = Column(Float, nullable=True)
    quantity = Column(Float, default=0)
    unit = Column(String(100), nullable=True, default="шт")
    description = Column(Text, nullable=True)
    image_url = Column(String(1000), nullable=True)
    is_active = Column(Boolean, default=True)
    user_deleted_at = Column(DateTime(timezone=True), nullable=True)
    extra_data = Column(JSON, default={})
    synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    store = relationship("Store", back_populates="products")

    def __repr__(self):
        return f"<Product {self.name}>"


class CatalogImportJob(Base):
    """Tracks catalog import progress — stored in DB so it survives restarts/multi-worker."""
    __tablename__ = "catalog_import_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="running")   # running / done / error
    stage = Column(String(30), nullable=False, default="reading")    # reading / importing / done
    imported = Column(Integer, nullable=False, default=0)
    skipped = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    file_name = Column(String(255), nullable=True)


class GlobalProduct(Base):
    """Shared product catalog — populated from all users, searchable by barcode."""
    __tablename__ = "global_products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    barcode = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(1000), nullable=False)
    price = Column(Float, nullable=True)
    purchase_price = Column(Float, nullable=True)
    article = Column(String(255), nullable=True)
    category = Column(String(500), nullable=True)
    unit = Column(String(100), nullable=True, default="шт")
    description = Column(Text, nullable=True)
    is_excluded = Column(Boolean, default=False, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<GlobalProduct {self.barcode} — {self.name}>"


class Log(Base):
    __tablename__ = "logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    store_id = Column(UUID(as_uuid=True), nullable=True)
    level = Column(SAEnum(LogLevel), default=LogLevel.info)
    action = Column(String(500), nullable=False)
    message = Column(Text, nullable=True)
    meta = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="logs")

    def __repr__(self):
        return f"<Log {self.action} ({self.level})>"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(SAEnum(SubscriptionStatus), default=SubscriptionStatus.trial, nullable=False)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    auto_renew = Column(Boolean, default=True)
    yookassa_customer_id = Column(String(255), nullable=True)
    yookassa_payment_method_id = Column(String(255), nullable=True)
    next_discount_percent = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="subscription")
    payments = relationship("Payment", back_populates="subscription", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Subscription user={self.user_id} status={self.status}>"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    yookassa_payment_id = Column(String(255), nullable=True, unique=True, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")
    status = Column(SAEnum(PaymentStatus), default=PaymentStatus.pending)
    payment_method_type = Column(String(100), nullable=True)
    confirmation_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    metadata_json = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    subscription = relationship("Subscription", back_populates="payments")
    user = relationship("User", back_populates="payments")

    def __repr__(self):
        return f"<Payment {self.yookassa_payment_id} {self.status}>"


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    code = Column(String(20), nullable=False, unique=True, index=True)
    total_referrals = Column(Integer, default=0)
    successful_referrals = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="referral_code")
    uses = relationship("ReferralUse",
                        primaryjoin="ReferralCode.user_id == foreign(ReferralUse.referrer_id)",
                        viewonly=True)

    def __repr__(self):
        return f"<ReferralCode {self.code}>"


class ReferralUse(Base):
    __tablename__ = "referral_uses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    referee_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    discount_granted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    code_owner = relationship("User", back_populates="referral_uses_given", foreign_keys=[referrer_id])
    referee = relationship("User", back_populates="referral_use_received", foreign_keys=[referee_id])
