import pytest
from app.database.postgres.models import Supplier
from app.database.postgres.session import get_db_session, get_session_factory
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


async def test_session_dependency_rolls_back(live_client) -> None:
    generator = get_db_session()
    session = await anext(generator)

    await session.execute(
        Supplier.__table__.insert().values(
            id="SUP_TEST_ROLLBACK",
            name="Rollback Test Supplier",
            category="test",
            location="IN-TG",
            status="active",
        )
    )
    await session.flush()

    with pytest.raises(RuntimeError):
        await generator.athrow(RuntimeError("deliberate rollback"))

    factory = get_session_factory()
    async with factory() as check:
        result = await check.execute(
            select(func.count())
            .select_from(Supplier)
            .where(Supplier.id == "SUP_TEST_ROLLBACK")
        )
        assert result.scalar_one() == 0
