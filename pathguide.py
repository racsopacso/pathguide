from __future__ import annotations

from pydantic import BaseModel
import typing as t
import itertools as it
from functools import cached_property

from config import ROOT_DIR

from tomli import loads as tloads

from dataclasses import dataclass

"""
Object types: 
 - Classes, Styles, Feats, RulesConcepts, SubObject

   Classes and Styles exist at the top level. They are never pointed to, they only point.

   Feats may have Feats as prerequisites.

   RulesConcepts may list Feats and RulesConcepts that are sources for them, and Feats that are recommended when you have them. 

   dex_to_damage is sourced from a list of feats

   those list of feats all provide dex to damage

   to avoid loops, either travel strictly down the tree, or strictly up the tree

   it's okay to go to dex to damage, compare the feats you have to the feats it's sourced from

   it's also okay to go to Slashing Grace, see it provides dex_to_damage, then recommend the things recommended by dex to damage

   but if you ask what dex_to_damage is sourced from, then what those things provide... 

   loop!
"""

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
    
    type: t.ClassVar[t.Optional[str]] = None

    upsides: t.Optional[TextList] = None
    downsides: t.Optional[TextList] = None

    recommended: t.Optional[LinkCollection] = None

    required: t.Optional[LinkCollection] = None

    provides: t.Optional[LinkCollection] = None

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
    
    @classmethod
    def parse_toml(cls, base_name: str, input_dict: dict):
        if "full_name" not in input_dict:
            input_dict["full_name"] = gen_title(base_name)  

        input_dict["name"] = base_name

        for field_name, field_obj in cls.model_fields.items():
            if field_obj.annotation == t.Optional[TextList]:
                if field_name in input_dict:
                    input_dict[field_name] = TextList(text_list = [elem if isinstance(elem, str) else TaggedText(tag=elem[0], text=elem[1]) for elem in input_dict[field_name]])

            if field_obj.annotation == t.Optional[LinkCollection]:
                if field_name in input_dict:
                    linklist = []

                    for key in input_dict[field_name]:
                        link_cls = FeatObjLink if key == "feats" else ObjLink
                        linklist += [link_cls(obj=obj, type=key) for obj in input_dict[field_name][key]]

                    input_dict[field_name] = LinkCollection(links = linklist)

        ret = cls.model_validate(input_dict)
    
        if "replacements" in input_dict:
            ret.add_tags(input_dict["replacements"])
        
        return ret
        
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
                for attr, taglist in iidict.items():
                    # iii = "text", "upsides" 
                    textlist: TextList = getattr(self, attr)

                    for tag_amendment in taglist:
                        textlist.set_up_tagmap(category, item, tag_amendment)
                    # inside 'items' we replace all text with tag 'x' with equivalent text from taglist

def parse_feat_elem(feat_elem: str | t.List[str]):
    if isinstance(feat_elem, str):
        ret = omnidict["feats"].get(feat_elem, NonDBFeat(name=feat_elem))

        if isinstance(ret, NonDBFeat):
            yield ret
        
        else:
            if ret.subfeats:
                yield from (feat for subfeat in ret.subfeats for feat in parse_feat_elem(subfeat))
            else:
                yield ret

    else:
        yield FeatUnion(name = feat_elem[0], elements = [res_elem for elem in feat_elem[1:] for res_elem in parse_feat_elem(elem)])


class FeatObjLink(BaseModel):
    obj: str | t.List[str]
    type: str

    @cached_property
    def objs(self) -> t.Tuple[Feat | FeatUnion | NonDBFeat, ...]:
        return tuple(parse_feat_elem(self.obj))
    
class ObjLink(BaseModel):
    obj: str | t.List[str]
    type: str

    @cached_property
    def objs(self) -> t.Tuple[Feat | FeatUnion | NonDBFeat]:
        return (omnidict[self.type][self.obj],)

class LinkCollection(BaseModel):
    links: t.List[ObjLink | FeatObjLink]

    def __iter__(self):
        return iter(self.objs)

    @cached_property
    def objs(self) -> t.Set[RulesObj]:
        ret = set(it.chain(*(link.objs for link in self.links)))
        return ret

    @cached_property
    def feats(self) -> t.Set[Feat | NonDBFeat | FeatUnion]:
        return {val for val in self.objs if type(val) in (Feat, NonDBFeat, FeatUnion)}
    
    @cached_property
    def concepts(self) -> t.Set[RulesConcept]:
        return {val for val in self.objs if isinstance(val, RulesConcept)}

class Style(RulesObj):
    url_prefix: t.ClassVar[t.Optional[str]] = "styles/"
    type: t.ClassVar[t.Optional[str]] = "styles"

class Attribute(RulesObj):
    url_prefix: t.ClassVar[t.Optional[str]] = "attributes/"
    type: t.ClassVar[t.Optional[str]] = "attributes"

class RulesConcept(RulesObj):
    url_prefix: t.ClassVar[t.Optional[str]] = "rules_concepts/"
    type: t.ClassVar[t.Optional[str]] = "rules_concepts"
    
    
    sources: t.Optional[LinkCollection] = None

    def is_provided(self, providedlist):
        return self in providedlist or any(source in providedlist for source in self.sources)

class Class(RulesObj):
    url_prefix: t.ClassVar[t.Optional[str]] = "classes/"
    type: t.ClassVar[t.Optional[str]] = "classes"

class Feat(RulesObj):
    subfeats: t.Optional[t.List[str]] = None
    prereqs: t.Optional[LinkCollection] = None
    url_prefix: t.ClassVar[t.Optional[str]] = "feats/"

    type: t.ClassVar[t.Optional[str]] = "feats"

    @property
    def full_line(self):
        if self.subfeats:
            return " -> ".join((feat.title for feat in self.subfeats))
        else:
            return self.full_name

    def is_provided(self, provideddict: t.Dict[str, t.Set[str]]):
        return self in provideddict

class NonDBFeat(BaseModel):
    name: str
    
    type: t.ClassVar[t.Optional[str]] = "nondbfeat"

    def get_article(self):
        return ""
    
    @cached_property
    def full_name(self):
        return self.title
    
    def __hash__(self):
        return hash(self.name)
    
    def is_provided(self, provideddict: t.Dict[str, t.Set[str]]):
        return self in provideddict
    
    @property
    def title(self):
        return gen_title(self.name)


class FeatUnion(BaseModel):
    name: str
    elements: t.List[Feat | NonDBFeat]
    
    type: t.ClassVar[t.Optional[str]] = "featunion"
    
    def __iter__(self):
        return iter(self.elements)
    
    def __hash__(self):
        return hash(self.name)
    
    def is_provided(self, provideddict: t.Dict[str, t.Set[str]]):
        return self in provideddict
    
    def in_list(self, list):
        return any(elem in list for elem in self.elements)
    
    def __getitem__(self, idx):
        return self.elements[idx]

@dataclass
class OmniMap:
    styles: t.Dict[str, Style]
    classes: t.Dict[str, Class]
    feats: t.Dict[str, Feat]
    attributes: t.Dict[str, RulesObj]
    rules_concepts: t.Dict[str, RulesConcept]

# def amend_toml_subelems(style: str | dict):
#     if not isinstance(style, dict):
#         return style
    
#     return {k: amend_toml_subelems(v) for k, v in style.items()}


with open("misc_rules_objs.toml", "r") as f:
    toml = tloads(f.read())
    omnidict = {base_name: {subname: RulesConcept.parse_toml(subname, subcls) for subname, subcls in cls.items()} for base_name, cls in toml.items()}

with open("feats.toml", "r") as f:
    toml = tloads(f.read())
    omnidict["feats"] = {base_name: Feat.parse_toml(base_name, feat) for base_name, feat in toml.items()}

with open("styles.toml", "r") as f:
    toml = tloads(f.read())
    omnidict["styles"] = {base_name: Style.parse_toml(base_name, style) for base_name, style in toml.items()}

with open("classes.toml", "r") as f:
    toml = tloads(f.read())
    omnidict["classes"] = {base_name: Class.parse_toml(base_name, cls) for base_name, cls in toml.items()}

with open("rules_concepts.toml", "r") as f:
    toml = tloads(f.read())
    omnidict["rules_concepts"] = {base_name: RulesConcept.parse_toml(base_name, style) for base_name, style in toml.items()}

omnimap = OmniMap(**omnidict)