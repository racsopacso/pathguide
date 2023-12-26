from __future__ import annotations

from pydantic import BaseModel
import typing as t
import itertools as it
from functools import cached_property

from config import ROOT_DIR

from tomli import loads as tloads

from dataclasses import dataclass

class RulesObj(BaseModel):
    name: str
    full_name: str
    text: t.Optional[str] = None
    replacements: t.Dict[str, t.Dict] = {}
    article_redirect: t.Optional[str] = None
    url_prefix: t.ClassVar[t.Optional[str]] = None

    def __hash__(self):
        return hash(self.name)
    
    def get_article(self) -> str:
        try:
            return ROOT_DIR + self.url_prefix + self.article_redirect if self.article_redirect else ROOT_DIR + self.url_prefix + self.name
        
        except:
            raise NotImplementedError


def parse_feat_elem(feat_elems: t.List[str | t.List[str]]):
    for feat_elem in feat_elems:
        if isinstance(feat_elem, str):
            ret = feat_dict.get(feat_elem, NonDBFeat(name=feat_elem))

            if isinstance(ret, NonDBFeat):
                yield ret
            
            else:
                if ret.subfeats:
                    yield from parse_feat_elem(ret.subfeats)
                else:
                    yield ret

        else:
            yield FeatUnion(name = feat_elem[0], elements = [obj for obj in parse_feat_elem(feat_elem[1:])])

class Required(BaseModel):
    feats: t.List[str | t.List[str]] = []

    @cached_property
    def feat_objs(self) -> t.List[Feat | FeatUnion | NonDBFeat]:
        return {obj for obj in parse_feat_elem(self.feats)}
    
    def __add__(self, other):
        if type(other) != type(self):
            return NotImplemented
        else:
            return type(self)(**{k: getattr(self, k) + getattr(other, k) for k in self.model_fields.keys()})

class Style(RulesObj):
    upsides: t.List[str] = []
    downsides: t.List[str] = []
    required: t.Optional[Required] = None
    url_prefix: t.ClassVar[t.Optional[str]] = "styles/"
    recommended: t.Optional[Required] = None

    def __repr__(self):
        return "Style(" + ", ".join((self.name, str(self.replacements), str(self.required))) + ")"

class Replacement(BaseModel):
    condition: str
    replace_dict: t.Dict[str, t.Any]

class Class(Style):
    provides: t.Optional[Required] = None
    url_prefix: t.ClassVar[t.Optional[str]] = "classes/"

    def __repr__(self):
        return "Class(" + ", ".join((self.name, str(self.replacements), str(self.required))) + ")"

class Feat(RulesObj):
    subfeats: t.Optional[t.List[str]] = None
    prereqs: t.Optional[Required] = None
    url_prefix: t.ClassVar[t.Optional[str]] = "feats/"
    is_union: t.ClassVar[bool] = False
    is_db: t.ClassVar[bool] = True

    @property
    def title(self):
        if self.subfeats:
            return self.full_name + " Line"
    
    @property
    def full_line(self):
        if self.subfeats:
            return " -> ".join((feat.title() for feat in self.subfeats))
        else:
            return self.full_name

    def is_provided(self, provideddict: t.Dict[str, t.Set[str]]):
        return self.name in provideddict.feats

class NonDBFeat(BaseModel):
    name: str
    is_db: t.ClassVar[bool] = False

    def get_article(self):
        return ""
    
    @cached_property
    def full_name(self):
        return self.name.title().replace("_", " ")
    
    def __hash__(self):
        return hash(self.name)
    
    def is_provided(self, provideddict: t.Dict[str, t.Set[str]]):
        return self.name in provideddict.feats


class FeatUnion(BaseModel):
    name: str
    elements: t.List[Feat | NonDBFeat]
    is_union: t.ClassVar[bool] = True
    
    def __iter__(self):
        return iter(self.elements)
    
    def __hash__(self):
        return hash(self.name)
    
    def is_provided(self, provideddict: t.Dict[str, t.Set[str]]):
        return self.name in provideddict.feats

@dataclass
class OmniMap:
    styles: t.Dict[str, Style]
    classes: t.Dict[str, Class]
    feats: t.Dict[str, Feat]

# def amend_toml_subelems(style: str | dict):
#     if not isinstance(style, dict):
#         return style
    
#     return {k: amend_toml_subelems(v) for k, v in style.items()}

def parse_toml_elem(base_name: str, style: dict, cls) -> RulesObj:
    if "full_name" not in style:
        style["full_name"] = base_name.title().replace("_", " ")

    style["name"] = base_name

    ret = cls.model_validate(style)
    
    return ret

with open("feats.toml", "r") as f:
    toml = tloads(f.read())
    feat_dict = {base_name: parse_toml_elem(base_name, feat, Feat) for base_name, feat in toml.items()}

with open("styles.toml", "r") as f:
    toml = tloads(f.read())
    style_dict = {base_name: parse_toml_elem(base_name, style, Style) for base_name, style in toml.items()}

with open("classes.toml", "r") as f:
    toml = tloads(f.read())
    class_dict = {base_name: parse_toml_elem(base_name, cls, Class) for base_name, cls in toml.items()}

omnimap = OmniMap(styles=style_dict, classes = class_dict, feats = feat_dict)