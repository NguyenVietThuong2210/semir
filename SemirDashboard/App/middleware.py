"""
RequestIDMiddleware — assigns a unique ID to every HTTP request.

- Stores the ID in thread-local storage so logger calls inside views/services
  automatically include it via RequestIDFilter.
- Exposes ``request.request_id`` for use in views.
- Adds ``X-Request-ID`` response header for client-side correlation.
"""

import uuid

from App.logging_utils import clear_request_id, set_request_id


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = uuid.uuid4().hex[:12]   # e.g. "a3f9c2b10d44"
        set_request_id(request_id)
        request.request_id = request_id
        try:
            response = self.get_response(request)
        finally:
            clear_request_id()
        response["X-Request-ID"] = request_id
        return response
