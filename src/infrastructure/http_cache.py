class CacheControlMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path.startswith("/checkout") or path.startswith("/logistic"):
            cache_value = b"no-cache, private"
        elif path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        else:
            cache_value = b"public, max-age=600, stale-while-revalidate=60"

        async def send_with_cache(message):
            if message["type"] == "http.response.start":
                content_type = b""
                for k, v in message.get("headers", []):
                    if k == b"content-type":
                        content_type = v
                        break
                if content_type.startswith(b"text/html"):
                    headers = list(message.get("headers", []))
                    headers.append((b"cache-control", cache_value))
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cache)
