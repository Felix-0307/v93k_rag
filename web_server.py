#!/usr/bin/env python3
"""V93K RAG Web Server - 静态文件 + /api/* 反向代理到 FastAPI :8000。

依赖：FastAPI 服务必须先在 :8000 跑起来，否则 /api/* 返回 503。

启动:
  终端 1: python -m uvicorn main:app --host 0.0.0.0 --port 8000
  终端 2: python web_server.py        # 静态文件 + 反向代理（默认 :8888）
"""
import http.client
import http.server
import json
import os
import socketserver
from urllib.parse import unquote

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONT_PORT = 8888


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """GET / POST：
    - /api/*  → 反向代理到 FastAPI :8000
    - 其他    → 当作静态文件，从 web_ui/dist/ 取
    """

    # ---------- API 代理 ----------
    def _proxy_to_backend(self, method):
        """把 /api/* 请求转发到 FastAPI，并把响应原样返回。

        - 若是 SSE（Content-Type: text/event-stream）：边收边转发，长超时 300s
        - 否则：一次性读完再转发（原有行为，向后兼容）
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
            # 长超时：SSE 流式可能数分钟，LLM 慢也常见
            conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=300)
            conn.request(method, self.path, body=body, headers=headers)
            resp = conn.getresponse()

            backend_headers = list(resp.getheaders())
            is_sse = False
            self.send_response(resp.status)
            # 不透传这些头（HTTP/1.0 默认 + 我们手动管连接关闭）
            skip = {"transfer-encoding", "connection", "content-length"}
            for k, v in backend_headers:
                kl = k.lower()
                if kl in skip:
                    continue
                if kl == "content-type" and v.startswith("text/event-stream"):
                    is_sse = True
                self.send_header(k, v)
            self.send_header("Access-Control-Allow-Origin", "*")

            if is_sse:
                # SSE：关 keep-alive，读完即关连接
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    while True:
                        chunk = resp.read1(8192)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    # 客户端断开（浏览器关闭/导航走），正常情况
                    pass
                conn.close()
                return

            # 非 SSE：原行为（一次性读 + 一次性写）
            data = resp.read()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            conn.close()
        except (ConnectionRefusedError, OSError):
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "FastAPI 后端未运行",
                "detail": f"无法连接 {BACKEND_HOST}:{BACKEND_PORT}，请先启动 uvicorn",
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy_to_backend("GET")
        self._serve_static()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._proxy_to_backend("POST")
        self.send_response(404)
        self.end_headers()

    def do_HEAD(self):
        if self.path.startswith("/api/"):
            # 健康检查走代理
            try:
                conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=5)
                conn.request("HEAD", self.path)
                resp = conn.getresponse()
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() in ("transfer-encoding", "connection"):
                        continue
                    self.send_header(k, v)
                self.end_headers()
                conn.close()
            except (ConnectionRefusedError, OSError):
                self.send_response(503)
                self.end_headers()
            return
        # 静态资源：仿照 GET 流程判断 200/404
        path = self._safe_static_path()
        if path and os.path.isfile(path):
            self.send_response(200)
            mime, _ = self._guess_mime(path)
            self.send_header("Content-Type", mime)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    # ---------- 静态文件 ----------
    def _safe_static_path(self):
        base_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "web_ui", "dist"))
        raw = unquote(self.path)
        if raw in ("/", "/index.html"):
            rel = "index.html"
        else:
            rel = raw.lstrip("/")
        candidate = os.path.realpath(os.path.join(base_dir, rel))
        if not candidate.startswith(base_dir):
            return None
        return candidate

    def _serve_static(self):
        path = self._safe_static_path()
        if not path or not os.path.isfile(path):
            self.send_error(404, f"File not found: {self.path}")
            return
        mime, _ = self._guess_mime(path)
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError as e:
            self.send_error(500, str(e))

    @staticmethod
    def _guess_mime(path):
        import mimetypes
        return mimetypes.guess_type(path)

    # 关闭 access log（前端调试时可打开）
    def log_message(self, format, *args):
        return


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print(f"前端静态 + API 代理 → http://localhost:{FRONT_PORT}")
    print(f"反向代理 FastAPI {BACKEND_HOST}:{BACKEND_PORT} （须先启动 uvicorn）")
    with ThreadedTCPServer(("", FRONT_PORT), ProxyHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")