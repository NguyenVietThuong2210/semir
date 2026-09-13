"""
App/views/guideline.py

Serves the static "Guideline" reference site (a standalone, pre-built HTML
bundle — 8-level curriculum + glossary + interview Q&A) that lives under
App/templates/guideline/. These are NOT Django templates: they're
self-contained HTML documents with their own <html>/<head>/CSS, linked to
each other via plain relative hrefs (e.g. index.html -> "modules/L1_1_....
html", modules/*.html -> "_shared.css"). This view therefore serves raw
file bytes (never through Django's template engine, which would choke on
or mis-render any literal "{{" / "{%" that happens to appear as English/
Vietnamese prose in the curriculum content) at a URL path that exactly
mirrors the on-disk path under guideline/, so every existing relative link
in the bundle resolves correctly with zero edits to the 100+ source files.

Content is refreshed by overwriting App/templates/guideline/ wholesale from
an external source (see .claude/skills/sync-guideline/SKILL.md) — this view
reads from disk on every request (no caching), so a resync takes effect
immediately with no code change and no server restart.

Gated behind the "data.guideline" permission (same pattern as the
pre-existing "data.formulas" page) — @requires_perm already implies
@login_required, so an anonymous visitor is always redirected to login
first, matching the "phải login mới vào được" requirement.
"""
import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse

from App.permissions import requires_perm

GUIDELINE_ROOT = (Path(settings.BASE_DIR) / "App" / "templates" / "guideline").resolve()

# Injected right after the opening <body ...> tag of every served HTML page —
# NOT baked into the source files (which get wholesale-overwritten on every
# resync), so this survives a resync automatically. Sticky top bar, kept
# visually distinct from the curriculum content's own styling since we don't
# control that CSS.
_BANNER = (
    b'<div style="position:sticky;top:0;z-index:99999;background:#0d2b4e;'
    b'color:#fff;padding:8px 16px;font-family:sans-serif;font-size:13px;'
    b'display:flex;gap:20px;align-items:center;">'
    b'<a href="/guideline/" style="color:#fff;text-decoration:none;">'
    b'\xe2\x9a\xa1 Guideline Home</a>'
    b'<a href="/" style="color:#9ecbff;text-decoration:none;">'
    b'\xe2\x86\x90 Back to Dashboard</a>'
    b'</div>'
)
_BODY_TAG_RE = re.compile(rb"(<body[^>]*>)", re.IGNORECASE)


@requires_perm("data.guideline")
def guideline_view(request, subpath=""):
    """Serve one file from App/templates/guideline/, path-traversal-safe.

    subpath="" (the /guideline/ index) serves index.html. Any subpath is
    resolved relative to GUIDELINE_ROOT and MUST still be inside it after
    resolution (blocks "../", absolute paths, symlink escapes, etc.) — the
    only security-relevant logic in this file, since everything else is a
    plain byte passthrough of pre-built static content."""
    rel = (subpath or "index.html").strip("/")
    target = (GUIDELINE_ROOT / rel).resolve()

    if target != GUIDELINE_ROOT and GUIDELINE_ROOT not in target.parents:
        raise Http404("Not found")
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise Http404("Not found")

    content_type, _ = mimetypes.guess_type(str(target))
    content_type = content_type or "application/octet-stream"
    data = target.read_bytes()

    if content_type == "text/html":
        data, n = _BODY_TAG_RE.subn(rb"\1" + _BANNER, data, count=1)
        if n == 0:
            # No recognizable <body> tag (shouldn't happen for these files,
            # but never fail to serve the page just because the banner
            # couldn't be injected) -- serve the original bytes as-is.
            data = target.read_bytes()

    return HttpResponse(data, content_type=content_type)
