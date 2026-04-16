from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def vstatic(path):
    """Return static URL with file mtime as cache-busting query parameter."""
    url = static(path)
    resolved_path = finders.find(path)

    if not resolved_path:
        return url

    # finders.find can return a list for duplicate matches.
    file_path = resolved_path[0] if isinstance(resolved_path, list) else resolved_path

    try:
        mtime = int(Path(file_path).stat().st_mtime)
    except OSError:
        return url

    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={mtime}"
