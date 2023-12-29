from typing import Any
from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from hypercorn.asyncio import serve
import asyncio
from hypercorn.config import Config
import logging
import typing as t
from pathguide import omnimap, FeatObjLink, RulesObj, Class
from itertools import zip_longest, chain
from config import ROOT_DIR
from fastapi.routing import APIRoute
from starlette.templating import _TemplateResponse
from functools import partial

from dataclasses import dataclass

config = Config()
config.bind = ['127.0.0.1:2345']
config.access_log_format = '%(R)s %(s)s %(st)s %(D)s %({Header}o)s'
config.accesslog = logging.getLogger(__name__)
config.loglevel = 'INFO'

app = FastAPI()

app.mount(ROOT_DIR+"static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

def parse_cookie_adj(cookie_adj: str, cookies: t.Dict[str, str]):
    # cookie_adj = e.g. rm.styles.twf
    op, key, obj = cookie_adj.split(".")
    cookie_str = cookies.get(key, "")

    match op:
        case "rm":
            idx = cookies[key].find(obj)
            length = len(obj) + 1
            
            val = cookie_str[:idx] + cookie_str[idx + length:]
        
        case "add":
            val = cookie_str + obj + " "

        case _:
            raise ValueError("Unrecognised cookie command")
    
    return key, val

def chain_of_providence(start: RulesObj):
    if start.type == "nondbfeat":
        return

    yield start
    
    if start.provides:
        for provided_obj in start.provides.objs:
            yield from chain_of_providence(provided_obj)

@dataclass
class PageResponse:
    html_page_name: str
    request: Request
    cookie_adj: t.Optional[str]
    other: t.Optional[t.Dict[str, t.Any]] = None

    def __post_init__(self):
        if self.cookie_adj:
            self.cookiekey, self.cookieval = parse_cookie_adj(self.cookie_adj, self.request.cookies)
            self.request.cookies[self.cookiekey] = self.cookieval
        
        self.attr_cache = {}

    def __getattr__(self, attr: str) -> t.Tuple[t.List[RulesObj], t.List[RulesObj]]:
        if attr in self.attr_cache:
            return self.attr_cache[attr]
        
        else:
            val = get_included_excluded(self.request.cookies, attr)
            self.attr_cache[attr] = val

            return val
    
    def get_provides(self):
        incl_styles, _ = self.styles
        incl_classes, _ = self.classes

        elem_chain = chain(incl_styles, incl_classes)

        return [feat for obj in elem_chain for feat in chain_of_providence(obj)]    
    
    def get_provided_dict(self):
        ret: t.Dict[str, t.Set[str]] = {}

        for obj in self.get_provides():
            if obj.type in ret:
                ret[obj.type].add(obj.name)
            else:
                ret[obj.type] = {obj.name}
        
        return ret


    def generate_response(self) -> _TemplateResponse:
        incl_classes, _ = self.classes
        provides = get_provides(incl_classes)

        other = self.other if self.other else {}

        resp = templates.TemplateResponse(self.html_page_name,
                                        {"request": self.request,
                                        "cookies": gen_sidebar(self.request.cookies),
                                        "provided_dict": self.get_provided_dict(),
                                        "omnimap": omnimap,
                                        "lookup_obj": self,
                                        "imports": {"zip_longest": zip_longest},
                                        "provides": provides,
                                        "ROOT_DIR": ROOT_DIR, 
                                        **other})
        
        if self.cookie_adj:
            resp.set_cookie(key = self.cookiekey, value = self.cookieval)
        
        return resp

def gen_sidebar(cookies: t.Dict[str, str]) -> t.Dict[str, t.Set[str]]:
    ret = {k: set(v.split()) for k, v in cookies.items()}
    return ret

page_map = {
    "feats": "feat.html",
    "styles": "style.html",
    "classes": "class.html"
}

def get_included_excluded(cookies: t.Dict[str, str], key: str) -> t.Tuple[t.List[RulesObj], t.List[RulesObj]]:
    included = []
    not_included = []

    cookie = cookies.get(key, [])

    for style in getattr(omnimap, key).values():
        if style.name in cookie:
            included.append(style)
        else:
            not_included.append(style)
    
    return included, not_included

def get_provides(classes: t.List[Class] | None) -> t.Set[FeatObjLink]:
    if not classes:
        return []
    
    return set(chain(*(cls.provides for cls in classes)))

@app.get(ROOT_DIR + "select/{page_name}", response_class=HTMLResponse)
async def select(request: Request, page_name: str, cookie_adj: t.Optional[str] = None):
    pr_obj = PageResponse("select.html", request, cookie_adj)

    to_render = list(getattr(omnimap, page_name).values())

    pr_obj.other = {"to_render": to_render, "name": page_name}

    return pr_obj.generate_response()

@app.get(ROOT_DIR + "{page_type}/{page_name}", response_class=HTMLResponse)
async def read_item(request: Request, page_type: str, page_name: str, cookie_adj: t.Optional[str] = None):
    pr_obj = PageResponse(page_map[page_type], request, cookie_adj)

    bod = getattr(omnimap, page_type)[page_name]

    pr_obj.other = {"body": bod}

    return pr_obj.generate_response()

@app.get(ROOT_DIR + "summary", response_class=HTMLResponse)
async def summary(request: Request, cookie_adj: t.Optional[str] = None):
    pr_obj = PageResponse("summary.html", request, cookie_adj)

    pr_obj.other = {
        "provided": pr_obj.get_provides()
    }

    return pr_obj.generate_response()

@app.get(ROOT_DIR, response_class=HTMLResponse)
async def main(request: Request, cookie_adj: t.Optional[str] = None):
    pr_obj = PageResponse("main.html", request, cookie_adj)

    return pr_obj.generate_response()


asyncio.run(serve(app, config))
