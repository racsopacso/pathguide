from __future__ import annotations

from pydantic import BaseModel
import typing as t
import itertools as it
from functools import cached_property

from config import ROOT_DIR

from tomli import loads as tloads

from dataclasses import dataclass

class TaggedText(BaseModel):
    tag: str
    text: str

    # looks like ["classes"]["ranger"]["text"] = TaggedText(tag = "attribute", text = "...")
    tagmap: t.Optional[t.Dict[str, t.Dict[str, str]]] = None

    def get_text(self, elems: t.Dict[str, t.Set[str]]):
        if self.tagmap:
            for category, catdict in elems.items():
                for item in catdict:
                    if category in self.tagmap and item in self.tagmap[category]:
                        return self.tagmap[category][item]
        
        return self.text
    

def gen_title(name: str):
    itername = iter(name)

    ret = next(itername).upper()
    cap = False

    for char in itername:
        match char:
            case "_":
                ret += " "
                cap = True

            case "-":
                ret += char
                cap = True
            
            case _:
                if cap:
                    ret += char.upper()
                    cap = False
                
                else:
                    ret += char
    
    return ret

class TextList(BaseModel):
    text_list: t.List[TaggedText | str]
    
    def __getitem__(self, idx):
        return self.text_list[idx]
    
    def __iter__(self):
        return iter(self.text_list)
    
    def set_up_tagmap(self, category: str, item: str, newtext: t.Tuple[str, str]):
        for text_obj in self:
            if isinstance(text_obj, str):
                continue

            if newtext[0] == text_obj.tag:
                if not text_obj.tagmap:
                    text_obj.tagmap = {}
                
                if category not in text_obj.tagmap:
                    text_obj.tagmap[category] = {}

                text_obj.tagmap[category][item] = newtext[1]
    
    def get_text(self, elems: t.Dict[str, t.Set[str]]) -> t.Generator[str]:
        for text_obj in self:
            if isinstance(text_obj, str):
                yield text_obj
            
            else:
                ret = text_obj.get_text(elems)
                if ret:
                    yield ret

def empty_string_yielder():
    yield ""

class RulesObj(BaseModel):
    name: str
    full_name: str
    
    text: t.Optional[TextList] = None
    
    article_redirect: t.Optional[str] = None
    url_prefix: t.ClassVar[t.Optional[str]] = None

    upsides: t.Optional[TextList] = None
    downsides: t.Optional[TextList] = None

    recommended: t.Optional[Required] = None

    required: t.Optional[Required] = None

    def __hash__(self):
        return hash(self.name)
    
    def get_article(self) -> str:
        try:
            return ROOT_DIR + self.url_prefix + self.article_redirect if self.article_redirect else ROOT_DIR + self.url_prefix + self.name
        
        except:
            raise NotImplementedError
        
    def get_upside_downside(self, elems: t.Dict[str, t.Set[str]]) -> t.Iterable[t.Tuple[str, str]]:
        upside = self.upsides.get_text(elems) if self.upsides else []
        downside = self.downsides.get_text(elems) if self.downsides else []
        
        return it.zip_longest(upside, downside, fillvalue = "")
        

        
    @property
    def title(self):
        return gen_title(self.full_name)

    def add_tags(self, replacements: t.Dict[str, t.Dict[str, t.Dict[str, t.List[t.Tuple[str, str]]]]]):
        # looks like ["classes"]["ranger"]["text"] = TaggedText(tag = "attribute", text = "...")
        
        # reqs: {"classes": {"fighter"}, "styles": {"thf", "reach"}}

        for category, idict in replacements.items():
            # i = "classes", "styles"
            for item, iidict in idict.items():
                # ii = "rogue", "ranger"
                print(iidict)
                for attr, taglist in iidict.items():
                    # iii = "text", "upsides" 
                    textlist: TextList = getattr(self, attr)
                    

                    for tag_amendment in taglist:
                        textlist.set_up_tagmap(category, item, tag_amendment)
                    # inside 'items' we replace all text with tag 'x' with equivalent text from taglist

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
    url_prefix: t.ClassVar[t.Optional[str]] = "styles/"

    def __repr__(self):
        return "Style(" + ", ".join((self.name, str(self.replacements), str(self.required))) + ")"

class Replacement(BaseModel):
    condition: str
    replace_dict: t.Dict[str, t.Any]

class Class(RulesObj):
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
    def full_line(self):
        if self.subfeats:
            return " -> ".join((feat.title for feat in self.subfeats))
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
        return self.title
    
    def __hash__(self):
        return hash(self.name)
    
    def is_provided(self, provideddict: t.Dict[str, t.Set[str]]):
        return self.name in provideddict.feats
    
    @property
    def title(self):
        return gen_title(self.name)


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
    
    def in_list(self, list):
        return any(elem in list for elem in self.elements)
    
    def __getitem__(self, idx):
        return self.elements[idx]

@dataclass
class OmniMap:
    styles: t.Dict[str, Style]
    classes: t.Dict[str, Class]
    feats: t.Dict[str, Feat]

# def amend_toml_subelems(style: str | dict):
#     if not isinstance(style, dict):
#         return style
    
#     return {k: amend_toml_subelems(v) for k, v in style.items()}

def parse_toml_elem(base_name: str, style: dict, cls: RulesObj) -> RulesObj:
    if "full_name" not in style:
        style["full_name"] = gen_title(base_name)  

    style["name"] = base_name

    for val in ("text", "upsides", "downsides"):
        if val in style:
            style[val] = TextList(text_list = [elem if isinstance(elem, str) else TaggedText(tag=elem[0], text=elem[1]) for elem in style[val]])
    
    ret = cls.model_validate(style)

    if "replacements" in style:
        ret.add_tags(style["replacements"])
    
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

with open("misc_rules_objs.toml", "r") as f:
    toml = tloads(f.read())
    dictdict = {base_name: {subname: parse_toml_elem(subname, subcls, RulesObj) for subname, subcls in cls.items()} for base_name, cls in toml.items()}

omnimap = OmniMap(styles=style_dict, classes = class_dict, feats = feat_dict)