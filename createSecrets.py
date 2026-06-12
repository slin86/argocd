#!/usr/bin/env python3
"""Bootstrap-Secrets 1-3 fuer das Homelab anlegen.

Existierende Secrets werden NICHT ueberschrieben, sondern uebersprungen
(mit Warnung) - vorhandene Passwoerter dann weiterverwenden.
"""
import base64
import secrets
import subprocess
import sys

NAMESPACES = ["database", "redis", "infisical"]


def kubectl(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["kubectl", *args], input=stdin, text=True, capture_output=True
    )


def ensure_namespace(ns: str) -> None:
    """Idempotent: create --dry-run | apply."""
    dry = kubectl("create", "namespace", ns, "--dry-run=client", "-o", "yaml")
    if dry.returncode != 0:
        sys.exit(f"FEHLER Namespace {ns}: {dry.stderr.strip()}")
    apply = kubectl("apply", "-f", "-", stdin=dry.stdout)
    if apply.returncode != 0:
        sys.exit(f"FEHLER Namespace {ns}: {apply.stderr.strip()}")
    print(f"Namespace {ns}: ok")


def create_secret(name: str, ns: str, literals: dict[str, str]) -> None:
    args = ["create", "secret", "generic", name, "-n", ns]
    args += [f"--from-literal={key}={value}" for key, value in literals.items()]
    proc = kubectl(*args)
    if proc.returncode == 0:
        print(f"Secret {ns}/{name}: angelegt")
    elif "already exists" in proc.stderr.lower():
        print(
            f"WARNUNG Secret {ns}/{name}: existiert bereits - NICHT "
            f"ueberschrieben. Vorhandenes Passwort weiterverwenden!"
        )
    else:
        sys.exit(f"FEHLER Secret {ns}/{name}: {proc.stderr.strip()}")


def main() -> None:
    # ---- Werte generieren (Hex => keine URL-Encoding-Probleme) ----
    pg_super_pw = secrets.token_hex(20)
    redis_pw = secrets.token_hex(20)
    infisical_db_pw = secrets.token_hex(20)
    encryption_key = secrets.token_hex(16)
    auth_secret = base64.b64encode(secrets.token_bytes(32)).decode()

    # ---- Ausgabe fuer den Passwortmanager (WICHTIG: jetzt sichern!) ----
    print("================= IN DEN PASSWORTMANAGER =================")
    print(f"postgres-superuser password : {pg_super_pw}")
    print(f"redis password              : {redis_pw}")
    print(f"infisical db password       : {infisical_db_pw}")
    print(f"infisical ENCRYPTION_KEY    : {encryption_key}")
    print(f"infisical AUTH_SECRET       : {auth_secret}")
    print("===========================================================\n")

    # ---- Namespaces (idempotent) ----
    for ns in NAMESPACES:
        ensure_namespace(ns)

    # ---- [1/4] Postgres-Superuser ----
    create_secret("postgres-superuser", "database", {"password": pg_super_pw})

    # ---- [2/4] Redis-Passwort (fuer die Redis-Instanz selbst) ----
    create_secret("redis-auth", "redis", {"password": redis_pw})

    # ---- [3/4] Infisical-Konfiguration ----
    create_secret(
        "infisical-secrets",
        "infisical",
        {
            "ENCRYPTION_KEY": encryption_key,
            "AUTH_SECRET": auth_secret,
            "DB_CONNECTION_URI": (
                f"postgresql://infisical:{infisical_db_pw}"
                "@postgres.database.svc.cluster.local:5432/infisical"
            ),
            "REDIS_URL": (
                f"redis://default:{redis_pw}"
                "@redis.redis.svc.cluster.local:6379/1"
            ),
            "SITE_URL": "http://secrets.home.lan",
        },
    )

    print("\nBootstrap-Secrets 1-3 angelegt.")
    print("Nicht vergessen: Postgres-User 'infisical' mit obigem Passwort anlegen!")


if __name__ == "__main__":
    main()
