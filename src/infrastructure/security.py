from fastapi import Request


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app
        self._csp = (
            b"default-src 'self'; "
            b"script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com https://cdn.jsdelivr.net https://static.cloudflareinsights.com; "
            b"style-src 'self' 'unsafe-inline'; "
            b"img-src 'self' data: https://*.supabase.co; "
            b"font-src 'self'; "
            b"connect-src 'self'; "
            b"frame-ancestors 'none'; "
            b"form-action 'self'"
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                headers.extend([
                    (b"content-security-policy", self._csp),
                    (b"x-frame-options", b"DENY"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
