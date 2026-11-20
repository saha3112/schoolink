import math
from flask import request, url_for


PAGE_SIZE = 10          # every list in the application shows the same number of rows per page


def paginate(total, per_page, page):
    per_page = PAGE_SIZE    # the per-page value passed by older callers is ignored on purpose: one size everywhere
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), pages)
    return {"page": page, "pages": pages, "offset": (page - 1) * per_page, "per_page": per_page, "total": total}


def page_arg():
    try:
        return max(1, int(request.args.get("page", 1)))
    except ValueError:
        return 1


def page_url(page):
    args = request.args.to_dict()
    args["page"] = page
    return url_for(request.endpoint, **{**request.view_args, **args})


def to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def full_name(*parts):
    return " ".join(p.strip() for p in parts if p and p.strip())
