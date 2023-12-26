from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from hypercorn.asyncio import serve
import asyncio
from hypercorn.config import Config
import logging
import typing as t
from pathguide import omnimap, Required
from itertools import zip_longest, chain
from config import ROOT_DIR

config = Config()
config.bind = ['127.0.0.1:2345']
config.access_log_format = '%(R)s %(s)s %(st)s %(D)s %({Header}o)s'
config.accesslog = logging.getLogger(__name__)
config.loglevel = 'INFO'
#config.root_path = "/pathguide/"
#config.keyfile = "funkydiagrams.com_private_key.key"
#config.certfile = "funkydiagrams.com_ssl_certificate.cer"

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

def gen_sidebar(cookies: t.Dict[str, str]) -> t.Dict[str, t.List[str]]:
    ret = {k: v.split() for k, v in cookies.items()}
    print("gen_s", ret)
    return ret

page_map = {
    "feats": "feat.html",
    "styles": "style.html",
    "classes": "class.html"
}

def get_included_excluded(cookies: t.Dict[str, str], key: str):
    included = []
    not_included = []

    cookie = cookies.get(key, [])

    for style in getattr(omnimap, key).values():
        if style.name in cookie:
            included.append(style)
        else:
            not_included.append(style)
    
    return included, not_included

def get_provides(classes):
    if not classes:
        return Required()
    
    iterclasses = iter(cls.provides for cls in classes)
    cls = next(iterclasses)
    
    for itercls in iterclasses:
        cls = cls + itercls

    return cls
        

@app.get(ROOT_DIR + "select/{page_name}", response_class=HTMLResponse)
async def select(request: Request, page_name: str, cookie_adj: t.Optional[str] = None):
    print("wow")
    if cookie_adj:
        cookiekey, cookieval = parse_cookie_adj(cookie_adj, request.cookies)
        request.cookies[cookiekey] = cookieval

    included_styles, not_included_styles = get_included_excluded(request.cookies, "styles")
    included_classes, _ = get_included_excluded(request.cookies, "classes")

    provides = get_provides(included_classes)

    to_render = list(getattr(omnimap, page_name).values())

    resp = templates.TemplateResponse("select.html",
                                      {"request": request,
                                       "cookies": gen_sidebar(request.cookies),
                                       "omnimap": omnimap,
                                       "included_styles": included_styles,
                                       "not_included_styles": not_included_styles,
                                       "included_classes": included_classes,
                                       "name": page_name,
                                       "to_render": to_render, 
                                       "provides": provides,
                                       "ROOT_DIR": ROOT_DIR})
    
    if cookie_adj:
        print(cookiekey, cookieval)
        resp.set_cookie(key = cookiekey, value = cookieval)

    return resp

@app.get(ROOT_DIR + "{page_type}/{page_name}", response_class=HTMLResponse)
async def read_item(request: Request, page_type: str, page_name: str, cookie_adj: t.Optional[str] = None):
    print(request.scope.get("root_path"))
    bod = getattr(omnimap, page_type)[page_name]

    if cookie_adj:
        cookiekey, cookieval = parse_cookie_adj(cookie_adj, request.cookies)
        request.cookies[cookiekey] = cookieval
    
    included_styles, not_included_styles = get_included_excluded(request.cookies, "styles")
    included_classes, _ = get_included_excluded(request.cookies, "classes")

    provides = get_provides(included_classes)
    
    resp = templates.TemplateResponse(page_map[page_type], 
                                      {"request": request, 
                                       "cookies": gen_sidebar(request.cookies), 
                                       "body": bod, 
                                       "included_styles": included_styles,
                                       "included_classes": included_classes,
                                       "not_included_styles": not_included_styles,
                                       "imports": {"zip_longest": zip_longest},
                                       "provides": provides,
                                       "ROOT_DIR": ROOT_DIR})
    
    if cookie_adj:
        resp.set_cookie(key = cookiekey, value = cookieval)

    return resp

@app.get(ROOT_DIR + "summary", response_class=HTMLResponse)
async def summary(request: Request, cookie_adj: t.Optional[str] = None):
    if cookie_adj:
        cookiekey, cookieval = parse_cookie_adj(cookie_adj, request.cookies)
        request.cookies[cookiekey] = cookieval

    included_styles, not_included_styles = get_included_excluded(request.cookies, "styles")
    included_classes, _ = get_included_excluded(request.cookies, "classes")

    provides = get_provides(included_classes)

    required_feats = {feat for obj in chain(included_styles, included_classes) if obj.required for feat in obj.required.feat_objs}
    recommended_feats = {feat for obj in chain(included_styles, included_classes) if obj.recommended for feat in obj.recommended.feat_objs}

    resp = templates.TemplateResponse("summary.html",
                                      {"request": request,
                                       "cookies": gen_sidebar(request.cookies),
                                       "omnimap": omnimap,
                                       "included_styles": included_styles,
                                       "not_included_styles": not_included_styles,
                                       "included_classes": included_classes, 
                                       "required_feats": required_feats,
                                       "recommended_feats": recommended_feats,
                                       "provides": provides,
                                       "ROOT_DIR": ROOT_DIR})
    
    if cookie_adj:
        resp.set_cookie(key = cookiekey, value = cookieval)

    return resp


asyncio.run(serve(app, config))
