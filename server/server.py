import json
import mimetypes
import random
import socket
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.json"
STATE_PATH = ROOT_DIR / "runtime_state.json"
VIDEOS_ROOT = Path("./Videos")
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def default_config():
    return {
        "server": {
            "host": "127.0.0.1",
            "port": 9000,
            "public_host": "met.flix",
        },
        "library": {
            "videos_root": str(VIDEOS_ROOT),
        },
        "auth": {
            "password": "CHANGE_ME",
        },
    }


def default_state():
    return {"hosting_enabled": True}


def load_json(path, fallback):
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return fallback
    if not isinstance(data, dict):
        return fallback
    return deep_merge(fallback, data)


def deep_merge(base, incoming):
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


CONFIG = load_json(CONFIG_PATH, default_config())
STATE = default_state()


def save_state():
    return


def ensure_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2), encoding="utf-8")


def clear_runtime_state_file():
    try:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
    except OSError:
        return


def local_ip_address():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def config_get(*keys, default=None):
    current = CONFIG
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def public_host_for(bind_host, configured_public_host):
    if configured_public_host:
        return configured_public_host
    if bind_host in {"127.0.0.1", "localhost"}:
        return "127.0.0.1"
    return local_ip_address()


def normalize_relative_path(relative_path):
    cleaned = relative_path.strip().replace("\\", "/").lstrip("/")
    if not cleaned or ".." in Path(cleaned).parts:
        return None
    return cleaned


def videos_root():
    configured_root = Path(str(config_get("library", "videos_root", default=str(VIDEOS_ROOT))))
    if not configured_root.is_absolute():
        configured_root = (ROOT_DIR / configured_root).resolve()
    return configured_root


def resolve_video_path(relative_path):
    normalized = normalize_relative_path(relative_path)
    if not normalized:
        return None
    root = videos_root()
    file_path = (root / normalized).resolve()
    if not str(file_path).startswith(str(root)):
        return None
    return file_path


def human_title(filename):
    title = Path(filename).stem.replace("-", " ").strip()
    if not title:
        return "Untitled"
    return title[:1].upper() + title[1:]


def video_payload(root, file_path, main_category, subcategory):
    return {
        "id": file_path.relative_to(root).as_posix(),
        "title": human_title(file_path.name),
        "filename": file_path.name,
        "main_category": main_category,
        "subcategory": subcategory,
        "extension": file_path.suffix.lower(),
    }


def scan_videos():
    root = videos_root()
    main_categories = []

    if not root.exists():
        return {"main_categories": [], "message": f"{root} was not found on the server."}

    for main_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        subcategories = []
        featured_pool = []

        for sub_dir in sorted([p for p in main_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
            videos = []
            for file_path in sorted(sub_dir.iterdir(), key=lambda p: p.name.lower()):
                if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                payload = video_payload(root, file_path, main_dir.name, sub_dir.name)
                videos.append(payload)
                featured_pool.append(payload)

            if videos:
                subcategories.append(
                    {
                        "name": sub_dir.name,
                        "videos": videos,
                        "featured": random.choice(videos),
                        "video_count": len(videos),
                    }
                )

        if subcategories:
            random.shuffle(featured_pool)
            featured_videos = featured_pool[: min(8, len(featured_pool))]
            main_categories.append(
                {
                    "name": main_dir.name,
                    "subcategories": subcategories,
                    "featured_videos": featured_videos,
                    "video_count": len(featured_pool),
                }
            )

    return {"main_categories": main_categories, "message": f"Serving videos from {root}."}


class BackendHandler(BaseHTTPRequestHandler):
    server_version = "MetflixBackend/1.0"

    def text_response(self, text, status=HTTPStatus.OK):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json_response(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            return self.text_response(
                "\n".join(
                    [
                        "Metflix backend service is running.",
                        f"Port: {config_get('server', 'port', default=9000)}",
                        f"Videos root: {videos_root()}",
                        "Use /api/health for status.",
                        "Use /api/library for categories and subcategories.",
                    ]
                )
            )

        if parsed.path == "/api/health":
            return self.json_response(
                {
                    "ok": True,
                    "hosting_enabled": bool(STATE.get("hosting_enabled", True)),
                    "message": f"Media server is online on port {config_get('server', 'port', default=9000)}.",
                    "port": int(config_get("server", "port", default=9000)),
                    "videos_root": str(videos_root()),
                    "local_ip": local_ip_address(),
                }
            )

        if parsed.path == "/api/library":
            data = scan_videos()
            return self.json_response(
                {
                    "hosting_enabled": bool(STATE.get("hosting_enabled", True)),
                    "main_categories": data["main_categories"],
                    "message": data["message"],
                    "videos_root": str(videos_root()),
                    "port": int(config_get("server", "port", default=9000)),
                }
            )

        if parsed.path.startswith("/api/video/"):
            if not STATE.get("hosting_enabled", True):
                return self.json_response({"error": "Hosting is turned off on the backend."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            relative = normalize_relative_path(urllib.parse.unquote(parsed.path.removeprefix("/api/video/")))
            if not relative:
                return self.json_response({"error": "Invalid video path."}, status=HTTPStatus.BAD_REQUEST)
            return self.serve_video(relative)

        return self.json_response({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            body = {}

        if parsed.path == "/api/host/toggle":
            requested = body.get("enabled")
            if isinstance(requested, bool):
                STATE["hosting_enabled"] = requested
            else:
                STATE["hosting_enabled"] = not STATE.get("hosting_enabled", True)
            save_state()
            return self.json_response({"hosting_enabled": bool(STATE["hosting_enabled"])})

        if parsed.path == "/api/delete":
            relative = body.get("video_id") or body.get("id") or ""
            file_path = resolve_video_path(relative)
            if not file_path or not file_path.is_file():
                return self.json_response({"error": "Video not found."}, status=HTTPStatus.NOT_FOUND)
            try:
                file_path.unlink()
            except OSError as error:
                return self.json_response({"error": f"Delete failed: {error}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return self.json_response({"ok": True, "deleted": normalize_relative_path(relative)})

        return self.json_response({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def serve_video(self, relative_path):
        root = videos_root()
        file_path = resolve_video_path(relative_path)
        if not file_path or not file_path.is_file():
            return self.json_response({"error": "Video not found."}, status=HTTPStatus.NOT_FOUND)

        size = file_path.stat().st_size
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        start = 0
        end = size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")

        if range_header and range_header.startswith("bytes="):
            range_spec = range_header.split("=", 1)[1]
            start_text, _, end_text = range_spec.partition("-")
            if start_text:
                start = int(start_text)
            if end_text:
                end = int(end_text)
            status = HTTPStatus.PARTIAL_CONTENT

        if start >= size or end >= size or start > end:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        with file_path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1024 * 64, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    break
                remaining -= len(chunk)

    def log_message(self, format, *args):
        return


def run():
    ensure_config()
    clear_runtime_state_file()
    STATE["hosting_enabled"] = True
    bind_host = str(config_get("server", "host", default="127.0.0.1"))
    port = int(config_get("server", "port", default=9000))
    public_host = public_host_for(bind_host, config_get("server", "public_host", default="127.0.0.1"))
    try:
        server = ThreadingHTTPServer((bind_host, port), BackendHandler)
    except OSError as error:
        if getattr(error, "errno", None) == 98:
            print(f"Port {port} is already in use on the backend.")
            print("Pick another port in server/config.json and update the root config.json server URL.")
            return
        raise
    print(f"Backend service running on http://{bind_host}:{port}")
    print(f"Backend public URL: http://{public_host}:{port}")
    print(f"Videos root: {videos_root()}")
    server.serve_forever()


if __name__ == "__main__":
    run()
import json
import mimetypes
import random
import socket
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.json"
STATE_PATH = ROOT_DIR / "runtime_state.json"
VIDEOS_ROOT = Path("./Videos")
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def default_config():
    return {
        "server": {
            "host": "127.0.0.1",
            "port": 9000,
            "public_host": "127.0.0.1",
        },
        "library": {
            "videos_root": str(VIDEOS_ROOT),
        },
    }


def default_state():
    return {"hosting_enabled": True}


def load_json(path, fallback):
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return fallback
    if not isinstance(data, dict):
        return fallback
    return deep_merge(fallback, data)


def deep_merge(base, incoming):
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


CONFIG = load_json(CONFIG_PATH, default_config())
STATE = default_state()


def save_state():
    return


def ensure_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2), encoding="utf-8")


def clear_runtime_state_file():
    try:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
    except OSError:
        return


def local_ip_address():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def config_get(*keys, default=None):
    current = CONFIG
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def public_host_for(bind_host, configured_public_host):
    if configured_public_host:
        return configured_public_host
    if bind_host in {"127.0.0.1", "localhost"}:
        return "127.0.0.1"
    return local_ip_address()


def normalize_relative_path(relative_path):
    cleaned = relative_path.strip().replace("\\", "/").lstrip("/")
    if not cleaned or ".." in Path(cleaned).parts:
        return None
    return cleaned


def videos_root():
    configured_root = Path(str(config_get("library", "videos_root", default=str(VIDEOS_ROOT))))
    if not configured_root.is_absolute():
        configured_root = (ROOT_DIR / configured_root).resolve()
    return configured_root


def resolve_video_path(relative_path):
    normalized = normalize_relative_path(relative_path)
    if not normalized:
        return None
    root = videos_root()
    file_path = (root / normalized).resolve()
    if not str(file_path).startswith(str(root)):
        return None
    return file_path


def human_title(filename):
    title = Path(filename).stem.replace("-", " ").strip()
    if not title:
        return "Untitled"
    return title[:1].upper() + title[1:]


def video_payload(root, file_path, main_category, subcategory):
    return {
        "id": file_path.relative_to(root).as_posix(),
        "title": human_title(file_path.name),
        "filename": file_path.name,
        "main_category": main_category,
        "subcategory": subcategory,
        "extension": file_path.suffix.lower(),
    }


def scan_videos():
    root = videos_root()
    main_categories = []

    if not root.exists():
        return {"main_categories": [], "message": f"{root} was not found on the server."}

    for main_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        subcategories = []
        featured_pool = []

        for sub_dir in sorted([p for p in main_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
            videos = []
            for file_path in sorted(sub_dir.iterdir(), key=lambda p: p.name.lower()):
                if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                payload = video_payload(root, file_path, main_dir.name, sub_dir.name)
                videos.append(payload)
                featured_pool.append(payload)

            if videos:
                subcategories.append(
                    {
                        "name": sub_dir.name,
                        "videos": videos,
                        "featured": random.choice(videos),
                        "video_count": len(videos),
                    }
                )

        if subcategories:
            random.shuffle(featured_pool)
            featured_videos = featured_pool[: min(8, len(featured_pool))]
            main_categories.append(
                {
                    "name": main_dir.name,
                    "subcategories": subcategories,
                    "featured_videos": featured_videos,
                    "video_count": len(featured_pool),
                }
            )

    return {"main_categories": main_categories, "message": f"Serving videos from {root}."}


class BackendHandler(BaseHTTPRequestHandler):
    server_version = "MetflixBackend/1.0"

    def text_response(self, text, status=HTTPStatus.OK):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json_response(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            return self.text_response(
                "\n".join(
                    [
                        "Metflix backend service is running.",
                        f"Port: {config_get('server', 'port', default=9000)}",
                        f"Videos root: {videos_root()}",
                        "Use /api/health for status.",
                        "Use /api/library for categories and subcategories.",
                    ]
                )
            )

        if parsed.path == "/api/health":
            return self.json_response(
                {
                    "ok": True,
                    "hosting_enabled": bool(STATE.get("hosting_enabled", True)),
                    "message": f"Media server is online on port {config_get('server', 'port', default=9000)}.",
                    "port": int(config_get("server", "port", default=9000)),
                    "videos_root": str(videos_root()),
                    "local_ip": local_ip_address(),
                }
            )

        if parsed.path == "/api/library":
            data = scan_videos()
            return self.json_response(
                {
                    "hosting_enabled": bool(STATE.get("hosting_enabled", True)),
                    "main_categories": data["main_categories"],
                    "message": data["message"],
                    "videos_root": str(videos_root()),
                    "port": int(config_get("server", "port", default=9000)),
                }
            )

        if parsed.path.startswith("/api/video/"):
            if not STATE.get("hosting_enabled", True):
                return self.json_response({"error": "Hosting is turned off on the backend."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            relative = normalize_relative_path(urllib.parse.unquote(parsed.path.removeprefix("/api/video/")))
            if not relative:
                return self.json_response({"error": "Invalid video path."}, status=HTTPStatus.BAD_REQUEST)
            return self.serve_video(relative)

        return self.json_response({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            body = {}

        if parsed.path == "/api/host/toggle":
            requested = body.get("enabled")
            if isinstance(requested, bool):
                STATE["hosting_enabled"] = requested
            else:
                STATE["hosting_enabled"] = not STATE.get("hosting_enabled", True)
            save_state()
            return self.json_response({"hosting_enabled": bool(STATE["hosting_enabled"])})

        if parsed.path == "/api/delete":
            relative = body.get("video_id") or body.get("id") or ""
            file_path = resolve_video_path(relative)
            if not file_path or not file_path.is_file():
                return self.json_response({"error": "Video not found."}, status=HTTPStatus.NOT_FOUND)
            try:
                file_path.unlink()
            except OSError as error:
                return self.json_response({"error": f"Delete failed: {error}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return self.json_response({"ok": True, "deleted": normalize_relative_path(relative)})

        return self.json_response({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def serve_video(self, relative_path):
        root = videos_root()
        file_path = resolve_video_path(relative_path)
        if not file_path or not file_path.is_file():
            return self.json_response({"error": "Video not found."}, status=HTTPStatus.NOT_FOUND)

        size = file_path.stat().st_size
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        start = 0
        end = size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")

        if range_header and range_header.startswith("bytes="):
            range_spec = range_header.split("=", 1)[1]
            start_text, _, end_text = range_spec.partition("-")
            if start_text:
                start = int(start_text)
            if end_text:
                end = int(end_text)
            status = HTTPStatus.PARTIAL_CONTENT

        if start >= size or end >= size or start > end:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        with file_path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1024 * 64, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    break
                remaining -= len(chunk)

    def log_message(self, format, *args):
        return


def run():
    ensure_config()
    clear_runtime_state_file()
    STATE["hosting_enabled"] = True
    bind_host = str(config_get("server", "host", default="127.0.0.1"))
    port = int(config_get("server", "port", default=9000))
    public_host = public_host_for(bind_host, config_get("server", "public_host", default="127.0.0.1"))
    try:
        server = ThreadingHTTPServer((bind_host, port), BackendHandler)
    except OSError as error:
        if getattr(error, "errno", None) == 98:
            print(f"Port {port} is already in use on the backend.")
            print("Pick another port in server/config.json and update the root config.json server URL.")
            return
        raise
    print(f"Backend service running on http://{bind_host}:{port}")
    print(f"Backend public URL: http://{public_host}:{port}")
    print(f"Videos root: {videos_root()}\n")
    print("Click Ctrl+C to exit.")
    server.serve_forever()


if __name__ == "__main__":
    run()
