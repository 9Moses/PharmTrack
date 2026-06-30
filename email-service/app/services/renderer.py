"""
app/services/renderer.py — Email Service
Renders Jinja2 HTML email templates.
"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_template(template_name: str, context: dict) -> str:
    template = _env.get_template(template_name)
    return template.render(**context)
