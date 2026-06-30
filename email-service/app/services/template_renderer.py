"""
app/services/template_renderer.py
Renders Jinja2 email templates from app/templates/.
"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_template(template_name: str, context: dict) -> str:
    template = _env.get_template(template_name)
    return template.render(**context)
