"""Controlled concept vocabulary and profile-aware intent detection."""
from __future__ import annotations
import re
from typing import Any

TAXONOMY: dict[str, dict[str, Any]] = {
    "STUDENT": {"category":"EDUCATION","terms":["student","college student","university student","undergraduate","postgraduate","scholarship","education","tuition","college fees","school fees","study","studies","higher education","विद्यार्थी","छात्र","छात्रा","पढ़ाई","padhai","college fees","fees"]},
    "FARMER": {"category":"AGRICULTURE","terms":["farmer","agriculture","cultivation","cultivator","agricultural worker","farmland","crop","kisan","farming","किसान","खेती","कृषि","kheti","fasal"]},
    "WIDOW": {"category":"SOCIAL_WELFARE","terms":["widow","widowed","husband deceased","widow pension","विधवा","vidhwa","pati guzar","maa widow"]},
    "WOMAN_CHILD": {"category":"WOMEN_CHILD","terms":["woman","women","girl","female","mother","daughter","pregnant","maternity","child benefit","महिला","औरत","गर्भवती"]},
    "SENIOR_CITIZEN": {"category":"SENIOR_CITIZEN","terms":["senior citizen","elderly","old age","retired","pension for elderly","वरिष्ठ नागरिक","बुजुर्ग","buzurg","pension","retirement"]},
    "EMPLOYMENT": {"category":"EMPLOYMENT","terms":["job","employment","unemployed","skill training","vocational training","job seeker","apprentice","रोजगार","नौकरी"]},
    "DISABILITY": {"category":"DISABILITY","terms":["disability","disabled","person with disability","divyang","दिव्यांग","विकलांग"]},
    "ENTREPRENEUR": {"category":"ENTREPRENEURSHIP","terms":["entrepreneur","business owner","self employed","startup","micro enterprise","उद्यमी","व्यवसाय"]},
    "HEALTHCARE": {"category":"HEALTHCARE","terms":["healthcare","health insurance","hospitalization","medical treatment","health support","स्वास्थ्य","इलाज"]},
    "HOUSING": {"category":"HOUSING","terms":["housing","house construction","home assistance","pucca house","आवास","घर"]},
    "PENSION": {"category":"SOCIAL_WELFARE","terms":["pension","pension information","vridha pension","वृद्धावस्था पेंशन","पेंशन"]},
    "FINANCIAL_ASSISTANCE": {"category":"FINANCIAL_ASSISTANCE","terms":["financial assistance","financial help","financial support","money for","income support","scholarship","grant","आर्थिक सहायता","वित्तीय सहायता","financial madad","madad","paise","paisa","arthik madad"]},
}

CATEGORY_ALIASES: dict[str, str] = {
    "education":"EDUCATION","agriculture":"AGRICULTURE","women & child":"WOMEN_CHILD","energy/women":"WOMEN_CHILD",
    "health":"HEALTHCARE","housing":"HOUSING","social security":"SOCIAL_WELFARE","pension":"SOCIAL_WELFARE",
    "artisans":"EMPLOYMENT","skills/employment":"EMPLOYMENT","employment/business":"EMPLOYMENT",
    "disability":"DISABILITY","insurance":"FINANCIAL_ASSISTANCE","financial inclusion":"FINANCIAL_ASSISTANCE",
    "business/finance":"ENTREPRENEURSHIP","labour/social security":"SOCIAL_WELFARE","street vendors":"EMPLOYMENT",
}
TARGET_FIELDS = {
    "STUDENT":("student_status","is_student"),"FARMER":("farmer_status","is_farmer"),
    "WIDOW":("widow_status","marital_status"),"SENIOR_CITIZEN":("senior_citizen_status","age"),
    "WOMAN_CHILD":("gender","is_pregnant"),"DISABILITY":("disability_status","disability"),
    "ENTREPRENEUR":("entrepreneur_status","occupation"),
    "EMPLOYMENT":("employment_status","occupation"),
}

def normalize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+|[\u0900-\u097f]+", text.casefold())

def detect_language(text: str) -> str:
    if re.search(r"[\u0900-\u097f]", text):
        return "Hindi"
    hinglish_markers={"main","mujhe","meri","mere","papa","maa","hain","hoon","chahiye","padhai","kheti","fasal","saal","liye","mein","rehta","rehti"}
    tokens=set(normalize(text))
    return "Hinglish" if len(tokens & hinglish_markers)>=2 else "English"

def extract_concepts(text: str) -> list[str]:
    tokens=normalize(text); padded=" "+" ".join(tokens)+" "
    found=[]
    for concept, data in TAXONOMY.items():
        for term in data["terms"]:
            phrase=" "+" ".join(normalize(term))+" "
            if phrase in padded:
                found.append(concept); break
    return found

def detect_intent(text: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile=profile or {}
    negative=explicit_negatives(text)
    concepts=[c for c in extract_concepts(text) if c not in negative]
    roles=[]
    def enabled(*keys: str) -> bool:
        return any(profile.get(k) is True for k in keys)
    if enabled("student_status","is_student") and "STUDENT" not in negative: roles.append("STUDENT")
    if enabled("farmer_status","is_farmer") and "FARMER" not in negative: roles.append("FARMER")
    if (enabled("widow_status") or str(profile.get("marital_status","")).casefold()=="widowed") and "WIDOW" not in negative: roles.append("WIDOW")
    if enabled("disability_status","disability") and "DISABILITY" not in negative: roles.append("DISABILITY")
    if (enabled("entrepreneur_status") or str(profile.get("occupation","")).casefold() in {"entrepreneur","self-employed","small business owner"}) and "ENTREPRENEUR" not in negative: roles.append("ENTREPRENEUR")
    if enabled("is_pregnant"): roles.append("WOMAN_CHILD")
    try:
        if int(profile.get("age") or 0)>=60: roles.append("SENIOR_CITIZEN")
    except (ValueError,TypeError): pass
    # Explicit role terms in the query are useful even before a profile turn is saved.
    for role in concepts:
        if role in {"FINANCIAL_ASSISTANCE", "PENSION"}:
            continue
        if role not in roles: roles.append(role)
    category_intents=[]
    for role in roles:
        cat=TAXONOMY.get(role,{}).get("category")
        if cat and cat not in category_intents: category_intents.append(cat)
    if not category_intents:
        category_intents=[TAXONOMY[c]["category"] for c in concepts if c in TAXONOMY and TAXONOMY[c]["category"] not in category_intents]
    primary=category_intents[0] if category_intents else "GENERAL_WELFARE"
    secondary=[c for c in category_intents[1:] if c!=primary]
    for concept in concepts:
        concept_category=TAXONOMY.get(concept,{}).get("category")
        if concept_category and concept_category!=primary and concept_category not in secondary:
            secondary.append(concept_category)
    if "FINANCIAL_ASSISTANCE" in [TAXONOMY[c]["category"] for c in concepts if c in TAXONOMY] and primary!="FINANCIAL_ASSISTANCE":
        secondary.append("FINANCIAL_ASSISTANCE")
    if "WIDOW" in roles and "WOMEN_CHILD" not in category_intents: secondary.append("WOMEN_CHILD")
    if "SENIOR_CITIZEN" in roles and "HEALTHCARE" not in category_intents: secondary.append("HEALTHCARE")
    return {"primary_category":primary,"secondary_categories":list(dict.fromkeys(secondary)),"roles":list(dict.fromkeys(roles)),"concepts":list(dict.fromkeys(concepts))}

def explicit_negatives(text: str) -> set[str]:
    tokens=normalize(text); joined=" ".join(tokens); negatives=set()
    forms={"STUDENT":["student","students","विद्यार्थी","छात्र"],"FARMER":["farmer","farmers","किसान"],"WIDOW":["widow","widowed","विधवा"],"DISABILITY":["disabled","disability","दिव्यांग"],"ENTREPRENEUR":["entrepreneur","उद्यमी"]}
    for role, terms in forms.items():
        for term in terms:
            t=" ".join(normalize(term))
            if re.search(r"(?:not|no longer|never|नहीं)\s+(?:a\s+)?"+re.escape(t)+r"\b",joined):
                negatives.add(role)
                break
    return negatives
