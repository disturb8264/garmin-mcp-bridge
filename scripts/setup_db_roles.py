"""One-time setup: replace admin app credentials with scoped DB roles."""

import os
import secrets
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql


ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
BACKUP_PATH = ROOT / "data" / "db_admin.env"
DB_NAME = "garmin_running"
WRITER = "garmin2_writer"
READER = "garmin2_reader"


def write_private(path: Path, content: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def replace_values(content: str, updates: dict[str, str]) -> str:
    lines = content.splitlines()
    seen = set()
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0]
        if key in updates and "=" in line:
            lines[index] = f"{key}={updates[key]}"
            seen.add(key)
    lines.extend(f"{key}={value}" for key, value in updates.items() if key not in seen)
    return "\n".join(lines) + "\n"


def main() -> None:
    values = dotenv_values(ENV_PATH)
    required = ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE")
    if any(not values.get(key) for key in required):
        raise RuntimeError("Complete PGHOST, PGPORT, PGUSER, PGPASSWORD and PGDATABASE first")
    if values["PGDATABASE"] != DB_NAME:
        raise RuntimeError(f"Expected PGDATABASE={DB_NAME}")
    if BACKUP_PATH.exists():
        raise RuntimeError("Admin backup already exists; setup may already have run")

    writer_password = secrets.token_urlsafe(36)
    reader_password = secrets.token_urlsafe(36)
    with psycopg.connect(
        host=values["PGHOST"], port=int(values["PGPORT"]), dbname=DB_NAME,
        user=values["PGUSER"], password=values["PGPASSWORD"],
        connect_timeout=5, autocommit=True,
    ) as conn:
        existing = conn.execute(
            "SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s)", (WRITER, READER)
        ).fetchall()
        if existing:
            raise RuntimeError("One or both project roles already exist; review them manually")
        with conn.transaction():
            for name, password in ((WRITER, writer_password), (READER, reader_password)):
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(name), sql.Literal(password)
                ))
            conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(DB_NAME)))
            conn.execute(sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(
                sql.Identifier(DB_NAME), sql.Identifier(WRITER)
            ))
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(DB_NAME), sql.Identifier(READER)
            ))
            conn.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(sql.Identifier(WRITER)))
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(READER)))
            conn.execute(sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT ON TABLES TO {}"
            ).format(sql.Identifier(WRITER), sql.Identifier(READER)))

    BACKUP_PATH.parent.mkdir(exist_ok=True)
    write_private(BACKUP_PATH, "\n".join(
        f"{key}={values[key]}" for key in required
    ) + "\n")
    updates = {
        "PGUSER": WRITER,
        "PGPASSWORD": writer_password,
        "MCP_PGUSER": READER,
        "MCP_PGPASSWORD": reader_password,
    }
    new_content = replace_values(ENV_PATH.read_text(encoding="utf-8"), updates)
    temporary = ENV_PATH.with_name(".env.new")
    write_private(temporary, new_content)
    os.replace(temporary, ENV_PATH)
    print("Scoped PostgreSQL roles created and .env updated; admin credentials saved outside containers")


if __name__ == "__main__":
    main()
