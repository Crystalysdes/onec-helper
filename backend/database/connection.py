from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
from backend.config import settings


_raw_url = settings.DATABASE_URL
_is_sqlite = _raw_url.startswith("sqlite")
_engine_kwargs = dict(
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=not _is_sqlite,
)
if not _is_sqlite:
    import ssl as _ssl
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 5
    # Strip ?ssl=... from URL — asyncpg requires ssl via connect_args, not URL params
    _db_url = _raw_url.split("?")[0]
    _ssl_ctx = _ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = _ssl.CERT_NONE  # Supabase uses self-signed on free tier
    _engine_kwargs["connect_args"] = {"ssl": _ssl_ctx}
else:
    _db_url = _raw_url

engine = create_async_engine(_db_url, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    from backend.database.models import Base as ModelBase
    async with engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
