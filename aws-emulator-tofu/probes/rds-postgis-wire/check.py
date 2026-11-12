import json

from lib import CA, client, result

TITLE = "Aurora PostgreSQL SQL fidelity: PostGIS, wire protocol vs Data API, PL/pgSQL"
CATEGORY = "RDS / Aurora"
AWS_EXPECTED = ("CREATE EXTENSION postgis works (tipg needs it); rows written via the Data API are visible over the "
                "PostgreSQL wire protocol (same database); DO blocks run; version() is PostgreSQL 16.")
FINDINGS = ["rds-sqlite-no-postgis", "rds-dataapi-separate-store", "rds-random-port"]


def check(outputs, row):
    rd = client("rds-data")
    arn, sec = outputs["arn"], outputs["secret"]
    c = {}

    def q(sql):
        try:
            r = rd.execute_statement(resourceArn=arn, secretArn=sec, database="probe", sql=sql)
            return r.get("records", "ok")
        except Exception as e:  # noqa: BLE001
            return f"ERR {str(e)[-110:]}"
    c["dataapi CREATE EXTENSION postgis"] = q("CREATE EXTENSION IF NOT EXISTS postgis")
    c["dataapi version()"] = q("SELECT version()")
    c["dataapi create+insert"] = [q("CREATE TABLE t (id int, v text)"), q("INSERT INTO t VALUES (1, 'via-data-api')")]
    c["dataapi DO block"] = q("DO $$ BEGIN PERFORM 1; END $$")
    pw = json.loads(client("secretsmanager").get_secret_value(SecretId=sec)["SecretString"])
    c["endpoint"] = f"{outputs['endpoint']}:{outputs['port']}"
    try:
        import psycopg
        with psycopg.connect(host=outputs["endpoint"], port=int(outputs["port"]), dbname="probe", user=pw["username"],
                             password=pw["password"], sslmode="require", sslrootcert=CA, connect_timeout=5,
                             autocommit=True) as con:
            def w(sql):
                try:
                    cur = con.execute(sql)
                    return cur.fetchall() if cur.description else "ok"
                except Exception as e:  # noqa: BLE001
                    return f"ERR {str(e)[:110]}"
            c["wire version()"] = w("SELECT version()")
            c["wire sees Data API row"] = w("SELECT v FROM t")
            c["wire CREATE EXTENSION postgis"] = w("CREATE EXTENSION postgis")
            c["wire ST_AsText(ST_Point(1,2))"] = w("SELECT ST_AsText(ST_Point(1,2))")
    except Exception as e:  # noqa: BLE001
        c["wire connect"] = f"ERR {type(e).__name__}: {str(e)[:120]}"
    postgis = not str(c["dataapi CREATE EXTENSION postgis"]).startswith("ERR") and \
        not str(c.get("wire CREATE EXTENSION postgis", "ERR")).startswith("ERR")
    same = "via-data-api" in str(c.get("wire sees Data API row"))
    return result("works" if postgis and same else "partial", "; ".join(f"{k}: {v}" for k, v in c.items())[:1500])
