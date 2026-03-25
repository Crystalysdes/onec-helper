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
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 5
    _db_url = _raw_url.split("?")[0]
    # Only use SSL for remote/cloud databases (Neon, Supabase).
    # Skip SSL for local Docker postgres (hostname = 'db', 'localhost', '127.0.0.1').
    _local_hosts = ("@db/", "@db:", "@localhost/", "@localhost:", "@127.0.0.1/", "@127.0.0.1:")
    _needs_ssl = not any(h in _raw_url for h in _local_hosts)
    if _needs_ssl:
        import ssl as _ssl
        _ssl_ctx = _ssl.create_default_context()
        _ssl_ctx.check_hostname = False
        _ssl_ctx.verify_mode = _ssl.CERT_NONE
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
