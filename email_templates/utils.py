import re

TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}")

def render_text(text: str, context: dict) -> str:
    """
    Replaces {{ token.path }} placeholders using a simple dot-path lookup.
    Example: {{ quotation.number }} or {{ property.site_id }}
    """
    if not text:
        return ""

    def lookup(path: str):
        parts = path.split(".")
        cur = context.get(parts[0])
        for p in parts[1:]:
            if cur is None:
                return ""
            # dict support
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                cur = getattr(cur, p, "")
        return "" if cur is None else str(cur)

    def repl(match):
        key = match.group(1)
        return lookup(key)

    return TOKEN_RE.sub(repl, text)
