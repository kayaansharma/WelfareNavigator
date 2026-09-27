"""Metadata-first candidate retrieval, sparse-vector RAG, and deterministic reranking."""
from __future__ import annotations
import math
from collections import Counter
from typing import Any, Callable
from urllib.parse import urlparse
from .taxonomy import CATEGORY_ALIASES, TAXONOMY, TARGET_FIELDS, detect_intent, extract_concepts, normalize

WEIGHTS={"target_match":40,"category_match":25,"concept_match":15,"location_match":10,"criteria_satisfied":10,"failed_required":-40,"target_mismatch":-25,"unknown_required":-15}
ROLE_CATEGORY={"STUDENT":"EDUCATION","FARMER":"AGRICULTURE","WIDOW":"SOCIAL_WELFARE","WOMAN_CHILD":"WOMEN_CHILD","SENIOR_CITIZEN":"SENIOR_CITIZEN","EMPLOYMENT":"EMPLOYMENT","DISABILITY":"DISABILITY","ENTREPRENEUR":"ENTREPRENEURSHIP","HEALTHCARE":"HEALTHCARE","HOUSING":"HOUSING"}
GENERIC={"government","benefit","benefits","support","assistance","financial","scheme","eligible","eligible","family","person","persons","state","india","central","the","and","for","with","under","from","through","criteria"}

def _rule_value(rule: dict[str, Any]) -> Any:
    return rule.get("value")

def _normalize_numeric_rule_value(value: Any) -> Any:
    """Coerce numeric strings in rule values while leaving categorical strings alone."""
    if isinstance(value, list):
        return [_normalize_numeric_rule_value(item) for item in value]
    if isinstance(value, str):
        candidate = value.strip()
        try:
            return int(candidate)
        except ValueError:
            try:
                return float(candidate)
            except ValueError:
                return value
    return value

def metadata_for(scheme: dict[str, Any]) -> dict[str, Any]:
    category=str(scheme.get("category","")).casefold()
    category_key=CATEGORY_ALIASES.get(category,"GENERAL_WELFARE")
    rules=scheme.get("rules",[])
    by_field={r.get("field"):r for r in rules}
    text=" ".join(str(scheme.get(k,"")) for k in ("name","description","benefits","eligibility_summary","eligibility_fields")).casefold()
    targets=set()
    if category_key=="EDUCATION" or (by_field.get("is_student") and by_field["is_student"].get("required",True)): targets.add("STUDENT")
    if category_key=="AGRICULTURE" or (by_field.get("is_farmer") and by_field["is_farmer"].get("required",True)) or ("farmer" in text and any(r.get("required",True) and r.get("field")=="occupation" for r in rules)): targets.add("FARMER")
    if "widow" in text or (by_field.get("marital_status") and "widow" in str(_rule_value(by_field["marital_status"])).casefold()): targets.add("WIDOW")
    age_value=_normalize_numeric_rule_value(by_field["age"].get("value",[0])) if "age" in by_field else [0]
    age_threshold=age_value[0] if isinstance(age_value,list) and age_value else age_value
    if category_key=="SENIOR_CITIZEN" or "old-age" in text or "senior citizen" in text or ("age" in by_field and by_field["age"].get("operator") in {">=","BETWEEN"} and isinstance(age_threshold,(int,float)) and age_threshold >= 60): targets.add("SENIOR_CITIZEN")
    if category_key=="WOMEN_CHILD" or any(r.get("field")=="gender" and str(r.get("value","")).casefold()=="female" and r.get("required",True) for r in rules): targets.add("WOMAN_CHILD")
    if category_key=="DISABILITY" or any(r.get("field") in {"disability","disability_status"} and r.get("required",True) for r in rules): targets.add("DISABILITY")
    if category_key=="ENTREPRENEURSHIP" or "entrepreneur" in text or "micro enterprise" in text: targets.add("ENTREPRENEUR")
    if category_key=="EMPLOYMENT" or any(r.get("field")=="employment_status" and r.get("required",True) for r in rules): targets.add("EMPLOYMENT")
    if category_key=="HEALTHCARE": targets.add("HEALTHCARE")
    if category_key=="HOUSING": targets.add("HOUSING")
    required=sorted({r["field"] for r in rules if r.get("required",True)})
    concepts=set(extract_concepts(text))
    concepts.update(targets)
    useful_terms=set(t for t in normalize(text) if t not in GENERIC and len(t)>2)
    for concept in concepts:
        useful_terms.update(t for term in TAXONOMY.get(concept,{}).get("terms",[]) for t in normalize(term))
    return {"category_key":category_key,"target_groups":sorted(targets),"required_profile_attributes":required,
            "exclusion_attributes":[],"keywords":sorted(useful_terms),"synonyms":sorted(concepts)}

def _sparse_vector(text: str) -> Counter[str]:
    return Counter(t for t in normalize(text) if t not in GENERIC and len(t)>1)

def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:return 0.0
    dot=sum(v*b.get(k,0) for k,v in a.items())
    return dot/(math.sqrt(sum(v*v for v in a.values()))*math.sqrt(sum(v*v for v in b.values())))

def build_chunks(schemes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks=[]
    for s in schemes:
        meta=metadata_for(s)
        doc_names=[d.get("name",str(d)) if isinstance(d,dict) else str(d) for d in s.get("documents",[])]
        parts=[
            ("overview"," ".join(str(s.get(k,"")) for k in ("name","benefits","description","eligibility_summary","eligibility_fields"))),
            ("eligibility"," ".join(r.get("description","") for r in s.get("rules",[]))),
            ("documents","Required or commonly requested documents: "+"; ".join(doc_names)),
            ("application",str(s.get("application_process","")))
        ]
        host=urlparse(s.get("source_url","")).netloc or "Source URL supplied in scheme CSV"
        for kind,content in parts:
            if not content.strip():continue
            chunks.append({"scheme_id":s["id"],"chunk_type":kind,"content":content,"source_url":s.get("source_url"),"source_name":host,"last_verified":s.get("last_verified"),"category":meta["category_key"],"target_groups":meta["target_groups"],"state":s.get("state"),"government_level":s.get("government"),"_vector":_sparse_vector(content)})
    return chunks

def profile_roles(profile: dict[str, Any]) -> set[str]:
    roles=set()
    for role,keys in TARGET_FIELDS.items():
        if role=="WIDOW":
            if profile.get("widow_status") is True or str(profile.get("marital_status","")).casefold()=="widowed":roles.add(role)
        elif role=="SENIOR_CITIZEN":
            if profile.get("senior_citizen_status") is True:
                roles.add(role)
            else:
                try:
                    if int(profile.get("age") or 0)>=60:roles.add(role)
                except (ValueError,TypeError):pass
        elif role=="WOMAN_CHILD":
            if str(profile.get("gender","")).casefold() in {"female","woman"} or profile.get("is_pregnant") is True:roles.add(role)
        elif role=="ENTREPRENEUR":
            if profile.get("entrepreneur_status") is True or str(profile.get("occupation","")).casefold() in {"entrepreneur","self-employed","small business owner"}:roles.add(role)
        elif role=="EMPLOYMENT":
            if profile.get("employment_status") is True or str(profile.get("employment_status","")).casefold() in {"unemployed","job-seeking","looking for work"}:roles.add(role)
        elif any(profile.get(k) is True for k in keys):roles.add(role)
    return roles

def _has_explicit_false(role: str, profile: dict[str, Any]) -> bool:
    keys=TARGET_FIELDS.get(role,())
    if role=="WIDOW":
        return profile.get("widow_status") is False or str(profile.get("marital_status","")).casefold() in {"single","married","divorced"}
    if role=="SENIOR_CITIZEN":
        return profile.get("senior_citizen_status") is False or (profile.get("age") is not None and int(profile["age"])<60)
    if role=="WOMAN_CHILD":
        return str(profile.get("gender","")).casefold() in {"male","man"}
    if role=="ENTREPRENEUR":
        return profile.get("entrepreneur_status") is False
    if role=="EMPLOYMENT":
        return str(profile.get("employment_status","")).casefold() in {"employed","working"}
    return any(profile.get(k) is False for k in keys)

def _state_match(scheme: dict[str, Any], profile: dict[str, Any]) -> bool:
    state=str(profile.get("state","")).casefold()
    sstate=str(scheme.get("state","")).casefold()
    return not state or sstate in {"all india","central","not specified"} or state==sstate

def retrieve_candidates(schemes: list[dict[str, Any]], profile: dict[str, Any], query: str,
                        chunks: list[dict[str, Any]], top_k: int=20) -> dict[str, Any]:
    intent=detect_intent(query,profile)
    roles=set(intent["roles"])|profile_roles(profile)
    categories={ROLE_CATEGORY[r] for r in roles if r in ROLE_CATEGORY}
    primary=intent["primary_category"]
    if primary!="GENERAL_WELFARE":categories.add(primary)
    categories.update(set(intent["secondary_categories"])-{"FINANCIAL_ASSISTANCE"})
    secondary=set(intent["secondary_categories"])
    # A secondary generic finance intent only broadens retrieval when no primary-role candidate exists.
    concepts=set(intent["concepts"])
    expanded=set(normalize(query))
    for concept in concepts:
        for term in TAXONOMY.get(concept,{}).get("terms",[]):expanded.update(normalize(term))
    if roles:
        expanded.update(roles)
    candidate=[]
    excluded=[]
    for s in schemes:
        meta=s.get("recommendation_metadata") or metadata_for(s)
        target=set(meta["target_groups"])
        matching_roles=target & roles
        explicit_category=meta["category_key"] in categories
        secondary_role=bool(target & roles)
        # Require a category or target-group connection; generic wording alone cannot select a scheme.
        if not (explicit_category or secondary_role):
            continue
        if not _state_match(s,profile):
            continue
        if target and roles and not matching_roles and meta["category_key"] not in categories:
            continue
        if target and any(_has_explicit_false(r,profile) for r in target):
            excluded.append(s["id"]);continue
        # A stated single role is a hard exclusion against schemes whose only target is another role.
        role_specific={"STUDENT","FARMER","WIDOW","WOMAN_CHILD","SENIOR_CITIZEN","DISABILITY","ENTREPRENEUR"}
        if roles and target & role_specific and not matching_roles:
            excluded.append(s["id"]);continue
        candidate.append((s,meta))
    rag_query=" ".join([query,*sorted(expanded),*sorted(roles)])
    query_vector=_sparse_vector(rag_query)
    rag_by_scheme: dict[str,list[dict[str,Any]]]={}
    candidate_ids={s["id"] for s,_ in candidate}
    for c in chunks:
        if c["scheme_id"] not in candidate_ids:continue
        score=_cosine(query_vector,c["_vector"])
        if score>0:rag_by_scheme.setdefault(c["scheme_id"],[]).append((score,c))
    for sid in rag_by_scheme:
        rag_by_scheme[sid].sort(key=lambda pair:pair[0],reverse=True)
    return {"intent":intent,"roles":sorted(roles),"candidate_ids":candidate_ids,"rag_by_scheme":rag_by_scheme,"excluded_ids":excluded,"candidate_count":len(candidate)}

def rank_recommendations(schemes: list[dict[str, Any]], profile: dict[str, Any], query: str,
                         chunks: list[dict[str, Any]], check_fn: Callable[[dict[str,Any],dict[str,Any]],dict[str,Any]],
                         limit: int=8) -> dict[str, Any]:
    retrieval=retrieve_candidates(schemes,profile,query,chunks)
    roles=set(retrieval["roles"]); known_roles=profile_roles(profile); intent=retrieval["intent"]
    categories={ROLE_CATEGORY[r] for r in roles if r in ROLE_CATEGORY}
    if intent["primary_category"]!="GENERAL_WELFARE":categories.add(intent["primary_category"])
    categories.update(set(intent["secondary_categories"])-{"FINANCIAL_ASSISTANCE"})
    concepts=set(intent["concepts"])
    ranked=[]
    scheme_map={s["id"]:s for s in schemes}
    for sid in retrieval["candidate_ids"]:
        s=scheme_map[sid]; meta=s.get("recommendation_metadata") or metadata_for(s); target=set(meta["target_groups"])
        role_hits=target&roles
        category_hit=meta["category_key"] in categories
        checks=check_fn(s,profile)
        failed=[c for c in checks["checks"] if c["status"]=="FAILED" and c.get("required",True)]
        unknown=[c for c in checks["checks"] if c["status"]=="UNKNOWN" and c.get("required",True)]
        if failed:
            retrieval["excluded_ids"].append(sid);continue
        score=WEIGHTS["target_match"] if role_hits else 0
        if category_hit:score+=WEIGHTS["category_match"]
        if set(meta["synonyms"])&concepts:score+=WEIGHTS["concept_match"]
        if _state_match(s,profile) and profile.get("state"):score+=WEIGHTS["location_match"]
        matched=[c for c in checks["checks"] if c["status"]=="MATCHED" and c.get("required",True)]
        unknown_targets=[r for r in role_hits if r not in known_roles and not _has_explicit_false(r,profile)]
        for role in unknown_targets:
            checks["checks"].append({"field":"target_group:"+role,"operator":"==","value":True,"description":"Confirm applicant is in target group "+role.replace("_"," ").title(),"required":True,"status":"UNKNOWN"})
            unknown.append(checks["checks"][-1])
        if unknown_targets:checks["status"]="NEEDS_MORE_INFORMATION"
        if matched:score+=WEIGHTS["criteria_satisfied"]
        score+=WEIGHTS["unknown_required"] if unknown else 0
        if score<25:continue
        rag_pairs=retrieval["rag_by_scheme"].get(sid,[])
        if rag_pairs and rag_pairs[0][0]>=0.08:score+=10
        evidence=[{k:v for k,v in chunk.items() if not k.startswith("_")} for _,chunk in rag_pairs[:2]]
        why=[]
        if category_hit:why.append(f'Category match: {meta["category_key"].replace("_"," ").title()}')
        if role_hits:why.append("Target group match: "+", ".join(sorted(role_hits)).replace("_"," ").title())
        if profile.get("state") and _state_match(s,profile):why.append("Location matches the profile")
        why.extend("Rule matched: "+c["description"] for c in matched[:3])
        result={**s,"scheme_id":s["id"],"recommendation_metadata":meta,"eligibility":checks,"status":checks["status"],
                "matched_criteria":[c["description"] for c in checks["checks"] if c["status"]=="MATCHED"],
                "unknown_criteria":[c["description"] for c in checks["checks"] if c["status"]=="UNKNOWN"],
                "failed_criteria":[c["description"] for c in checks["checks"] if c["status"]=="FAILED"],
                "why_relevant":why,"missing_documents":[d.get("name",str(d)) if isinstance(d,dict) else str(d) for d in s.get("documents",[])],
                "source":{"source_url":s.get("source_url"),"source_name":s.get("source_name"),"last_verified":s.get("last_verified")},
                "rag_evidence":evidence,"_score":score}
        ranked.append(result)
    ranked.sort(key=lambda s:(s["eligibility"]["status"]!="POTENTIAL_MATCH",-s["_score"],s["name"]))
    selected=ranked[:limit]
    for s in selected:s.pop("_score",None)
    return {"intent":intent,"roles":sorted(roles),"candidate_count":retrieval["candidate_count"],
            "excluded_count":len(set(retrieval["excluded_ids"])),"rag_available":bool(chunks),
            "recommendations":selected,"message":"No strong matches found. Share what kind of support you are looking for." if not selected else ""}

def rag_search(schemes: list[dict[str,Any]], profile: dict[str,Any], query: str, chunks: list[dict[str,Any]], limit:int=5) -> list[dict[str,Any]]:
    retrieval=retrieve_candidates(schemes,profile,query,chunks)
    pairs=[pair for rows in retrieval["rag_by_scheme"].values() for pair in rows]
    pairs.sort(key=lambda pair:pair[0],reverse=True)
    return [{"relevance":round(score,4),**{k:v for k,v in chunk.items() if not k.startswith("_")}} for score,chunk in pairs[:limit]]
