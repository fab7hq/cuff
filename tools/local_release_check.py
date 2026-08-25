"""Verify the built Cuff candidate and its one shared host payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PRODUCT = "cuff"
DISTRIBUTION = "cuff-cli"
VERSION = "0.2.2"
VALID_SAMPLES = 3
HOST_EXIT_CODES = tuple(range(256))
CHECK_FIELDS = {
    "ok", "errors", "work_item", "latest_claim", "selected_evidence", "record_count",
}


@dataclass(frozen=True)
class Completed:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def run(
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: Path | None = None,
    expected: tuple[int, ...] = (0,),
) -> Completed:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
        )
        result = Completed(argv, completed.returncode, completed.stdout, completed.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
        result = Completed(argv, 124, stdout, stderr)
    if result.returncode not in expected:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"{_redacted_argv(argv)} exited {result.returncode}; expected {expected}: {detail}"
        )
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def tree_sha256(root: Path) -> tuple[str, list[str]]:
    members = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for member in members:
        digest.update(member.encode())
        digest.update(b"\0")
        digest.update((root / member).read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest(), members


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object: {path}")
    return value


def require_live_controls(
    manifest_path: Path,
    preflight_path: Path,
    commit: str,
    hosts: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_json(manifest_path, "qualification manifest")
    preflight = load_json(preflight_path, "containment preflight")
    expected_candidate = {"version": VERSION, "commit": commit}
    qualification_id = manifest.get("qualification_id")
    if (
        manifest.get("schema") != 1
        or manifest.get("state") != "FROZEN"
        or not isinstance(qualification_id, str)
        or not qualification_id
        or manifest.get("candidate") != expected_candidate
        or manifest.get("hosts") != list(hosts)
        or manifest.get("cases") != ["current", "stale"]
        or manifest.get("valid_samples") != VALID_SAMPLES
        or manifest.get("deterministic_only") is not True
    ):
        raise RuntimeError("qualification manifest does not match the exact live candidate")
    policies = manifest.get("policies")
    if not isinstance(policies, dict):
        raise RuntimeError("qualification manifest policies are missing")
    for host in hosts:
        policy = policies.get(host)
        if not isinstance(policy, dict):
            raise RuntimeError(f"qualification policy is missing for {host}")
        for field in ("prompt_digest", "tool_policy_digest", "containment_policy_digest"):
            value = policy.get(field)
            if not isinstance(value, str) or not value.startswith("sha256:"):
                raise RuntimeError(f"qualification {field} is invalid for {host}")

    if (
        preflight.get("schema") != 1
        or preflight.get("qualification_id") != qualification_id
        or preflight.get("candidate") != expected_candidate
        or preflight.get("verdict") != "PASS"
    ):
        raise RuntimeError("containment preflight does not pass for the frozen qualification")
    lanes = preflight.get("lanes")
    if not isinstance(lanes, dict):
        raise RuntimeError("containment preflight lanes are missing")
    for host in hosts:
        lane = lanes.get(host)
        policy = policies[host]
        if (
            not isinstance(lane, dict)
            or lane.get("verdict") != "PASS"
            or lane.get("containment_policy_digest") != policy["containment_policy_digest"]
            or not isinstance(lane.get("tested_routes"), list)
            or not lane["tested_routes"]
            or not isinstance(lane.get("allowed_controls"), list)
            or not lane["allowed_controls"]
            or not isinstance(lane.get("denied_controls"), list)
            or not lane["denied_controls"]
            or not isinstance(lane.get("raw_evidence_digest"), str)
            or not lane["raw_evidence_digest"].startswith("sha256:")
        ):
            raise RuntimeError(f"containment preflight is incomplete for {host}")
    return manifest, preflight


def output_sha256(result: Completed) -> str:
    return "sha256:" + hashlib.sha256(
        result.stdout.encode() + b"\0" + result.stderr.encode()
    ).hexdigest()


def source_status(root: Path, env: dict[str, str]) -> str:
    return run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], env=env, cwd=root
    ).stdout


def isolated_environment(source: dict[str, str], lane: Path) -> dict[str, str]:
    allowed = ("PATH", "LANG", "LC_ALL", "TERM", "SSL_CERT_FILE", "SSL_CERT_DIR")
    env = {key: source[key] for key in allowed if key in source}
    home = lane / "user-home"
    temporary = lane / "tmp"
    home.mkdir(exist_ok=True)
    temporary.mkdir(exist_ok=True)
    env.update({
        "HOME": str(home),
        "TMPDIR": str(temporary),
        "USER": "cuff-e2e",
        "LOGNAME": "cuff-e2e",
    })
    return env


def candidate_commit(root: Path, requested: str | None, env: dict[str, str]) -> str:
    commit = run(["git", "rev-parse", requested or "HEAD"], env=env, cwd=root).stdout.strip()
    if len(commit) not in (40, 64) or any(character not in "0123456789abcdef" for character in commit):
        raise RuntimeError(f"invalid candidate commit: {commit}")
    return commit


def find_wheel(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.glob(f"{DISTRIBUTION.replace('-', '_')}-{VERSION}-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one {DISTRIBUTION} {VERSION} wheel in {dist_dir}")
    return wheels[0]


def inspect_artifacts(dist_dir: Path) -> tuple[Path, Path, dict[str, list[str]]]:
    wheel = find_wheel(dist_dir)
    sdists = sorted(dist_dir.glob(f"{DISTRIBUTION.replace('-', '_')}-{VERSION}.tar.gz"))
    if len(sdists) != 1:
        raise RuntimeError(f"expected one {DISTRIBUTION} {VERSION} sdist in {dist_dir}")
    sdist = sdists[0]
    with zipfile.ZipFile(wheel) as archive:
        wheel_members = sorted(name for name in archive.namelist() if not name.endswith("/"))
    if not wheel_members or any(
        not (name.startswith("cuff/") or name.startswith(f"cuff_cli-{VERSION}.dist-info/"))
        for name in wheel_members
    ):
        raise RuntimeError("wheel contains files outside the Cuff package and distribution metadata")
    with tarfile.open(sdist, "r:gz") as archive:
        sdist_members = sorted(member.name for member in archive.getmembers() if member.isfile())
    prefix = f"cuff_cli-{VERSION}/"
    allowed_roots = {"LICENSE", "PKG-INFO", "README.md", "pyproject.toml", "setup.cfg"}
    for name in sdist_members:
        if not name.startswith(prefix):
            raise RuntimeError(f"sdist member escapes its root: {name}")
        relative = name.removeprefix(prefix)
        if relative in allowed_roots:
            continue
        if relative.startswith("core/cuff/") or relative.startswith("core/cuff_cli.egg-info/"):
            continue
        raise RuntimeError(f"unexpected sdist member: {name}")
    return wheel, sdist, {"wheel": wheel_members, "sdist": sdist_members}


def require_versions(root: Path, payload: Path) -> None:
    import tomllib

    project = tomllib.loads((root / "pyproject.toml").read_text())
    lock = tomllib.loads((root / "uv.lock").read_text())
    manifests = [
        json.loads((payload / ".claude-plugin/plugin.json").read_text()),
        json.loads((payload / ".codex-plugin/plugin.json").read_text()),
    ]
    locked = next(package for package in lock["package"] if package["name"] == DISTRIBUTION)
    versions = {
        project["project"]["version"],
        locked["version"],
        *(manifest["version"] for manifest in manifests),
    }
    if versions != {VERSION}:
        raise RuntimeError(f"candidate metadata versions differ: {sorted(versions)}")
    action = (root / "action/action.yml").read_text()
    package = (root / "core/cuff/__init__.py").read_text()
    if f'default: "{VERSION}"' not in action or f'__version__ = "{VERSION}"' not in package:
        raise RuntimeError("action default or import version does not match the candidate")
    guidance = {
        "README.md": [f"cuff-cli=={VERSION}", "sandbox/cuff-02"],
        "RUNBOOK.md": [f"cuff-cli=={VERSION}", f"v{VERSION}"],
        "action/README.md": [f"action@v{VERSION}", f'version: "{VERSION}"'],
        "docs/product/roadmap.md": [f"## {VERSION} recovery projection"],
    }
    for relative, required in guidance.items():
        content = (root / relative).read_text()
        if any(value not in content for value in required):
            raise RuntimeError(f"current installation guidance is stale: {relative}")


def install_wheel(wheel: Path, lane: Path, env: dict[str, str]) -> tuple[Path, Completed]:
    bin_dir = lane / "bin"
    lane_env = env.copy()
    lane_env["UV_TOOL_DIR"] = str(lane / "uv-tools")
    lane_env["UV_TOOL_BIN_DIR"] = str(bin_dir)
    installed = run(
        ["uv", "tool", "install", "--force", "--no-index", str(wheel)],
        env=lane_env,
    )
    executable = (bin_dir / PRODUCT).resolve()
    if not executable.is_file():
        raise RuntimeError(f"installed executable is missing: {executable}")
    version = run([str(executable), "--version"], env=lane_env)
    if version.stdout.strip() != VERSION:
        raise RuntimeError(f"unexpected installed version: {version.stdout.strip()}")
    return executable, installed


def write_marketplace(
    marketplace: Path,
    payload: Path,
    commit: str,
    *,
    live: bool,
) -> None:
    source: str | dict[str, str]
    if live:
        source = {
            "source": "git-subdir",
            "url": "https://github.com/fab7hq/cuff.git",
            "path": "plugins/cuff",
            "sha": commit,
        }
    else:
        local_payload = marketplace / "plugins" / PRODUCT
        shutil.copytree(payload, local_payload)
        source = {"source": "local", "path": f"./plugins/{PRODUCT}"}

    claude_catalog = marketplace / ".claude-plugin" / "marketplace.json"
    claude_catalog.parent.mkdir(parents=True)
    claude_source: str | dict[str, str] = source
    if not live:
        claude_source = f"./plugins/{PRODUCT}"
    claude_catalog.write_text(
        json.dumps(
            {
                "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
                "name": "cuff-rc",
                "description": "Isolated Cuff release-candidate marketplace.",
                "owner": {"name": "Fab7"},
                "plugins": [
                    {
                        "name": PRODUCT,
                        "description": "Cuff release candidate.",
                        "version": VERSION,
                        "source": claude_source,
                        "category": "productivity",
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )

    codex_catalog = marketplace / ".agents" / "plugins" / "marketplace.json"
    codex_catalog.parent.mkdir(parents=True)
    codex_catalog.write_text(
        json.dumps(
            {
                "name": "cuff-rc",
                "interface": {"displayName": "Cuff release candidate"},
                "plugins": [
                    {
                        "name": PRODUCT,
                        "version": VERSION,
                        "source": source,
                        "policy": {
                            "installation": "AVAILABLE",
                            "authentication": "ON_INSTALL",
                        },
                        "category": "Productivity",
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )


def installed_payload(host_home: Path, manifest: str) -> Path:
    candidates: list[Path] = []
    for found in host_home.rglob(manifest):
        try:
            data = json.loads(found.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("name") == PRODUCT:
            candidates.append(found.parent.parent)
    if len(candidates) != 1:
        raise RuntimeError(f"expected one installed {PRODUCT} payload, found {len(candidates)}")
    return candidates[0]


def require_payload_match(source: Path, installed: Path) -> None:
    source_files = sorted(
        path.relative_to(source) for path in source.rglob("*") if path.is_file()
    )
    installed_files = sorted(
        path.relative_to(installed) for path in installed.rglob("*") if path.is_file()
    )
    missing = set(source_files) - set(installed_files)
    extras = set(installed_files) - set(source_files)
    allowed_extras = {
        relative
        for relative in extras
        if relative.parts[:2] == (".codex-plugin", "migrated-command-skills")
    }
    if missing or extras != allowed_extras:
        raise RuntimeError(
            f"installed payload file set differs; missing={sorted(missing)}, "
            f"unexpected={sorted(extras - allowed_extras)}"
        )
    for relative in source_files:
        if sha256(source / relative) != sha256(installed / relative):
            raise RuntimeError(f"installed payload differs: {relative}")


def install_plugin(
    host: str,
    marketplace: Path,
    payload: Path,
    lane: Path,
    env: dict[str, str],
) -> tuple[Path, list[Completed]]:
    host_home = lane / f"{host}-home"
    host_home.mkdir()
    lane_env = env.copy()
    if host == "claude":
        lane_env["CLAUDE_CONFIG_DIR"] = str(host_home)
        commands = [
            run(["claude", "plugin", "validate", "--strict", str(payload)], env=lane_env),
            run(["claude", "plugin", "marketplace", "add", str(marketplace)], env=lane_env),
            run(
                ["claude", "plugin", "install", f"{PRODUCT}@cuff-rc", "--scope", "user", "--yes"],
                env=lane_env,
            ),
            run(["claude", "plugin", "list"], env=lane_env),
        ]
        installed = installed_payload(host_home, ".claude-plugin/plugin.json")
    else:
        lane_env["CODEX_HOME"] = str(host_home)
        commands = [
            run(
                ["codex", "plugin", "marketplace", "add", str(marketplace), "--json"],
                env=lane_env,
            ),
            run(["codex", "plugin", "add", f"{PRODUCT}@cuff-rc", "--json"], env=lane_env),
            run(["codex", "plugin", "list"], env=lane_env),
        ]
        installed = installed_payload(host_home, ".codex-plugin/plugin.json")
    require_payload_match(payload, installed)
    return installed, commands


def initialize_consumer(
    executable: Path,
    lane: Path,
    env: dict[str, str],
    sample_id: str,
) -> dict[str, Any]:
    consumer = lane / "samples" / sample_id / "consumer"
    consumer.mkdir(parents=True)
    run(["git", "init", "-q"], env=env, cwd=consumer)
    run(["git", "config", "user.name", "Cuff E2E"], env=env, cwd=consumer)
    run(["git", "config", "user.email", "e2e@example.invalid"], env=env, cwd=consumer)
    subject = consumer / "subject.txt"
    subject.write_text("candidate\n")
    run(["git", "add", "subject.txt"], env=env, cwd=consumer)
    run(["git", "commit", "-qm", "neutral consumer"], env=env, cwd=consumer)

    initialized = run([str(executable), "init", "--json"], env=env, cwd=consumer)
    run(["git", "add", ".fab7/cuff/project.json"], env=env, cwd=consumer)
    run(["git", "commit", "-qm", "initialize cuff"], env=env, cwd=consumer)
    claimed = run(
        [
            str(executable), "claim", "--work-item", "release-e2e", "--summary",
            "Candidate verified", "--subject-path", "subject.txt", "--json",
        ],
        env=env,
        cwd=consumer,
    )
    claim = json.loads(claimed.stdout)["record"]
    failed = run(
        [
            str(executable), "verify", "--work-item", "release-e2e", "--claim", claim["id"],
            "--json", "--", sys.executable, "-c", "raise SystemExit(7)",
        ],
        env=env,
        cwd=consumer,
        expected=(1,),
    )
    passed = run(
        [
            str(executable), "verify", "--work-item", "release-e2e", "--claim", claim["id"],
            "--json", "--", sys.executable, "-c", "pass",
        ],
        env=env,
        cwd=consumer,
    )
    direct = run(
        [str(executable), "check", "--work-item", "release-e2e", "--json"],
        env=env,
        cwd=consumer,
    )
    return {
        "consumer": consumer,
        "subject": subject,
        "claim": claim,
        "initialized": initialized,
        "failed": failed,
        "passed": passed,
        "direct": direct,
    }


def invoke_host(
    host: str,
    consumer: Path,
    env: dict[str, str],
    model: str,
) -> Completed:
    if host == "claude":
        return run(
            [
                "claude", "-p",
                "/cuff:check --work-item release-e2e. Run the installed command now and return "
                "only its exact stdout JSON document, with no markdown or commentary.",
                "--output-format", "json", "--model", model,
            ],
            env=env,
            cwd=consumer,
            expected=HOST_EXIT_CODES,
        )
    return run(
        [
            "codex", "exec", "--ephemeral", "--json", "--sandbox", "read-only",
            "--ignore-rules",
            "-c", "mcp_servers={}",
            "-c", "shell_environment_policy.inherit=all",
            "-c", f"shell_environment_policy.set.PATH={json.dumps(env.get('PATH', ''))}",
            "-C", str(consumer),
            "Use $cuff:check for work item release-e2e. Run the installed skill now and return "
            "only its exact stdout JSON document, with no markdown or commentary.", "--model", model,
        ],
        env=env,
        cwd=consumer,
        expected=HOST_EXIT_CODES,
    )


def recursive_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in recursive_strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in recursive_strings(child)]
    return []


def check_results(output: str) -> list[dict[str, Any]]:
    containers: list[Any] = []
    try:
        containers.append(json.loads(output))
    except json.JSONDecodeError:
        for line in output.splitlines():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    candidates: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for container in containers:
        if isinstance(container, dict) and set(container) == CHECK_FIELDS:
            candidates.append(container)
        for content in recursive_strings(container):
            for index, character in enumerate(content):
                if character != "{":
                    continue
                try:
                    value, _end = decoder.raw_decode(content[index:])
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict) and set(value) == CHECK_FIELDS:
                    candidates.append(value)
    return candidates


def observed_models(output: str) -> list[str]:
    models: set[str] = set()
    containers: list[Any] = []
    for line in [output, *output.splitlines()]:
        try:
            containers.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"model", "model_name", "modelName"} and isinstance(child, str):
                    models.add(child)
                if key == "modelUsage" and isinstance(child, dict):
                    models.update(name for name in child if isinstance(name, str))
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for container in containers:
        visit(container)
    return sorted(models)


def require_host_result(result: Completed, expected: dict[str, Any]) -> dict[str, Any]:
    candidates = check_results(result.stdout)
    if expected not in candidates:
        raise RuntimeError(
            f"host did not return the direct Cuff projection; found {len(candidates)} candidates"
        )
    return expected


def observation(result: Completed, cuff_json: dict[str, Any] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "argv": _redacted_argv(result.argv),
        "exit_status": result.returncode,
        "output_digest": output_sha256(result),
    }
    if cuff_json is not None:
        data["cuff_json"] = cuff_json
    return data


def retain_host_output(lane: Path, sample_id: str, result: Completed) -> dict[str, Any]:
    observations = lane / "observations"
    observations.mkdir(exist_ok=True)
    path = observations / f"{sample_id}.json"
    sensitive_markers = ("access_token", "refresh_token", "api_key", "authorization: bearer", "sk-")

    def sanitize(value: str) -> tuple[str, bool]:
        lowered = value.lower()
        if any(marker in lowered for marker in sensitive_markers):
            return "<redacted-sensitive-output>", True
        return (
            value.replace(str(Path.home()), "<operator-home>").replace(str(lane), "<lane>"),
            False,
        )

    stdout, stdout_redacted = sanitize(result.stdout)
    stderr, stderr_redacted = sanitize(result.stderr)
    retained = {
        "argv": _redacted_argv(result.argv),
        "exit_status": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "sensitive_output_redacted": stdout_redacted or stderr_redacted,
    }
    path.write_text(json.dumps(retained, indent=2, sort_keys=True) + "\n")
    return {"path": str(path), "sha256": sha256(path), "output_digest": output_sha256(result)}


def sample_check(
    host: str,
    lane: Path,
    executable: Path,
    env: dict[str, str],
    model: str,
    case: str,
    index: int,
) -> dict[str, Any]:
    sample_id = f"{case}-{index:02d}"
    state = initialize_consumer(executable, lane, env, sample_id)
    if case == "stale":
        state["subject"].write_text("mutated\n")
        direct = run(
            [str(executable), "check", "--work-item", "release-e2e", "--json"],
            env=env,
            cwd=state["consumer"],
            expected=(1,),
        )
        direct_json = json.loads(direct.stdout)
        codes = [error["code"] for error in direct_json["errors"]]
        if "CUFF_SUBJECT_STALE" not in codes:
            raise RuntimeError("mutated subject did not produce CUFF_SUBJECT_STALE")
    else:
        direct = state["direct"]
        direct_json = json.loads(direct.stdout)

    before = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        env=env,
        cwd=state["consumer"],
    ).stdout
    host_result = invoke_host(host, state["consumer"], env, model)
    raw = retain_host_output(lane, sample_id, host_result)
    if host_result.returncode not in (0, 1):
        raise RuntimeError(f"{host} exited unexpectedly for {sample_id}: {host_result.returncode}")
    require_host_result(host_result, direct_json)
    models = observed_models(host_result.stdout)
    if not models:
        raise RuntimeError(f"{host} did not expose a resolved model for {sample_id}")
    after = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        env=env,
        cwd=state["consumer"],
    ).stdout
    if before != after:
        raise RuntimeError(f"{host} changed consumer state for {sample_id}")
    return {
        "id": sample_id,
        "case": case,
        "consumer": str(state["consumer"]),
        "resolved_models": models,
        "setup": {
            "init": observation(state["initialized"], json.loads(state["initialized"].stdout)),
            "claim": state["claim"],
            "failed_verify": observation(state["failed"], json.loads(state["failed"].stdout)),
            "passing_verify": observation(state["passed"], json.loads(state["passed"].stdout)),
        },
        "direct": observation(direct, direct_json),
        "host": observation(host_result, direct_json),
        "raw_host_output": raw,
        "consumer_status_before": before,
        "consumer_status_after": after,
    }


def _redacted_argv(argv: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for argument in argv:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
        elif argument in {"--api-key", "--token", "--password"}:
            redacted.append(argument)
            hide_next = True
        else:
            redacted.append(argument)
    return redacted


def lane_check(
    host: str,
    sandbox: Path,
    wheel: Path,
    payload: Path,
    commit: str,
    base_env: dict[str, str],
    *,
    live: bool,
    remote: bool,
    reuse_prepared: bool,
    model: str | None,
    prepared: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lane = sandbox / host
    if not lane.exists():
        lane.mkdir(parents=True)
    env = isolated_environment(base_env, lane)
    if reuse_prepared:
        executable = (lane / "bin" / PRODUCT).resolve()
        version = run([str(executable), "--version"], env=env)
        if version.stdout.strip() != VERSION:
            raise RuntimeError(f"unexpected prepared version: {version.stdout.strip()}")
        wheel_install = None
    else:
        executable, wheel_install = install_wheel(wheel, lane, env)
    env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
    if reuse_prepared:
        host_home = lane / f"{host}-home"
        installed = installed_payload(
            host_home,
            ".claude-plugin/plugin.json" if host == "claude" else ".codex-plugin/plugin.json",
        )
        require_payload_match(payload, installed)
        plugin_commands: list[Completed] = []
    else:
        marketplace = lane / "marketplace"
        write_marketplace(marketplace, payload, commit, live=remote)
        installed, plugin_commands = install_plugin(host, marketplace, payload, lane, env)
    host_version = run([host, "--version"], env=env)
    evidence: dict[str, Any] = dict(prepared or {})
    evidence.update({
        "host": host,
        "host_version": host_version.stdout.strip(),
        "requested_model": model,
        "marketplace_coordinate": f"{PRODUCT}@cuff-rc",
        "marketplace_candidate_commit": commit,
        "plugin_version": VERSION,
        "installed_payload": str(installed),
        "installed_check_digest": sha256(
            installed / ("commands/check.md" if host == "claude" else "skills/check/SKILL.md")
        ),
        "resolved_executable": str(executable),
        "resolved_version": VERSION,
    })
    if wheel_install is not None:
        evidence["wheel_install"] = observation(wheel_install)
    if plugin_commands:
        evidence["plugin_install"] = [observation(command) for command in plugin_commands]
    if not live:
        return evidence
    if not model:
        raise RuntimeError(f"--{host}-model is required with --live")

    if host == "claude":
        env["CLAUDE_CONFIG_DIR"] = str(lane / "claude-home")
    else:
        env["CODEX_HOME"] = str(lane / "codex-home")
    samples = [
        sample_check(host, lane, executable, env, model, case, index)
        for case in ("current", "stale")
        for index in range(1, VALID_SAMPLES + 1)
    ]
    evidence["samples"] = samples
    evidence["valid_samples"] = {
        case: sum(sample["case"] == case for sample in samples)
        for case in ("current", "stale")
    }
    evidence["observed_models"] = sorted({
        observed
        for sample in samples
        for observed in sample["resolved_models"]
    })
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", choices=("codex", "claude", "all"), default="all")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--prepare-auth", action="store_true")
    parser.add_argument("--reuse-prepared", action="store_true")
    parser.add_argument("--candidate-commit")
    parser.add_argument("--codex-model")
    parser.add_argument("--claude-model")
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--qualification-manifest", type=Path)
    parser.add_argument("--preflight-evidence", type=Path)
    args = parser.parse_args()
    if args.prepare_auth and args.live:
        parser.error("--prepare-auth and --live are separate phases")
    if args.reuse_prepared and not args.live:
        parser.error("--reuse-prepared requires --live")
    if args.live and (args.qualification_manifest is None or args.preflight_evidence is None):
        parser.error("--live requires --qualification-manifest and --preflight-evidence")

    root = Path(__file__).resolve().parents[1]
    workspace = root.parent
    sandbox = (args.evidence_dir or workspace / "sandbox" / "cuff-02" / "e2e").resolve()
    dist_dir = (args.dist_dir or workspace / "sandbox" / "cuff-02" / "dist").resolve()
    payload = root / "plugins" / PRODUCT
    base_env = os.environ.copy()
    require_versions(root, payload)
    before = source_status(root, base_env)
    if before:
        raise RuntimeError("release candidate source checkout must be clean")
    if (root / ".fab7").exists():
        raise RuntimeError("Cuff source checkout must not contain a Cuff ledger")
    commit = candidate_commit(root, args.candidate_commit, base_env)
    if commit != candidate_commit(root, None, base_env):
        raise RuntimeError("candidate commit must be the checked-out HEAD")
    wheel, sdist, artifact_members = inspect_artifacts(dist_dir)
    artifacts = [wheel, sdist]
    payload_digest, payload_members = tree_sha256(payload)
    evidence_path = sandbox / "release-candidate-evidence.json"
    prepared_result: dict[str, Any] | None = None
    if args.reuse_prepared:
        if not evidence_path.is_file():
            raise RuntimeError(f"prepared evidence is missing: {evidence_path}")
        prepared_result = json.loads(evidence_path.read_text())
        if prepared_result["candidate"]["commit"] != commit:
            raise RuntimeError("prepared evidence belongs to another candidate commit")
    else:
        if sandbox.exists():
            raise RuntimeError(f"evidence directory already exists: {sandbox}")
        sandbox.mkdir(parents=True)

    hosts = ("codex", "claude") if args.host == "all" else (args.host,)
    qualification: dict[str, Any] | None = None
    preflight: dict[str, Any] | None = None
    control_digests: tuple[str, str] | None = None
    if args.live:
        manifest_path = args.qualification_manifest.resolve()
        preflight_path = args.preflight_evidence.resolve()
        qualification, preflight = require_live_controls(
            manifest_path,
            preflight_path,
            commit,
            hosts,
        )
        control_digests = (sha256(manifest_path), sha256(preflight_path))
    lanes = {
        host: lane_check(
            host,
            sandbox,
            wheel,
            payload,
            commit,
            base_env,
            live=args.live,
            remote=args.live or args.prepare_auth,
            reuse_prepared=args.reuse_prepared,
            model=getattr(args, f"{host}_model"),
            prepared=(prepared_result or {}).get("lanes", {}).get(host),
        )
        for host in hosts
    }
    after = source_status(root, base_env)
    if before != after:
        raise RuntimeError("source repository status changed during E2E")
    if (root / ".fab7").exists():
        raise RuntimeError("E2E created a Cuff ledger under the source checkout")

    result = {
        "schema": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "candidate": {
            "version": VERSION,
            "commit": commit,
            "artifacts": [
                {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
                for path in artifacts
            ],
            "payload": "plugins/cuff",
            "payload_sha256": payload_digest,
            "payload_members": payload_members,
            "artifact_members": artifact_members,
        },
        "live": args.live,
        "prepared_auth": args.prepare_auth,
        "source_status_before": before,
        "source_status_after": after,
        "lanes": lanes,
    }
    if qualification is not None and preflight is not None:
        if control_digests != (
            sha256(args.qualification_manifest.resolve()),
            sha256(args.preflight_evidence.resolve()),
        ):
            raise RuntimeError("qualification controls changed during live execution")
        result["qualification"] = {
            "id": qualification["qualification_id"],
            "state": "PASS",
            "deterministic_only": True,
            "manifest_sha256": control_digests[0],
            "preflight_sha256": control_digests[1],
            "valid_samples": VALID_SAMPLES,
        }
    evidence_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.prepare_auth:
        for host in hosts:
            variable = "CLAUDE_CONFIG_DIR" if host == "claude" else "CODEX_HOME"
            print(
                f"{host}: HOME={sandbox / host / 'user-home'} "
                f"{variable}={sandbox / host / f'{host}-home'}"
            )
    print(evidence_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
