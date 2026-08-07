---
name: mysql-storage
description: Provides persistent storage via a shared Aliyun RDS MySQL instance (database "pctest") for any feature that needs a database. Use whenever a task requires storing, querying, or managing structured/persistent data and no other datastore is specified. You have full DDL/DML permission on this database — design and evolve the schema (tables, indexes, migrations) as the task requires. Triggers include "存到数据库", "需要持久化", "用数据库存一下", "add a table for X", "store this data", "query the database".
---

# MySQL Storage

Shared MySQL datastore for tasks that need persistence. Use this instead of ad-hoc
files/JSON when a feature needs structured, queryable, or multi-run data.

## Credentials

Never hardcode credentials in code, commits, or anywhere under `skill/`. They live
in a gitignored local file:

`.claude/mysql.local.json` (repo root, git-ignored — see `.gitignore`):

```json
{
  "host": "rm-bp1451ry3ll508ex4do.mysql.rds.aliyuncs.com",
  "port": 3306,
  "user": "pc",
  "password": "...",
  "database": "pctest"
}
```

Read this file at runtime (Python `json.load`, Node `require`, etc.) rather than
copying the values into scripts or application config. If the file is missing, tell
the user it needs to be recreated — do not ask them to repaste the password into
chat since that already happened once for this project and shouldn't be needed
again in this repo.

If a script needs to run outside this repo/session, read env vars instead
(`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`) and
document that the caller must export them from the same local file.

## Connecting

Pick whatever driver fits the task's language — all point at the same instance/db:

- Python: `pymysql` (confirmed available in this environment) or `mysql-connector-python`
- Node/TS: `mysql2`
- CLI: `mysql -h <host> -P 3306 -u pc -p pctest` if the `mysql` client is installed

Example (Python):

```python
import json, pymysql

with open(".claude/mysql.local.json") as f:
    cfg = json.load(f)

conn = pymysql.connect(
    host=cfg["host"], port=cfg["port"],
    user=cfg["user"], password=cfg["password"],
    database=cfg["database"], connect_timeout=10,
    charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
)
```

## Schema ownership

This is a shared database (`pctest`) — you have full permission to create, alter,
and drop tables as features need them. Guidelines:

- Prefix or namespace tables by feature/app when the database is shared across
  unrelated projects (e.g. `vibelab_users`, `vibelab_sessions`) unless the user
  says otherwise — keeps things identifiable later.
- Use `utf8mb4` charset and `InnoDB` engine for new tables.
- Add a primary key and reasonable indexes for anything queried by non-PK columns.
- Before `DROP TABLE` or destructive `ALTER`/`DELETE` on tables that may hold real
  data, confirm with the user first — creation and additive changes (new table,
  new column, new index) don't need confirmation, but destructive/irreversible
  ones do.
- If you introduce a schema, briefly note the tables/columns you created in your
  response so the user has a record of what exists.

## Verifying

`SHOW TABLES` / `DESCRIBE <table>` before assuming a schema exists — don't guess
column names. This instance is currently empty (no tables) as of setup.
