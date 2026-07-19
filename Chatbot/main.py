"""Process entrypoint that starts all chatbot services."""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

SERVICES = [
    {
        "name": "orchestrator",
        "script": BASE_DIR / "runners" / "main_orchestrator.py",
        "port_env": "ORCHESTRATOR_PORT",
        "host_env": "API_HOST",
        "default_port": 8017,
    },
    {
        "name": "sql_generator",
        "script": BASE_DIR / "runners" / "main_sql_generator.py",
        "port_env": "SQL_GENERATOR_PORT",
        "host_env": "API_HOST",
        "default_port": 8018,
    },
    {
        "name": "validator",
        "script": BASE_DIR / "runners" / "main_validator.py",
        "port_env": "VALIDATOR_PORT",
        "host_env": "API_HOST",
        "default_port": 8019,
    },
    {
        "name": "formatter",
        "script": BASE_DIR / "runners" / "main_formatter.py",
        "port_env": "FORMATTER_PORT",
        "host_env": "API_HOST",
        "default_port": 8020,
    },
    {
        "name": "whatsapp_adapter",
        "script": BASE_DIR / "runners" / "main_whatsapp.py",
        "port_env": "WHATSAPP_ADAPTER_PORT",
        "host_env": "API_HOST",
        "default_port": 8021,
    },
    {
        "name": "frontend",
        "script": BASE_DIR / "runners" / "main_frontend.py",
        "port_env": "FRONTEND_PORT",
        "host_env": "FRONTEND_HOST",
        "default_port": 8080,
    },
]


def stop_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    """Terminate all child processes gracefully, then force kill if needed."""
    for _, proc in processes:
        if proc.poll() is None:
            proc.terminate()

    deadline = time.time() + 10
    for name, proc in processes:
        if proc.poll() is not None:
            continue
        timeout = max(0.0, deadline - time.time())
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[main] forcing stop for {name} (pid={proc.pid})", flush=True)
            proc.kill()


def read_port(service: dict, env: dict) -> int:
    """Read service port from environment with fallback to default."""
    raw = env.get(service["port_env"])
    if raw is None or raw == "":
        return service["default_port"]
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{service['port_env']} must be an integer, got: {raw!r}")


def read_host(service: dict, env: dict) -> str:
    """Read service host from environment with fallback to API_HOST."""
    host_env = service.get("host_env")
    if host_env:
        raw = env.get(host_env)
        if raw:
            return raw
    return env.get("API_HOST", "0.0.0.0")


def is_port_available(host: str, port: int) -> bool:
    """Return True when a host:port can be bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def main() -> int:
    child_env = os.environ.copy()
    # Reload should be off for containerized/process-managed execution.
    child_env.setdefault("API_RELOAD", "false")
    processes: list[tuple[str, subprocess.Popen]] = []

    def _shutdown_handler(signum, _frame):
        print(f"[main] received signal {signum}; stopping services", flush=True)
        stop_processes(processes)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    startup_items: list[tuple[str, Path, str, int]] = []
    for service in SERVICES:
        name = service["name"]
        script = service["script"]
        if not script.exists():
            print(f"[main] missing runner script: {script}", flush=True)
            stop_processes(processes)
            return 1

        try:
            host = read_host(service, child_env)
            port = read_port(service, child_env)
        except ValueError as exc:
            print(f"[main] invalid port configuration for {name}: {exc}", flush=True)
            return 1
        startup_items.append((name, script, host, port))

    busy_ports: list[tuple[str, str, int]] = []
    for name, _, host, port in startup_items:
        if not is_port_available(host, port):
            busy_ports.append((name, host, port))

    if busy_ports:
        print("[main] cannot start services because these ports are already in use:", flush=True)
        for name, host, port in busy_ports:
            print(f"[main] - {name}: {host}:{port}", flush=True)
        print(
            "[main] stop the conflicting process(es) or change *_PORT variables, then retry.",
            flush=True,
        )
        return 1

    for name, script, _, _ in startup_items:
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(BASE_DIR),
            env=child_env,
        )
        processes.append((name, proc))
        print(f"[main] started {name} (pid={proc.pid})", flush=True)

    try:
        while True:
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    print(
                        f"[main] service {name} exited with code {code}; shutting down others",
                        flush=True,
                    )
                    stop_processes(processes)
                    return code
            time.sleep(1)
    except KeyboardInterrupt:
        print("[main] keyboard interrupt received; stopping services", flush=True)
        stop_processes(processes)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
