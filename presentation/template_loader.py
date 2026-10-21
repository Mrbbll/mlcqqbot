"""读取并渲染项目内的 Markdown 回复模板。"""
from functools import lru_cache
from pathlib import Path
from string import Template


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=None)
def _read_template(name: str) -> str:
    """从固定模板目录读取 UTF-8 模板并缓存结果。"""
    template_path = (_TEMPLATE_DIR / name).resolve()
    try:
        template_path.relative_to(_TEMPLATE_DIR.resolve())
    except ValueError as exc:
        raise ValueError("模板路径必须位于 presentation/templates 中") from exc
    return template_path.read_text(encoding="utf-8").rstrip("\r\n")


def load_template(name: str) -> str:
    """读取没有变量占位符的 Markdown 模板。"""
    return _read_template(name)


def render_template(name: str, values: dict[str, object]) -> str:
    """将参数填入 Markdown 模板；普通文本参数需由调用方先转义。"""
    template = Template(_read_template(name))
    return template.substitute({key: str(value) for key, value in values.items()})
