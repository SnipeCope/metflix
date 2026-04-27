import time
import getpass
import json
import socket
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
ROOT_CONFIG_PATH = ROOT_DIR / "config.json"
SERVER_CONFIG_PATH = ROOT_DIR / "server" / "config.json"


def root_default_config():
    return {
        "client": {
            "host": "127.0.0.1",
            "port": 8000,
            "public_host": "met.flix",
        },
        "server": {
            "url": "http://met.flix:9000",
            "device_hint": "Metflix backend service",
        },
        "auth": {
            "password": "CHANGE_ME",
        },
    }


def server_default_config():
    return {
        "server": {
            "host": "127.0.0.1",
            "port": 9000,
            "public_host": "met.flix",
        },
        "library": {
            "videos_root": "./Videos",
        },
        "auth": {
            "password": "CHANGE_ME",
        },
    }


def deep_merge(base, incoming):
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def validate_json_object(path, fallback):
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON in {path}: {error}") from error
    except OSError as error:
        raise SystemExit(f"Could not read {path}: {error}") from error

    if not isinstance(data, dict):
        raise SystemExit(f"Invalid JSON structure in {path}: top-level object must be a JSON object.")

    return deep_merge(fallback, data)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        rendered = json.dumps(payload, indent=2)
        json.loads(rendered)
        path.write_text(rendered + "\n", encoding="utf-8")
    except OSError as error:
        raise SystemExit(f"Could not write {path}: {error}") from error


def detect_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def prompt_password():
    while True:
        password = getpass.getpass("Enter a password for the server: ").strip()
        if password:
            return password
        print("Password cannot be empty.")


def configure():
    detected_ip = detect_local_ip()
    password = prompt_password()

    root_config = validate_json_object(ROOT_CONFIG_PATH, root_default_config())
    server_config = validate_json_object(SERVER_CONFIG_PATH, server_default_config())

    server_port = int(server_config.get("server", {}).get("port", 9000))
    client_port = int(root_config.get("client", {}).get("port", 8000))

    root_config.setdefault("client", {})
    root_config["client"]["host"] = "0.0.0.0"
    root_config["client"]["port"] = client_port
    root_config["client"]["public_host"] = detected_ip

    root_config.setdefault("server", {})
    root_config["server"]["url"] = f"http://{detected_ip}:{server_port}"
    root_config["server"]["device_hint"] = root_config["server"].get("device_hint", "Metflix backend service")

    root_config.setdefault("auth", {})
    root_config["auth"]["password"] = password

    server_config.setdefault("server", {})
    server_config["server"]["host"] = "0.0.0.0"
    server_config["server"]["port"] = server_port
    server_config["server"]["public_host"] = detected_ip

    server_config.setdefault("library", {})
    server_config["library"]["videos_root"] = server_config["library"].get("videos_root", "./Videos")

    server_config.setdefault("auth", {})
    server_config["auth"]["password"] = password

    write_json(ROOT_CONFIG_PATH, root_config)
    write_json(SERVER_CONFIG_PATH, server_config)

    print("Setup complete.\n")
    print(f"Detected local IP: {detected_ip}")
    print(f"Web client URL: http://{detected_ip}:{client_port}")
    print(f"Backend URL: http://{detected_ip}:{server_port}")
    print(f"Updated: {ROOT_CONFIG_PATH}")
    print(f"Updated: {SERVER_CONFIG_PATH}\n")
    print("You can close this window now.")

    time.sleep(5)


if __name__ == "__main__":
    configure()
