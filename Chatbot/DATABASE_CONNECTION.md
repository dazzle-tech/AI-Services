# Database Connection Guide

This guide explains how to connect the chatbot to either SQLite (default) or PostgreSQL databases.

## Quick Start

### Using SQLite (Default)

The system uses SQLite by default. No configuration needed if you're using the test database.

### Using PostgreSQL

1. **Install PostgreSQL driver:**

   ```bash
   pip install psycopg2-binary
   ```

2. **Create a `.env` file** in the `chatbot` directory (copy from `.env.example`):

   ```bash
   cp .env.example .env
   ```

3. **Configure PostgreSQL connection** in `.env`:

   ```env
   DB_TYPE=postgresql
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=DBLocal
   DB_USER=postgres
   DB_PASSWORD=your_password_here
   DB_SCHEMA=public
   ```

4. **Restart the services** for changes to take effect.

## Configuration Details

### Environment Variables

| Variable               | Default               | Description                                   |
| ---------------------- | --------------------- | --------------------------------------------- |
| `DB_TYPE`              | `sqlite`              | Database type: `sqlite` or `postgresql`       |
| `DB_HOST`              | `localhost`           | PostgreSQL host (PostgreSQL only)             |
| `DB_PORT`              | `5432`                | PostgreSQL port (PostgreSQL only)             |
| `DB_NAME`              | `DBLocal`             | PostgreSQL database name (PostgreSQL only)    |
| `DB_USER`              | `postgres`            | PostgreSQL username (PostgreSQL only)         |
| `DB_PASSWORD`          | (empty)               | PostgreSQL password (PostgreSQL only)         |
| `DB_SCHEMA`            | `public`              | PostgreSQL schema name (PostgreSQL only)      |
| `HOSPITAL_SQLITE_PATH` | `data/hospital.db`    | SQLite database file path (SQLite only)       |
| `AUDIT_DB_PATH`        | `data/medai_audit.db` | SQLite audit database file path (SQLite only) |

### Connection String Format

The system automatically constructs the connection based on your `DB_TYPE` setting:

- **SQLite**: Uses file path from `HOSPITAL_SQLITE_PATH`
- **PostgreSQL**: Uses connection parameters to build: `host:port/database` with user credentials

## Switching Between Databases

To switch from SQLite to PostgreSQL:

1. Update `.env` file with PostgreSQL settings
2. Set `DB_TYPE=postgresql`
3. Ensure `psycopg2-binary` is installed
4. Restart all services

To switch back to SQLite:

1. Set `DB_TYPE=sqlite` in `.env`
2. Restart services

## Troubleshooting

### PostgreSQL Connection Issues

1. **"psycopg2 not installed"**

   - Install: `pip install psycopg2-binary`

2. **"Connection refused"**

   - Check PostgreSQL is running: `pg_isready`
   - Verify host and port settings

3. **"Authentication failed"**

   - Verify username and password in `.env`
   - Check PostgreSQL user permissions

4. **"Database does not exist"**

   - Verify `DB_NAME` matches your actual database name
   - Check database exists: `psql -l`

5. **"Schema not found"**
   - Verify `DB_SCHEMA` exists in your database
   - Default schema is usually `public`

### SQLite Connection Issues

1. **"Database file not found"**
   - Check `HOSPITAL_SQLITE_PATH` points to correct file
   - Ensure file exists and is readable

## Notes

- The audit database (`medai_audit.db`) always uses SQLite regardless of `DB_TYPE` setting
- All SQL queries are compatible with both SQLite and PostgreSQL
- The system automatically handles SQL syntax differences (e.g., parameter placeholders: `?` for SQLite, `%s` for PostgreSQL)
