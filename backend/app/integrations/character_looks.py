"""Structured "look" profiles for character portraits.

The extractor returns a small profile per character instead of free text:

    {"type": "human", "sex": "man", "age": "middle-aged", "build": "tall",
     "hair": "long brown", "eyes": "grey", "facial_hair": "grey beard",
     "clothing": "cloak and furs", "distinctive": "...", "culture": "..."}

`build_subject` always turns that into a phrase with a real subject noun
("a tall middle-aged man with long brown hair...", "a large white
direwolf"), so the image model never has to guess who it is drawing -- the
cause of Jaime/Robb/Ghost being drawn as women and Catelyn as a man.

It also cleans details that image models take literally:
* "dwarf" -> "adult man with dwarfism and an adult face" (not a toddler)
* comparisons to other named characters ("taller than Jon Snow") -> "tall"
* horse / riding details ("riding a pony", "a shaggy garron") are dropped.

Nothing here imports other app modules, so both the extractor and the
portrait code can use it without import cycles.
"""
from __future__ import annotations

import re
import unicodedata

LOOK_FIELDS = (
    "type", "species", "sex", "age", "build", "hair", "eyes", "skin",
    "facial_hair", "clothing", "distinctive", "culture",
)
_FIELD_MAX_CHARS = 90

# The extractor sometimes writes a non-answer instead of "" -- those must
# never be painted ("Photorealistic portrait photograph of not described directly").
_NON_ANSWER = re.compile(
    r"^\s*(?:n/?a|none|null|nil|unknown|unspecified|not\s+applicable|-+|\.+|"
    r"(?:no|not)\s+(?:physical\s+|visual\s+)?(?:description|details?|info(?:rmation)?)(?:\s+(?:given|provided|available))?|"
    r"(?:appearance\s+)?(?:is\s+)?not\s+(?:directly\s+|explicitly\s+|physically\s+|clearly\s+)?"
    r"(?:described|mentioned|specified|stated|given|provided|known|detailed)\b.*)"
    r"\s*[.!]?\s*$",
    re.IGNORECASE,
)

_SEX_WORDS = {
    "man": "man", "male": "man", "he": "man", "m": "man", "adult man": "man",
    "woman": "woman", "female": "woman", "she": "woman", "f": "woman", "lady": "woman", "adult woman": "woman",
    "boy": "boy", "girl": "girl",
}
# Titles and family words that settle a character's sex when the extractor
# didn't ("Ser Boros", "Septa Mordane", "Lady Arryn", "Old Nan" stays unknown).
# ---- titles: the ONE shared list (portraits.py and the Flutter initials
# helper use it too). Genre-neutral: everyday, professional, military,
# religious, noble and foreign honorifics, plus a few common fantasy ones.
# Lower-case; a title never identifies anyone, so it's never scrubbed from
# prompts, and a gendered one settles a character's sex when the text model
# didn't. Keep frontend/lib/models/character_map_item.dart in sync.
FEMALE_TITLES = frozenset({
    # everyday / foreign
    "mrs", "miss", "ms", "madam", "madame", "mademoiselle", "mme", "mlle", "mistress", "dame",
    "senora", "senorita", "signora", "frau", "fraulein",
    # nobility / royalty
    "lady", "queen", "princess", "duchess", "countess", "baroness", "marchioness", "viscountess",
    "empress", "khaleesi",
    # religious
    "sister", "abbess", "nun", "priestess", "septa",
    # family / roles used as titles
    "mother", "aunt", "auntie", "grandmother", "granny", "grandma", "nana", "wife", "daughter", "maid",
})
MALE_TITLES = frozenset({
    # everyday / foreign
    "mr", "mister", "master", "monsieur", "senor", "signor", "herr",
    # nobility / royalty / knighthood
    "sir", "ser", "lord", "king", "prince", "duke", "count", "earl", "baron", "marquis", "marquess",
    "viscount", "emperor", "khal", "magister",
    # religious / scholarly orders that are men-only in their stories
    "father", "brother", "friar", "monk", "abbot", "septon", "maester",
    # family / roles used as titles
    "uncle", "grandfather", "grandpa", "husband", "son",
})
# No sex implied: professional, military, official, academic, religious.
NEUTRAL_TITLES = frozenset({
    "dr", "doctor", "professor", "prof", "headmaster", "headmistress", "teacher", "nurse",
    "captain", "capt", "commander", "general", "colonel", "major", "lieutenant", "lt", "sergeant", "sgt",
    "corporal", "private", "admiral", "officer", "constable", "inspector", "detective", "agent",
    "judge", "justice", "mayor", "governor", "president", "minister", "chancellor", "senator", "ambassador",
    "chief", "elder", "reverend", "rev", "pastor", "vicar", "bishop", "cardinal", "pope", "rabbi", "imam",
    "priest", "deacon", "knight", "squire", "saint", "st",
})
# Deliberately NOT titles: "wizard", "witch" and similar are nouns that also
# appear in book titles ("The Wizard of Oz") and must stay scrubbable.
ALL_TITLES = FEMALE_TITLES | MALE_TITLES | NEUTRAL_TITLES
# Backwards-compatible private names used below.
_FEMALE_TITLES = FEMALE_TITLES
_MALE_TITLES = MALE_TITLES

_HORSE = re.compile(
    r"\b(horses?|pon(?:y|ies)|garrons?|mounts?|steeds?|mares?|stallions?|geldings?|saddles?|"
    r"rid(?:es|ing)|rode|astride|on horseback)\b",
    re.IGNORECASE,
)
_HORSE_PHRASE = re.compile(
    r"\s*\b(?:with|on|and|riding|astride)\s+(?:(?:a|an|the|his|her|their)\s+)?(?:[\w\-]+\s+){0,3}?"
    r"(?:horses?|pon(?:y|ies)|garrons?|mounts?|steeds?|mares?|stallions?|geldings?)\b",
    re.IGNORECASE,
)
_COMPARATIVE_BASE = {
    "taller": "tall", "shorter": "short", "bigger": "big", "smaller": "small", "larger": "large",
    "older": "older", "younger": "young", "thinner": "thin", "fatter": "heavyset", "heavier": "heavyset",
    "stronger": "strong", "broader": "broad", "leaner": "lean", "stouter": "stout",
}
# "taller than Jon Snow", "taller than his brother" -> "tall"
_COMPARISON = re.compile(
    r"\b(\w+er)\s+than\s+(?:(?:his|her|their|the)\s+\w+|[A-Z][\w'\-]*(?:\s+[A-Z][\w'\-]*)*)",
)
# "like his father", "as tall as Robb", "half his brother's height"
_LIKE_NAME = re.compile(r"\b(?:just\s+)?like\s+(?:his|her|their)?\s*[A-Z][\w'\-]*(?:\s+[A-Z][\w'\-]*)*")
_AS_AS = re.compile(r"\bas\s+(\w+)\s+as\s+(?:(?:his|her|their)\s+\w+|[A-Z][\w'\-]*(?:\s+[A-Z][\w'\-]*)*)")
_HALF_HEIGHT = re.compile(r"\bhalf\s+(?:his|her|their|the)\s+[\w']+\s+height\b", re.IGNORECASE)
_DWARF = re.compile(r"\b(?:a\s+)?dwarf(?:ish)?\b", re.IGNORECASE)
_YEARS_OLD = re.compile(r"\b(\d+|[a-z]+(?:-[a-z]+)?)[\s-]+years?[\s-]+old\b", re.IGNORECASE)
_CHILD_AGE = re.compile(r"\b(child|infant|baby|toddler|kid|young boy|young girl|[1-9]-year-old|1[0-2]-year-old|"
                        r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)-year-old)\b",
                        re.IGNORECASE)


def meaningful_appearance(value: object) -> str | None:
    """The text, or None if it's empty or a non-answer such as
    "not described directly", "unknown" or "N/A"."""
    text = str(value).strip() if value is not None else ""
    if not text or _NON_ANSWER.match(text):
        return None
    return text


def clean_setting(value: object, max_chars: int = 160) -> str | None:
    text = meaningful_appearance(value)
    return text[:max_chars].strip() if text else None


def _clean_value(value: object) -> str | None:
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value if isinstance(v, (str, int, float)))
    if not isinstance(value, (str, int, float)):
        return None
    return meaningful_appearance(str(value)[:_FIELD_MAX_CHARS].strip(" ,;."))


def normalize_look(raw: object) -> dict | None:
    """A clean profile with only known fields and real values, or None."""
    if not isinstance(raw, dict):
        return None
    look: dict[str, str] = {}
    for key in LOOK_FIELDS:
        value = _clean_value(raw.get(key))
        if value:
            look[key] = value
    sex = look.get("sex")
    if sex is not None:
        normalized = _SEX_WORDS.get(sex.casefold())
        if normalized:
            look["sex"] = normalized
        else:
            look.pop("sex")
    kind = (look.get("type") or "").casefold()
    if kind not in {"human", "animal"}:
        species = (look.get("species") or "").casefold()
        kind = "animal" if species and species not in {"human", "person", "man", "woman"} else "human"
    look["type"] = kind
    if kind == "human":
        look.pop("species", None)
    return look if len(look) > 1 else None  # {"type": ...} alone says nothing


def merge_looks(primary: dict | None, fallback: dict | None) -> dict | None:
    """Field by field: `primary` wins, `fallback` fills the gaps."""
    if not primary:
        return dict(fallback) if fallback else None
    merged = dict(fallback or {})
    merged.update({k: v for k, v in primary.items() if v})
    return merged


def _ascii(text: str) -> str:
    """ "Señora" -> "Senora", so accented titles match the list."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def sex_from_name(name: str | None) -> str | None:
    words = {w.casefold().strip(".") for w in re.findall(r"[A-Za-z.]+", _ascii(name or ""))}
    if words & _FEMALE_TITLES:
        return "woman"
    if words & _MALE_TITLES:
        return "man"
    return None


def clean_detail(text: str) -> str:
    """Drops horse/riding clauses and comparisons to other characters."""
    text = _HALF_HEIGHT.sub("very short", text)
    text = _COMPARISON.sub(lambda m: _COMPARATIVE_BASE.get(m.group(1).casefold(), ""), text)
    text = _AS_AS.sub(lambda m: m.group(1), text)
    text = _LIKE_NAME.sub("", text)
    # First cut horse phrases out of a clause ("a young man with a shaggy
    # garron" -> "a young man"), then drop clauses that are still about horses.
    text = _HORSE_PHRASE.sub("", text)
    parts = [p.strip() for p in re.split(r"[,;]", text)]
    parts = [p for p in parts if p and not _HORSE.search(p)]
    return re.sub(r"\s{2,}", " ", ", ".join(parts)).strip(" ,;.")


def _article(phrase: str) -> str:
    return "an" if phrase[:1].casefold() in "aeiou" else "a"


def _with_noun(value: str, noun: str) -> str:
    return value if noun in value.casefold() else f"{value} {noun}"


def render_look(look: dict | None) -> str | None:
    """Short human-readable summary (stored as the node's `appearance`)."""
    if not look:
        return None
    subject = build_subject(look, None, None)
    return None if subject == FALLBACK_SUBJECT else subject


FALLBACK_SUBJECT = "an ordinary adult person"


_HUMAN_NOUN = re.compile(
    r"\b(man|woman|boy|girl|person|child|lady|lord|knight|youth|baby|infant|elder|maiden|lad|lass)\b",
    re.IGNORECASE,
)
_NUMBER_AGE = re.compile(
    r"^(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty)$",
    re.IGNORECASE,
)


def _clean_fields(look: dict) -> tuple[dict[str, str], bool]:
    """Cleaned detail fields (no type/sex) and whether dwarfism was mentioned."""
    fields = {k: clean_detail(v) for k, v in look.items() if isinstance(v, str) and k not in {"type", "sex"}}
    dwarf = any(_DWARF.search(v) for v in fields.values())
    fields = {k: re.sub(r"\s{2,}", " ", _DWARF.sub("", v)).strip(" ,;") for k, v in fields.items()}
    return {k: v for k, v in fields.items() if v}, dwarf


def _animal_subject(fields: dict[str, str]) -> str:
    species = fields.pop("species", "animal")
    head = " ".join(x for x in (fields.pop("build", ""), fields.pop("age", ""), species) if x)
    parts = [f"{_article(head)} {head}"]
    if fields.get("hair"):
        parts[0] += f" with {_with_noun(fields.pop('hair'), 'fur')}"
    if fields.get("eyes"):
        parts.append(_with_noun(fields.pop("eyes"), "eyes"))
    if fields.get("distinctive"):
        parts.append(fields["distinctive"])
    return ", ".join(parts)


def _human_head(fields: dict[str, str], sex: str | None, dwarf: bool) -> str:
    """ "a tall seven-year-old boy", "an adult man with dwarfism...", "a man in his thirties"."""
    age = _YEARS_OLD.sub(lambda m: f"{m.group(1)}-year-old", fields.pop("age", ""))
    if _NUMBER_AGE.match(age):
        age = f"{age}-year-old"
    if sex in {"man", "woman"} and _CHILD_AGE.search(age):
        sex = "boy" if sex == "man" else "girl"
    noun = sex if sex in {"man", "woman", "boy", "girl"} else "person"
    if dwarf:
        noun = f"adult {noun if noun in {'man', 'woman'} else 'man'} with dwarfism and an adult face"
        age = "" if _CHILD_AGE.search(age) else age
    suffix = ""
    if age.casefold().startswith(("in ", "about ", "around ", "aged ")):
        suffix, age = f" {age}", ""
    head = " ".join(x for x in (fields.pop("build", ""), age, noun) if x)
    return f"{_article(head)} {head}{suffix}"


def _human_details(fields: dict[str, str]) -> list[str]:
    features = [_with_noun(fields.pop(k), n) for k, n in (("hair", "hair"), ("eyes", "eyes")) if fields.get(k)]
    if fields.get("facial_hair"):
        features.append(fields.pop("facial_hair"))
    parts = ["with " + ", ".join(features)] if features else []
    if fields.get("skin"):
        parts.append(_with_noun(fields.pop("skin"), "skin"))
    if fields.get("distinctive"):
        parts.append(fields.pop("distinctive"))
    if fields.get("clothing"):
        clothing = fields.pop("clothing")
        parts.append(clothing if clothing.casefold().startswith(("wearing", "dressed", "in ")) else f"wearing {clothing}")
    if fields.get("culture"):
        parts.append(fields.pop("culture"))
    return parts


def _free_text(appearance: str | None, dwarf: bool) -> str | None:
    text = meaningful_appearance(clean_detail(appearance or ""))
    if text and (dwarf or _DWARF.search(text)):
        text = _DWARF.sub("adult man with dwarfism and an adult face", text)
    return text


def build_subject(look: dict | None, appearance: str | None, name: str | None) -> str:
    """The portrait's subject phrase -- always with a subject noun when the
    profile, a title in the name, or the free-text appearance gives one."""
    look = dict(look or {})
    if not look.get("sex"):
        look["sex"] = sex_from_name(name)
    fields, dwarf = _clean_fields(look)
    if look.get("type") == "animal":
        return _animal_subject(fields)[:400]

    head = _human_head(fields, look.get("sex"), dwarf)
    details = _human_details(fields)
    free = _free_text(appearance, dwarf)
    knows_nothing = head == "a person"  # no sex, age, build or dwarfism
    if not details and free:
        # Only sex/age known (or nothing): the free-text appearance carries the
        # detail. Keep its own subject ("a bony woman ...") or put ours in front.
        if knows_nothing or _HUMAN_NOUN.search(free):
            return free[:400]
        return f"{head}, {free}"[:400]
    if not details and knows_nothing:
        return FALLBACK_SUBJECT
    subject = head
    # "a tall man with golden hair" -- but not a second "with" after
    # "...with dwarfism and an adult face".
    if details and details[0].startswith("with ") and " with " not in head:
        subject += " " + details.pop(0)
    return ", ".join([subject, *details])[:400]


# ---- which characters get a portrait (D14) --------------------------------

# Fields that make a face distinguishable. Sex alone ("a man") does not.
DETAIL_FIELDS = ("age", "build", "hair", "eyes", "skin", "facial_hair", "clothing", "distinctive", "species")
_MAIN_ROLES = re.compile(
    r"\b(protagonist|antagonist|deuteragonist|main|major|lead|hero|heroine|villain|narrator)\b", re.IGNORECASE
)
_DETAIL_SPLIT = re.compile(r",|;|\bwith\b|\band\b|\bwearing\b", re.IGNORECASE)


def detail_count(look: dict | None, appearance: str | None = None) -> int:
    """How many concrete visual details are known: profile fields, or the
    pieces of a free-text appearance when there is no profile."""
    count = sum(1 for f in DETAIL_FIELDS if meaningful_appearance((look or {}).get(f)))
    if count == 0:
        text = meaningful_appearance(appearance)
        if text:
            count = sum(1 for part in _DETAIL_SPLIT.split(text) if len(part.strip()) > 2)
    return count


def is_main_role(role: str | None) -> bool:
    return bool(role and _MAIN_ROLES.search(role))


# ---- the same person under two names (D15) --------------------------------

_TITLE_WORDS = ALL_TITLES | {"old", "young", "little", "big", "the", "of"}
_NAME_WORD = re.compile(r"[a-z0-9]+")


def title_free_words(name: str) -> frozenset[str]:
    """Name words without titles: "Magister Illyrio" -> {"illyrio"}."""
    words = _NAME_WORD.findall(_ascii(name or "").casefold().replace("'s", ""))
    return frozenset(w for w in words if w not in _TITLE_WORDS)


def _sex_of(name: str, look: dict | None) -> str | None:
    sex = (look or {}).get("sex")
    if sex in {"man", "boy"}:
        return "man"
    if sex in {"woman", "girl"}:
        return "woman"
    return sex_from_name(name)


def titled_variant(name_a: str, look_a: dict | None, name_b: str, look_b: dict | None) -> bool:
    """True when two names could be one person once titles are ignored:
    "Magister Illyrio" ~ "Illyrio Mopatis", "Lady Arryn" ~ "Lysa Arryn".
    Needs a title on at least one side (plain name variants are handled
    elsewhere) and never pairs a man with a woman ("Mr. Dursley" vs
    "Mrs. Dursley"). Callers must still require exactly one candidate."""
    a, b = title_free_words(name_a), title_free_words(name_b)
    if not a or not b or not (a <= b or b <= a):
        return False
    if title_free_words(name_a) == frozenset(_NAME_WORD.findall(name_a.casefold())) and \
            title_free_words(name_b) == frozenset(_NAME_WORD.findall(name_b.casefold())):
        return False  # no titles anywhere: not this rule's job
    sex_a, sex_b = _sex_of(name_a, look_a), _sex_of(name_b, look_b)
    return not (sex_a and sex_b and sex_a != sex_b)
