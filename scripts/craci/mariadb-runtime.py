#!/usr/bin/env python3
"""Execute Chronicle Witness's unchanged SQL on a disposable real MariaDB.

Python standard library only. Findings remain failures; this harness never adds
collations or rewrites the product query to make a failing contract pass.
Run with SOURCE_DIR, EXPECTED_SOURCE_SHA and CRACI_MARIADB_IMAGE (official digest).
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

WORK_ID = "J26-CRACI-EXPLORE2-20261114"
PRODUCT = Path("solutions/mariadb-wikipedia-time")
FILES = ("sql/schema.sql", "fixtures/synthetic.json", "src/chronicle.mjs", "src/cli.mjs")
UTC = dt.timezone.utc
INSERT = """INSERT INTO wiki_revision_events
 (dataset_id, source_revision_id, page_id, article_title, revised_at_utc,
  content_body, content_sha256, source_url, dataset_license)
 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""


def digest(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def emit(event: str, **values) -> None:
    print(canonical({"event": event, "work_id": WORK_ID, **values}), flush=True)


def run(args: list[str], *, input_text: str | None = None,
        env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(args, input=input_text, capture_output=True,
                          text=True, encoding="utf-8", env=env, timeout=timeout)


def require_process(result: subprocess.CompletedProcess, stage: str) -> str:
    if result.returncode:
        raise RuntimeError(f"{stage}: exit={result.returncode}; stderr={result.stderr[-1600:]}")
    return result.stdout


def instant(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def sql_time(value: str | dt.datetime) -> str:
    return (instant(value) if isinstance(value, str) else value).strftime("%Y-%m-%d %H:%M:%S.%f")


def normalized_time(value: str) -> str:
    value = value.replace(" ", "T")
    if not value.endswith("Z") and "+" not in value[10:]:
        value += "Z"
    return instant(value).isoformat(timespec="microseconds")


def sql_value(value: str | None) -> str:
    # Only hex digits are inserted into SQL text. Untrusted data are then bound
    # through EXECUTE USING variables; no quoting/SQL-mode assumption is needed.
    return "NULL" if value is None else f"CONVERT(X'{value.encode('utf-8').hex()}' USING utf8mb4)"


def prepared(statement: str, values: list[str | None]) -> str:
    if statement.count("?") != len(values):
        raise ValueError("Prepared statement parameter count mismatch")
    parts = [f"SET @j26_sql = {sql_value(statement.rstrip().rstrip(';'))};",
             "PREPARE j26_stmt FROM @j26_sql;"]
    parts += [f"SET @j26_p{i} = {sql_value(value)};" for i, value in enumerate(values)]
    binding = " USING " + ",".join(f"@j26_p{i}" for i in range(len(values))) if values else ""
    parts += [f"EXECUTE j26_stmt{binding};", "DEALLOCATE PREPARE j26_stmt;"]
    return "\n".join(parts)


def source_binding(source: Path, expected: str) -> dict[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ValueError("EXPECTED_SOURCE_SHA must be a full lowercase Git commit")
    actual = require_process(run(["git", "-C", str(source), "rev-parse", "HEAD"]), "source HEAD").strip()
    if actual != expected:
        raise ValueError(f"Source HEAD mismatch: expected {expected}, observed {actual}")
    hashes = {}
    for relative in FILES:
        path = PRODUCT / relative
        current = (source / path).read_bytes()
        committed = subprocess.run(["git", "-C", str(source), "show", f"{expected}:{path.as_posix()}"],
                                   capture_output=True, timeout=30)
        if committed.returncode or committed.stdout != current:
            raise ValueError(f"Source bytes differ from commit: {path}")
        hashes[path.as_posix()] = digest(current)
    return hashes


def extract_source_sql(text: str) -> tuple[str, str]:
    # Preserve the exact source statements. Do not execute the illustrative
    # historic SELECT or send unbound question marks to the SQL command line.
    ddl = re.search(r"CREATE TABLE IF NOT EXISTS wiki_revision_events\s*\([\s\S]*?"
                    r"\)\s*ENGINE=InnoDB[^;]*;", text)
    query = re.search(r"SELECT source_revision_id,[\s\S]*?LIMIT 2;", text)
    if not ddl or not query or "WITH SYSTEM VERSIONING" not in ddl.group(0):
        raise ValueError("Original DDL/as-of query contract not found; review source before adapting")
    if query.group(0).count("?") != 3:
        raise ValueError("Original as-of query must bind dataset, page and revision time")
    return ddl.group(0), query.group(0)


def oracle(dataset: dict, page: str, at: str) -> dict:
    candidates = [r for r in dataset["revisions"]
                  if r["page_id"] == page and instant(r["revised_at"]) <= instant(at)]
    if not candidates:
        return {"status": "NO_EVIDENCE"}
    newest = max(instant(r["revised_at"]) for r in candidates)
    latest = [r for r in candidates if instant(r["revised_at"]) == newest]
    if len(latest) > 1:
        return {"status": "AMBIGUOUS_TIMESTAMP", "conflicting_ids": sorted(r["revision_id"] for r in latest)}
    r = latest[0]
    return {"status": "FOUND", "revision_id": r["revision_id"],
            "revised_at": normalized_time(r["revised_at"]),
            "body_sha256": digest(r["body"]), "stored_sha256": digest(r["body"]),
            "source_url": r["source_url"]}


def product_snapshot(snapshot: dict) -> dict:
    result = {"status": snapshot["status"]}
    if snapshot["status"] == "FOUND":
        result.update(revision_id=snapshot["revision_id"],
                      revised_at=normalized_time(snapshot["revised_at"]),
                      body_sha256=digest(snapshot["text"]), stored_sha256=snapshot["sha256"],
                      source_url=snapshot["source_url"])
    if snapshot["status"] == "AMBIGUOUS_TIMESTAMP":
        result["conflicting_ids"] = sorted(snapshot["conflicting_ids"])
    return result


def database_snapshot(rows: list[dict]) -> dict:
    if not rows:
        return {"status": "NO_EVIDENCE"}
    if len(rows) > 1 and normalized_time(rows[0]["revised_at_utc"]) == normalized_time(rows[1]["revised_at_utc"]):
        return {"status": "AMBIGUOUS_TIMESTAMP", "conflicting_ids": sorted(r["source_revision_id"] for r in rows)}
    r = rows[0]
    return {"status": "FOUND", "revision_id": r["source_revision_id"],
            "revised_at": normalized_time(r["revised_at_utc"]),
            "body_sha256": digest(r["content_body"]), "stored_sha256": r["content_sha256"],
            "source_url": r["source_url"]}


class Experiment:
    def __init__(self, source: Path, env: dict[str, str], project: str, temporary: Path):
        self.source, self.env, self.project, self.temporary = source, env, project, temporary
        self.compose = ["docker", "compose", "-f", str(Path(__file__).with_name("mariadb-compose.yml")), "-p", project]
        self.checks: list[dict] = []

    def command(self, arguments: list[str], timeout: int = 60) -> str:
        return require_process(run(self.compose + arguments, env=self.env, timeout=timeout), "compose " + arguments[0])

    def sql(self, statement: str, *, allow_error: bool = False) -> subprocess.CompletedProcess:
        prefix = "SET NAMES utf8mb4; SET SESSION time_zone = '+00:00';\n"
        result = run(self.compose + ["exec", "-T", "db", "mariadb", "--user=root", "--batch", "--xml",
                                    "--default-character-set=utf8mb4", "--database=" + self.env["CRACI_MARIADB_DATABASE"]],
                     input_text=prefix + statement + "\n", env=self.env, timeout=40)
        if not allow_error:
            require_process(result, "SQL")
        return result

    def rows(self, statement: str, values: list[str | None] | None = None) -> list[dict]:
        result = self.sql(prepared(statement, values) if values is not None else statement)
        xml = result.stdout.strip()
        if not xml:
            return []
        root = ET.fromstring(xml)
        if root.tag != "resultset":
            raise ValueError("Expected exactly one MariaDB XML result set")
        return [{field.attrib["name"]: None if field.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true"
                 else field.text or "" for field in row.findall("field")} for row in root.findall("row")]

    def check(self, name: str, expected, actual, **details) -> bool:
        passed = actual == expected
        row = {"case": name, "passed": passed, "expected": expected, "actual": actual, **details}
        self.checks.append(row)
        emit("check", **row)
        return passed

    def import_sql(self, dataset: dict, revisions: list[dict] | None = None) -> str:
        statements = ["START TRANSACTION;"]
        for r in dataset["revisions"] if revisions is None else revisions:
            statements.append(prepared(INSERT, [dataset["dataset_id"], r["revision_id"], r["page_id"], r["title"],
                                                sql_time(r["revised_at"]), r["body"], digest(r["body"]),
                                                r["source_url"], dataset["dataset_license"]]))
        return "\n".join(statements + ["COMMIT;"])

    def cli(self, dataset: dict, page: str, at: str) -> subprocess.CompletedProcess:
        path = self.temporary / (digest(canonical(dataset)) + ".json")
        path.write_text(canonical(dataset), encoding="utf-8")
        return run(["node", str(self.source / PRODUCT / "src/cli.mjs"), "--data", str(path),
                    "--page", page, "--at", at], timeout=20)

    def compare(self, name: str, query: str, dataset: dict, page: str, at: str) -> None:
        expected = oracle(dataset, page, at)
        cli = json.loads(require_process(self.cli(dataset, page, at), "product CLI"))
        self.check(name + ":cli", expected, product_snapshot(cli["snapshot"]))
        self.check(name + ":provider-label", ["NO_MARIADB_CONNECTION", False],
                   [cli.get("provider"), cli.get("verified_live_source")])
        observed = database_snapshot(self.rows(query, [dataset["dataset_id"], page, sql_time(at)]))
        self.check(name + ":database", expected, observed,
                   input_sha256=digest(canonical({"dataset": dataset, "page": page, "at": at})),
                   failure_class="product_sql_semantics" if observed != expected else None)


def revision(revision_id: str, page: str, at: str, body: str) -> dict:
    return {"revision_id": revision_id, "page_id": page, "revised_at": at,
            "title": "Synthetic runtime probe", "body": body, "source_url": None}


def execute_cases(x: Experiment, ddl: str, query: str, fixture: dict) -> None:
    x.sql(ddl)
    x.check("original_ddl_executed", True, True, ddl_sha256=digest(ddl), query_sha256=digest(query))
    metadata = x.rows("SELECT VERSION() AS version, @@character_set_server AS server_charset, "
                      "@@collation_server AS server_collation, @@character_set_client AS client_charset;")[0]
    collations = x.rows("SELECT COLUMN_NAME, COLLATION_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION;",
                        [x.env["CRACI_MARIADB_DATABASE"], "wiki_revision_events"])
    emit("database_metadata", **metadata, column_collations=collations)
    before_import = x.rows("SELECT UTC_TIMESTAMP(6) AS instant;")[0]["instant"]
    x.sql(x.import_sql(fixture))
    x.check("source_fixture_count", len(fixture["revisions"]),
            int(x.rows("SELECT COUNT(*) AS n FROM wiki_revision_events;")[0]["n"]))
    boundaries = [
        ("before_first", "demo:harbor-energy", "2025-01-09T23:59:59.999Z"),
        ("first_exact", "demo:harbor-energy", "2025-01-10T00:00:00Z"),
        ("second_before", "demo:harbor-energy", "2025-01-10T23:59:59.999Z"),
        ("second_exact", "demo:harbor-energy", "2025-01-11T00:00:00Z"),
        ("third_before", "demo:harbor-energy", "2025-01-11T02:59:59.999Z"),
        ("third_exact", "demo:harbor-energy", "2025-01-11T03:00:00Z"),
        ("second_page", "demo:civic-debate", "2025-02-01T00:00:00Z"),
        ("missing_page", "missing", "2025-03-01T00:00:00Z"),
    ]
    for case, page, at in boundaries:
        x.compare(case, query, fixture, page, at)

    edge = {"dataset_id": "j26-runtime-edges", "dataset_license": "CC0 synthetic harness fixture",
            "provenance": "SYNTHETIC", "revisions": [
                revision("301", "case:Harbor", "2025-03-01T00:00:00Z", "Uppercase page, separate identity"),
                revision("302", "case:harbor", "2025-03-01T01:00:00Z", "Lowercase page, separate identity"),
                revision("303", "accent:cafe", "2025-03-01T00:00:00Z", "Unaccented page"),
                revision("304", "accent:café", "2025-03-01T01:00:00Z", "Accented page"),
                revision("305", "unicode:ää😀", "2025-03-01T00:00:00.001Z", "Ää Öö é e\u0301 河 😀\nquote ' slash \\ tab\t ; DROP TABLE imaginary; --"),
                revision("306", "ties", "2025-03-02T00:00:00Z", "First simultaneous revision"),
                revision("307", "ties", "2025-03-02T00:00:00Z", "Second simultaneous revision"),
                revision("308", "milliseconds", "2025-03-03T00:00:00.001Z", "First millisecond"),
                revision("309", "milliseconds", "2025-03-03T00:00:00.002Z", "Second millisecond"),
            ]}
    x.sql(x.import_sql(edge))
    for case, page, at in [
        ("case_distinct_latest", "case:Harbor", "2025-03-01T02:00:00Z"),
        ("case_no_cross_page_history", "case:harbor", "2025-03-01T00:30:00Z"),
        ("diacritic_distinct_latest", "accent:cafe", "2025-03-01T02:00:00Z"),
        ("diacritic_no_cross_page_history", "accent:café", "2025-03-01T00:30:00Z"),
        ("unicode_parameter_roundtrip", "unicode:ää😀", "2025-03-01T00:00:00.001Z"),
        ("same_time_ambiguity", "ties", "2025-03-02T00:00:00Z"),
        ("millisecond_before", "milliseconds", "2025-03-03T00:00:00Z"),
        ("millisecond_exact_first", "milliseconds", "2025-03-03T00:00:00.001Z"),
        ("millisecond_exact_second", "milliseconds", "2025-03-03T00:00:00.002Z"),
    ]:
        x.compare(case, query, edge, page, at)

    # A failed statement does not implicitly roll back an InnoDB transaction.
    # The batch client exits on its first error; disconnect must roll back both
    # the new row and the attempted duplicate. No --force or INSERT IGNORE.
    before = int(x.rows("SELECT COUNT(*) AS n FROM wiki_revision_events;")[0]["n"])
    trial = revision("99901", "rollback-only", "2025-03-04T00:00:00Z", "Must not survive")
    duplicate = x.sql(x.import_sql(fixture, [trial, fixture["revisions"][0]]), allow_error=True)
    x.check("duplicate_key_refused", True, duplicate.returncode != 0 and "ERROR 1062" in duplicate.stderr,
            client_exit=duplicate.returncode, error=duplicate.stderr[-500:])
    x.check("duplicate_transaction_rolled_back", before,
            int(x.rows("SELECT COUNT(*) AS n FROM wiki_revision_events;")[0]["n"]))
    x.check("partial_insert_absent", "0", x.rows("SELECT COUNT(*) AS n FROM wiki_revision_events "
            "WHERE dataset_id = ? AND source_revision_id = ?;", [fixture["dataset_id"], "99901"])[0]["n"])
    bad_fixture = copy.deepcopy(fixture)
    bad_fixture["revisions"].append(copy.deepcopy(fixture["revisions"][0]))
    refused = x.cli(bad_fixture, "demo:harbor-energy", "2025-03-04T00:00:00Z")
    x.check("product_duplicate_identity_refused", [2, "DUPLICATE_REVISION"],
            [refused.returncode, json.loads(refused.stderr).get("reason")])

    # Dataset identity must be as exact as the offline source contract.
    first_scope = {"dataset_id": "RuntimeDataset", "dataset_license": "CC0 synthetic",
                   "provenance": "SYNTHETIC", "revisions": [revision("801", "scope", "2025-03-05T00:00:00Z", "Dataset A")]}
    second_scope = copy.deepcopy(first_scope)
    second_scope["dataset_id"] = "runtimedataset"
    second_scope["revisions"][0]["body"] = "Distinct dataset B"
    x.sql(x.import_sql(first_scope))
    scope_result = x.sql(x.import_sql(second_scope), allow_error=True)
    x.check("dataset_case_identity_distinct", 0, scope_result.returncode,
            error=scope_result.stderr[-500:], failure_class="product_sql_collation" if scope_result.returncode else None)
    x.compare("dataset_upper_scope", query, first_scope, "scope", "2025-03-05T00:00:00Z")
    if scope_result.returncode == 0:
        x.compare("dataset_lower_scope", query, second_scope, "scope", "2025-03-05T00:00:00Z")

    # Import/correction history is independent of Wikipedia's revision clock.
    system_query = ("SELECT content_body, content_sha256 FROM wiki_revision_events "
                    "FOR SYSTEM_TIME AS OF TIMESTAMP ? WHERE dataset_id = ? AND source_revision_id = ?;")
    original = fixture["revisions"][1]
    after_import = x.rows("SELECT UTC_TIMESTAMP(6) AS instant;")[0]["instant"]
    corrected_body = original["body"] + "\nSynthetic import correction."
    x.sql(prepared("UPDATE wiki_revision_events SET content_body = ?, content_sha256 = ? "
                   "WHERE dataset_id = ? AND source_revision_id = ?;",
                   [corrected_body, digest(corrected_body), fixture["dataset_id"], original["revision_id"]]))
    x.check("system_time_before_import_empty", [], x.rows(system_query,
            [before_import, fixture["dataset_id"], original["revision_id"]]))
    x.check("revision_time_is_not_ingestion_time", [], x.rows(system_query,
            [sql_time(original["revised_at"]), fixture["dataset_id"], original["revision_id"]]))
    history = x.rows(system_query, [after_import, fixture["dataset_id"], original["revision_id"]])
    x.check("system_time_preserves_original_import", [{"content_body": original["body"], "content_sha256": digest(original["body"])}], history)
    corrected = copy.deepcopy(fixture)
    corrected["revisions"][1]["body"] = corrected_body
    x.compare("current_import_correction", query, corrected, "demo:harbor-energy", "2025-01-11T01:00:00Z")
    x.check("two_ingestion_versions_recorded", "2", x.rows("SELECT COUNT(*) AS n FROM wiki_revision_events "
            "FOR SYSTEM_TIME ALL WHERE dataset_id = ? AND source_revision_id = ?;",
            [fixture["dataset_id"], original["revision_id"]])[0]["n"])

    durable_query = ("SELECT dataset_id, source_revision_id, page_id, revised_at_utc, content_body, "
                     "content_sha256, ROW_START, ROW_END FROM wiki_revision_events FOR SYSTEM_TIME ALL "
                     "ORDER BY BINARY dataset_id, BINARY source_revision_id, ROW_START;")
    before_restart = x.rows(durable_query)
    container_before = x.command(["ps", "-q", "db"]).strip()
    started_before = require_process(run(["docker", "inspect", "--format", "{{.State.StartedAt}}", container_before],
                                         timeout=30), "pre-restart time").strip()
    x.command(["restart", "--timeout", "15", "db"], timeout=45)
    x.command(["up", "-d", "--no-recreate", "--wait", "--wait-timeout", "90"], timeout=120)
    container_after = x.command(["ps", "-q", "db"]).strip()
    started_after = require_process(run(["docker", "inspect", "--format", "{{.State.StartedAt}}", container_after],
                                        timeout=30), "post-restart time").strip()
    x.check("same_container_restarted", container_before, container_after)
    x.check("container_restart_observed", True, started_before != started_after,
            started_before=started_before, started_after=started_after)
    after_restart = x.rows(durable_query)
    x.check("restart_preserves_current_and_history", digest(canonical(before_restart)), digest(canonical(after_restart)),
            before_rows=len(before_restart), after_rows=len(after_restart))


def main() -> int:
    experiment = None
    cleanup_needed = False
    fatal = None
    env = os.environ.copy()
    try:
        source = Path(os.environ["SOURCE_DIR"]).resolve()
        expected = os.environ["EXPECTED_SOURCE_SHA"]
        image = os.environ["CRACI_MARIADB_IMAGE"]
        if not re.fullmatch(r"(?:docker\.io/)?(?:library/)?mariadb(?::[A-Za-z0-9_.-]+)?@sha256:[0-9a-f]{64}", image):
            raise ValueError("CRACI_MARIADB_IMAGE must name an official MariaDB image pinned by sha256")
        binding = source_binding(source, expected)
        product = source / PRODUCT
        ddl, query = extract_source_sql((product / "sql/schema.sql").read_text(encoding="utf-8"))
        fixture = json.loads((product / "fixtures/synthetic.json").read_text(encoding="utf-8"))
        if fixture.get("provenance") != "SYNTHETIC" or len(fixture.get("revisions", [])) != 4:
            raise ValueError("Expected the pinned four-revision synthetic source fixture; review changed source")
        nonce = uuid.uuid4().hex
        project = "j26-mariadb-" + nonce
        env["CRACI_MARIADB_DATABASE"] = "j26_" + nonce
        emit("binding", source_commit=expected, source_files=binding, image=image, compose_project=project,
             harness_sha256=digest(Path(__file__).read_bytes()),
             compose_sha256=digest(Path(__file__).with_name("mariadb-compose.yml").read_bytes()),
             synthetic_only=True, provider_database=False, sponsor_dataset=False, published_host_ports=False)
        with tempfile.TemporaryDirectory(prefix="j26-mariadb-") as temporary:
            experiment = Experiment(source, env, project, Path(temporary))
            require_process(run(["docker", "version", "--format", "{{.Server.Version}}"], timeout=30), "Docker server")
            cleanup_needed = True
            experiment.command(["up", "-d", "--wait", "--wait-timeout", "90"], timeout=180)
            image_metadata = json.loads(require_process(run(["docker", "image", "inspect", image, "--format",
                '{"id":{{json .Id}},"repo_digests":{{json .RepoDigests}},"architecture":{{json .Architecture}},"os":{{json .Os}}}'],
                timeout=30), "pinned image inspect"))
            container_id = experiment.command(["ps", "-q", "db"]).strip()
            used_image = require_process(run(["docker", "inspect", "--format", "{{.Image}}", container_id],
                                             timeout=30), "container image inspect").strip()
            host_machine = os.uname().machine
            emit("image_metadata", requested=image, actual=image_metadata, container_image_id=used_image,
                 host_machine=host_machine, container_machine=experiment.command(["exec", "-T", "db", "uname", "-m"]).strip())
            experiment.check("image_digest_verified", True,
                any(item.endswith("@" + image.split("@", 1)[1]) for item in image_metadata["repo_digests"]))
            experiment.check("container_uses_pinned_image", image_metadata["id"], used_image)
            experiment.check("native_container_architecture", {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(host_machine),
                             image_metadata["architecture"])
            experiment.check("container_os", "linux", image_metadata["os"])
            execute_cases(experiment, ddl, query, fixture)
            experiment.check("source_bytes_unchanged", binding, source_binding(source, expected))
    except Exception as error:
        fatal = {"type": type(error).__name__, "message": str(error)[:2500]}
        emit("execution_error", **fatal)
    finally:
        if cleanup_needed and experiment is not None:
            try:
                experiment.command(["down", "--volumes", "--remove-orphans", "--timeout", "15"], timeout=60)
                containers = require_process(run(["docker", "ps", "-a", "--filter",
                    "label=com.docker.compose.project=" + experiment.project, "--format", "{{.ID}}"], timeout=30), "cleanup containers")
                volumes = require_process(run(["docker", "volume", "ls", "--filter",
                    "label=com.docker.compose.project=" + experiment.project, "--format", "{{.Name}}"], timeout=30), "cleanup volumes")
                experiment.check("own_resources_removed", ["", ""], [containers.strip(), volumes.strip()])
            except Exception as error:
                fatal = fatal or {"type": type(error).__name__, "message": str(error)[:2500]}
                emit("cleanup_error", project=experiment.project, message=str(error)[:1500])
    checks = experiment.checks if experiment is not None else []
    failures = [row["case"] for row in checks if not row["passed"]]
    emit("summary", source_commit=os.environ.get("EXPECTED_SOURCE_SHA"),
         passed=sum(row["passed"] for row in checks), failed=len(failures),
         failed_cases=failures, execution_error=fatal,
         result="error" if fatal else "fail" if failures else "pass",
         external_provider_verified=False, sponsor_data_verified=False)
    return 2 if fatal else 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
