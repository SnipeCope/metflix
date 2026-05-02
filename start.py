import json
import random
import secrets
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"
CONFIG_PATH = ROOT_DIR / "config.json"
SESSION_COOKIE = "metflix_session"

PAGE_ROUTES = {
    "/": "home.html",
    "/history": "history.html",
    "/manage-watched": "manage-watched.html",
}


def default_config():
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


def deep_merge(base, incoming):
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


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


CONFIG = load_json(CONFIG_PATH, default_config())
SESSIONS = set()
SESSIONS_LOCK = threading.Lock()


def ensure_config_file():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2), encoding="utf-8")


def clear_all_sessions():
    with SESSIONS_LOCK:
        SESSIONS.clear()


def config_get(*keys, default=None):
    current = CONFIG
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def configured_password():
    return str(config_get("auth", "password", default="CHANGE_ME"))


def parse_backend_url():
    raw_url = str(config_get("server", "url", default="http://met.flix:9000")).strip()
    parsed = urllib.parse.urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        parsed = urllib.parse.urlparse("http://met.flix:9000")
    return parsed


def local_ip_address():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def public_host_for(bind_host, configured_public_host):
    if configured_public_host:
        return configured_public_host
    if bind_host in {"127.0.0.1", "localhost"}:
        return "127.0.0.1"
    return local_ip_address()


def local_ui_url():
    bind_host = str(config_get("client", "host", default="127.0.0.1"))
    public_host = public_host_for(bind_host, config_get("client", "public_host", default="met.flix"))
    port = int(config_get("client", "port", default=8000))
    return f"http://{public_host}:{port}"


def backend_headers():
    return {"Accept": "application/json"}


def backend_url(path):
    base = parse_backend_url().geturl().rstrip("/")
    return f"{base}{path}"


def request_backend_json(path, method="GET", payload=None):
    data = None
    headers = backend_headers()
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(backend_url(path), data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_relative_path(relative_path):
    cleaned = relative_path.strip().replace("\\", "/").lstrip("/")
    if not cleaned or ".." in Path(cleaned).parts:
        return None
    return cleaned


def get_backend_connection_status():
    try:
        data = request_backend_json("/api/health")
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="ignore").strip()
        return {"connected": False, "message": details or f"Backend returned HTTP {error.code}."}
    except urllib.error.URLError as error:
        reason = getattr(error, "reason", None)
        target = parse_backend_url().geturl()
        if isinstance(reason, OSError) and getattr(reason, "winerror", None) == 10061:
            return {
                "connected": False,
                "message": f"Nothing is listening at {target}. Start the backend service first.",
            }
        return {
            "connected": False,
            "message": f"Backend service is unreachable at {target}. Check your network and make sure the backend is running.",
        }
    except Exception as error:
        return {"connected": False, "message": str(error)}

    return {
        "connected": True,
        "message": data.get("message") or f"Connected to {config_get('server', 'device_hint', default='Metflix backend service')}.",
        "hosting_enabled": bool(data.get("hosting_enabled", True)),
        "resolved_host": data.get("local_ip") or parse_backend_url().hostname or "met.flix",
    }


def flatten_library(main_categories):
    videos = []
    for main_category in main_categories:
        videos.extend(main_category.get("featured_videos", []))
        for subcategory in main_category.get("subcategories", []):
            videos.extend(subcategory.get("videos", []))
    deduped = {}
    for video in videos:
        deduped[video["id"]] = video
    return list(deduped.values())


def build_library():
    status = get_backend_connection_status()
    server_url = parse_backend_url()
    client_bind_host = str(config_get("client", "host", default="127.0.0.1"))
    client_public_host = public_host_for(client_bind_host, config_get("client", "public_host", default="met.flix"))
    client_port = int(config_get("client", "port", default=8000))
    info = {
        "client_url": local_ui_url(),
        "backend_url": server_url.geturl(),
        "client_port": client_port,
        "backend_port": server_url.port or 9000,
        "backend_host": server_url.hostname or "met.flix",
        "client_host": client_public_host,
        "backend_hint": config_get("server", "device_hint", default="Metflix backend service"),
        "videos_root": "Not provided by server",
        "main_category_count": 0,
        "subcategory_count": 0,
    }

    if not status["connected"]:
        return {
            "hosting_enabled": False,
            "source": "backend_service",
            "backend_connection": status,
            "source_error": status["message"],
            "main_categories": [],
            "all_videos": [],
            "video_count": 0,
            "info": info,
        }

    remote = request_backend_json("/api/library")
    info.update(
        {
            "backend_port": int(remote.get("port", server_url.port or 9000)),
            "videos_root": remote.get("videos_root", "Not provided by server"),
            "backend_host": status.get("resolved_host") or server_url.hostname or "met.flix",
            "main_category_count": len(remote.get("main_categories", [])),
            "subcategory_count": sum(len(category.get("subcategories", [])) for category in remote.get("main_categories", [])),
        }
    )
    main_categories = remote.get("main_categories", [])
    all_videos = flatten_library(main_categories)

    return {
        "hosting_enabled": bool(remote.get("hosting_enabled", True)),
        "source": "backend_service",
        "backend_connection": status,
        "source_error": None,
        "main_categories": main_categories,
        "all_videos": all_videos,
        "video_count": len(all_videos),
        "info": info,
    }


def json_bytes(payload):
    return json.dumps(payload).encode("utf-8")


class VideoServerHandler(SimpleHTTPRequestHandler):
    def safe_write(self, payload):
        try:
            self.wfile.write(payload)
            return True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return False

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def parse_cookies(self):
        cookie_header = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        return cookie

    def is_authenticated(self):
        cookies = self.parse_cookies()
        token = cookies.get(SESSION_COOKIE)
        if token is None:
            return False
        with SESSIONS_LOCK:
            return token.value in SESSIONS

    def create_session(self):
        token = secrets.token_urlsafe(24)
        with SESSIONS_LOCK:
            SESSIONS.add(token)
        return token

    def clear_session(self):
        cookies = self.parse_cookies()
        token = cookies.get(SESSION_COOKIE)
        if token:
            with SESSIONS_LOCK:
                SESSIONS.discard(token.value)

    def send_redirect(self, location):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def send_cookie(self, name, value, *, max_age=None, expires=None, httponly=True):
        cookie = SimpleCookie()
        cookie[name] = value
        cookie[name]["path"] = "/"
        cookie[name]["samesite"] = "Lax"
        if httponly:
            cookie[name]["httponly"] = True
        if max_age is not None:
            cookie[name]["max-age"] = str(max_age)
        if expires is not None:
            cookie[name]["expires"] = expires
        self.send_header("Set-Cookie", cookie.output(header="").strip())

    def end_json(self, payload, status=HTTPStatus.OK):
        body = json_bytes(payload)
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        self.safe_write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path.startswith("/api/"):
            return self.handle_api_get(parsed.path)

        if parsed.path.startswith("/static/"):
            return super().do_GET()

        if parsed.path in PAGE_ROUTES:
            self.path = f"/static/{PAGE_ROUTES[parsed.path]}"
            return super().do_GET()

        return self.send_redirect("/")

    def handle_api_get(self, path):
        if path == "/api/session":
            return self.end_json({"authenticated": self.is_authenticated()})

        if not self.is_authenticated():
            return self.end_json({"error": "Unauthorized"}, status=HTTPStatus.UNAUTHORIZED)

        if path == "/api/library":
            try:
                return self.end_json(build_library())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except Exception as error:
                return self.end_json({"error": str(error)}, status=HTTPStatus.BAD_GATEWAY)

        if path.startswith("/api/video/"):
            relative = normalize_relative_path(urllib.parse.unquote(path.removeprefix("/api/video/")))
            if not relative:
                return self.end_json({"error": "Invalid video path."}, status=HTTPStatus.BAD_REQUEST)
            return self.proxy_backend_video(relative)

        return self.end_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        body = self.read_json_body()

        if parsed.path == "/api/login":
            if body.get("password") != configured_password():
                return self.end_json({"error": "Wrong password."}, status=HTTPStatus.UNAUTHORIZED)
            token = self.create_session()
            payload = json_bytes({"ok": True})
            self.send_response(HTTPStatus.OK)
            self.send_cookie(SESSION_COOKIE, token, max_age=60 * 60 * 24 * 30)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == "/api/logout":
            self.clear_session()
            payload = json_bytes({"ok": True})
            self.send_response(HTTPStatus.OK)
            self.send_cookie(SESSION_COOKIE, "", max_age=0, expires="Thu, 01 Jan 1970 00:00:00 GMT")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return

        if not self.is_authenticated():
            return self.end_json({"error": "Unauthorized"}, status=HTTPStatus.UNAUTHORIZED)

        if parsed.path == "/api/host/toggle":
            try:
                payload = request_backend_json("/api/host/toggle", method="POST", payload=body or {})
            except Exception as error:
                return self.end_json({"error": str(error)}, status=HTTPStatus.BAD_GATEWAY)
            return self.end_json(payload)

        if parsed.path == "/api/delete":
            relative = body.get("video_id") or body.get("id") or ""
            relative = normalize_relative_path(relative)
            if not relative:
                return self.end_json({"error": "Invalid video path."}, status=HTTPStatus.BAD_REQUEST)
            try:
                payload = request_backend_json("/api/delete", method="POST", payload={"video_id": relative})
            except urllib.error.HTTPError as error:
                details = error.read().decode("utf-8", errors="ignore").strip()
                return self.end_json({"error": details or f"Backend returned HTTP {error.code}."}, status=error.code)
            except Exception as error:
                return self.end_json({"error": str(error)}, status=HTTPStatus.BAD_GATEWAY)
            return self.end_json(payload)

        return self.end_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/static/"):
            relative = path.removeprefix("/static/")
            return str((STATIC_DIR / relative).resolve())
        return str(ROOT_DIR)

    def proxy_backend_video(self, relative_path):
        request = urllib.request.Request(
            backend_url(f"/api/video/{urllib.parse.quote(relative_path)}"),
            headers=backend_headers() | ({ "Range": self.headers["Range"] } if self.headers.get("Range") else {}),
            method="GET",
        )

        try:
            response = urllib.request.urlopen(request, timeout=20)
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="ignore").strip()
            return self.end_json({"error": details or f"Backend returned HTTP {error.code}."}, status=error.code)
        except urllib.error.URLError:
            return self.end_json({"error": "Backend service is unreachable."}, status=HTTPStatus.BAD_GATEWAY)

        with response:
            try:
                self.send_response(response.status)
                for header, value in response.getheaders():
                    if header.lower() in {"connection", "transfer-encoding", "server", "date"}:
                        continue
                    self.send_header(header, value)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

            while True:
                chunk = response.read(1024 * 64)
                if not chunk:
                    break
                if not self.safe_write(chunk):
                    break

    def log_message(self, format, *args):
        return


def run():
    ensure_config_file()
    clear_all_sessions()
    bind_host = str(config_get("client", "host", default="127.0.0.1"))
    port = int(config_get("client", "port", default=8000))
    public_host = public_host_for(bind_host, config_get("client", "public_host", default="met.flix"))
    server = ThreadingHTTPServer((bind_host, port), VideoServerHandler)
    print(f"Web app running on http://{bind_host}:{port}")
    print(f"Web app public URL: http://{public_host}:{port}")
    print(f"Backend target: {parse_backend_url().geturl()}\n")
    print("Click Ctrl+C to exit")
    server.serve_forever()


if __name__ == "__main__":
    run()
