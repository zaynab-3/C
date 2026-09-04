import asyncio

from sqlalchemy import text

from c_backend.db import engine


async def main() -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                """
                SELECT
                    current_database(),
                    current_user,
                    current_setting('server_version')
                """
            )
        )

        database, user, version = result.one()

        print(f"Database: {database}")
        print(f"User: {user}")
        print(f"PostgreSQL: {version}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(
        main(),
        loop_factory=asyncio.SelectorEventLoop,
    )
