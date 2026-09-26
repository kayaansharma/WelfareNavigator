from __future__ import annotations
import re
import csv
import json
import os
from io import BytesIO
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse
from typing import Any
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .taxonomy import detect_intent, detect_language, explicit_negatives
from .recommendations import build_chunks, metadata_for, rag_search, rank_recommendations, retrieve_candidates

SCHEMES: list[dict[str, Any]] = [
 {"id":"edu-demo","name":"Student Support Grant (Demo)","category":"Education","government":"Synthetic demo dataset","ministry":"Demo only","state":"Uttar Pradesh","benefits":"Illustrative education assistance; no real benefit is offered.","description":"Synthetic example used to demonstrate profile matching and application preparation.","eligibility_summary":"Synthetic demo criteria only. Not an official government scheme.","application_process":"Find current education services through official government resources. This demo does not submit applications.","application_url":"https://www.india.gov.in/","source_url":"https://www.india.gov.in/","source_name":"India.gov.in general directory; rules are synthetic","last_verified":"2026-09-26","active":True,"documents":["Aadhaar","Income Certificate","Domicile Certificate","Student Certificate"],"rules":[{"field":"age","operator":"<=","value":30,"description":"Age 30 or below (synthetic demo rule)"},{"field":"annual_income","operator":"<=","value":250000,"description":"Annual family income ₹2.5 lakh or below (synthetic demo rule)"},{"field":"state","operator":"IN","value":["Uttar Pradesh"],"description":"Resident of Uttar Pradesh (synthetic demo rule)"},{"field":"student_status","operator":"==","value":True,"description":"Currently studying (synthetic demo rule)"},{"field":"institution_type","operator":"IN","value":["government","government-aided"],"description":"Government or aided institution (synthetic demo rule)"}]},
 {"id":"farm-demo","name":"Small Farmer Support (Demo)","category":"Agriculture","government":"Synthetic demo dataset","ministry":"Demo only","state":"All India","benefits":"Illustrative farm-input assistance; no real benefit is offered.","description":"Synthetic example to test farmer profile questions.","eligibility_summary":"Synthetic demo criteria only. Not an official government scheme.","application_process":"Check services with your state agriculture department.","application_url":"https://www.india.gov.in/","source_url":"https://www.india.gov.in/","source_name":"India.gov.in general directory; rules are synthetic","last_verified":"2026-09-26","active":True,"documents":["Aadhaar","Land Record","Bank Document"],"rules":[{"field":"farmer_status","operator":"==","value":True,"description":"Identifies as a farmer (synthetic demo rule)"},{"field":"land_ownership","operator":"==","value":True,"description":"Owns or cultivates land (synthetic demo rule)"}]},
 {"id":"enterprise-demo","name":"Women Entrepreneur Starter Support (Demo)","category":"Entrepreneurship","government":"Synthetic demo dataset","ministry":"Demo only","state":"All India","benefits":"Illustrative startup support; no real benefit is offered.","description":"Synthetic example; verify real services with official sources.","eligibility_summary":"Synthetic demo criteria only. Not an official government scheme.","application_process":"Explore official enterprise resources.","application_url":"https://www.india.gov.in/","source_url":"https://www.india.gov.in/","source_name":"India.gov.in general directory; rules are synthetic","last_verified":"2026-09-26","active":True,"documents":["Aadhaar","Bank Document"],"rules":[{"field":"gender","operator":"IN","value":["woman","female"],"description":"Woman applicant (synthetic demo rule)"},{"field":"occupation","operator":"IN","value":["entrepreneur","self-employed"],"description":"Entrepreneur or self-employed (synthetic demo rule)"}]},
 {"id":"senior-demo","name":"Senior Wellbeing Assistance (Demo)","category":"Senior Citizens","government":"Synthetic demo dataset","ministry":"Demo only","state":"All India","benefits":"Illustrative senior support; no real benefit is offered.","description":"Synthetic example for senior support discovery.","eligibility_summary":"Synthetic demo criteria only. Not an official government scheme.","application_process":"Check official central and state social welfare portals.","application_url":"https://www.india.gov.in/","source_url":"https://www.india.gov.in/","source_name":"India.gov.in general directory; rules are synthetic","last_verified":"2026-09-26","active":True,"documents":["Aadhaar","Age Proof","Bank Document"],"rules":[{"field":"age","operator":">=","value":60,"description":"Age 60 or above (synthetic demo rule)"}]},
 {"id":"access-demo","name":"Accessible Services Support (Demo)","category":"Disability","government":"Synthetic demo dataset","ministry":"Demo only","state":"All India","benefits":"Illustrative accessibility services; no real benefit is offered.","description":"Synthetic example for disability service discovery.","eligibility_summary":"Synthetic demo criteria only. Not an official government scheme.","application_process":"Contact a district social welfare office to verify available services.","application_url":"https://www.india.gov.in/","source_url":"https://www.india.gov.in/","source_name":"India.gov.in general directory; rules are synthetic","last_verified":"2026-09-26","active":True,"documents":["Aadhaar","Disability Certificate"],"rules":[{"field":"disability_status","operator":"==","value":True,"description":"Reports a disability (synthetic demo rule)"}]},
 {"id":"work-demo","name":"Employment Pathways Support (Demo)","category":"Employment","government":"Synthetic demo dataset","ministry":"Demo only","state":"All India","benefits":"Illustrative job-seeker support; no real benefit is offered.","description":"Synthetic example for employment service discovery.","eligibility_summary":"Synthetic demo criteria only. Not an official government scheme.","application_process":"Explore official employment services and state skill missions.","application_url":"https://www.india.gov.in/","source_url":"https://www.india.gov.in/","source_name":"India.gov.in general directory; rules are synthetic","last_verified":"2026-09-26","active":True,"documents":["Aadhaar","Education Certificate"],"rules":[{"field":"employment_status","operator":"IN","value":["unemployed","job-seeking"],"description":"Currently looking for work (synthetic demo rule)"}]}
]
SEED_DIR = Path(__file__).resolve().parents[2] / "database" / "seed"

def read_csv(name: str) -> list[dict[str, str]]:
    with (SEED_DIR / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def load_catalog() -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    scheme_rows = read_csv("schemes.csv")
    rule_rows = read_csv("eligibility_rules.csv")
    document_rows = read_csv("scheme_documents.csv")
    def parse_value(field: str, operator: str, raw: str) -> Any:
        if operator == "BETWEEN":
            return [int(part.strip()) for part in raw.split("-", 1)]
        if operator == "IN":
            return [part.strip() for part in raw.split("|")]
        if field in {"age", "annual_family_income", "family_size"}:
            try: return int(raw)
            except ValueError: return raw
        if field in {"is_farmer", "is_student", "is_pregnant", "has_bank_account", "has_lpg_connection", "disability"} and raw.lower() in {"yes", "no"}:
            return raw.lower() == "yes"
        return raw
    by_scheme: dict[str, list[dict[str, Any]]] = {}
    op_map = {"equals":"==", "greater_than_or_equal":">=", "less_than_or_equal":"<=", "between":"BETWEEN", "in":"IN"}
    for row in rule_rows:
        op = op_map.get(row["operator"].lower(), row["operator"].upper())
        by_scheme.setdefault(row["scheme_id"], []).append({
            "field":row["field"], "operator":op,
            "value":parse_value(row["field"], op, row["value"]),
            "description":f'{row["field"]} {row["operator"]} {row["value"]}'+(f' — {row["notes"]}' if row["notes"] else ""),
            "notes":row["notes"],
            "required":row["required"].lower()=="true", "rule_id":row["rule_id"]
        })
    docs_by_scheme: dict[str, list[dict[str, Any]]] = {}
    for row in document_rows:
        docs_by_scheme.setdefault(row["scheme_id"], []).append({
            "name":row["document_name"], "type":row["document_type"],
            "requirement_level":row["requirement_level"], "notes":row["notes"]
        })
    catalog=[]
    for row in scheme_rows:
        sid=row["scheme_id"]
        catalog.append({
            "id":sid, "name":row["scheme_name"], "category":row["category"],
            "government":row["government"], "ministry":"Not specified in provided CSV",
            "state":"All India" if row["government"]=="Central" else "Uttar Pradesh",
            "benefits":row["benefits"], "description":row["eligibility_summary"],
            "eligibility_summary":row["eligibility_summary"], "eligibility_fields":row["eligibility_fields"],
            "application_process":"Review current scheme guidance and application instructions at the official portal.",
            "application_url":row["application_url"], "source_url":row["source_url"],
            "source_name":urlparse(row["source_url"]).netloc or "Source URL supplied in schemes.csv", "last_verified":row["last_verified"],
            "active":True, "synthetic":False, "rules":by_scheme.get(sid,[]),
            "documents":docs_by_scheme.get(sid,[])
        })
    return catalog, read_csv("demo_users.csv"), read_csv("user_documents.csv"), read_csv("scheme_categories.csv")

try:
    SCHEMES, DEMO_USERS, DEMO_USER_DOCUMENTS, SCHEME_CATEGORIES = load_catalog()
except (OSError, KeyError):
    DEMO_USERS, DEMO_USER_DOCUMENTS, SCHEME_CATEGORIES = [], [], []
for scheme in SCHEMES:
    scheme["recommendation_metadata"]=metadata_for(scheme)
RAG_CHUNKS=build_chunks(SCHEMES)
PROFILE: dict[str, Any] = {k:None for k in ["age","date_of_birth","gender","state","district","city","rural_or_urban","residence_type","annual_income","annual_family_income","monthly_income","occupation","education","education_level","student_status","is_student","family_size","number_of_children","marital_status","widow_status","senior_citizen_status","category","caste_category","social_category","disability_status","disability","land_ownership","land_holding","farmer_status","is_farmer","entrepreneur_status","employment_status","institution_type","has_bank_account","has_lpg_connection","is_pregnant","beneficiary_relationship","verified_annual_income"]}
PROFILE.update(existing_benefits=[],language="English",_statuses={})
DOCUMENTS: list[dict[str, Any]] = []
app=FastAPI(title="Welfare Navigator API",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000"],allow_methods=["*"],allow_headers=["*"])
class ChatRequest(BaseModel):
 message:str
 language:str|None=None
class ProfileBody(BaseModel):
 profile:dict[str,Any]
class CheckBody(BaseModel):
 profile:dict[str,Any]|None=None
 scheme_id:str|None=None
 query:str=""
class ChecklistBody(BaseModel):
 scheme_id:str
class ContextBody(BaseModel):
 query:str=""
 profile:dict[str,Any]|None=None
class DocumentReviewBody(BaseModel):
 field:str
 confirm:bool

def evaluate(rule:dict[str,Any],profile:dict[str,Any])->str:
 field=rule["field"]
 aliases={"annual_family_income":"annual_income","is_student":"student_status","is_farmer":"farmer_status","disability":"disability_status","social_category":"category"}
 actual=profile.get(field)
 if actual is None and field in aliases: actual=profile.get(aliases[field])
 if field in {"annual_income","annual_family_income"} and profile.get("_statuses",{}).get("verified_annual_income")=="DOCUMENT_VERIFIED":
  actual=profile.get("verified_annual_income")
 op=rule["operator"].upper().replace("=", "==") if rule["operator"]=="=" else rule["operator"].upper(); value=rule.get("value")
 if op=="AND":
  states=[evaluate({"field":k,"operator":"==","value":v},profile) for k,v in value.items()]
  return "FAILED" if "FAILED" in states else "UNKNOWN" if "UNKNOWN" in states else "MATCHED"
 if op=="OR":
  states=[evaluate({"field":k,"operator":"==","value":v},profile) for k,v in value.items()]
  return "MATCHED" if "MATCHED" in states else "UNKNOWN" if "UNKNOWN" in states else "FAILED"
 if actual is None or actual=="": return "UNKNOWN"
 try:
  if op=="BETWEEN": return "MATCHED" if value[0] <= actual <= value[1] else "FAILED"
  equal=lambda a,b: a.lower()==b.lower() if isinstance(a,str) and isinstance(b,str) else a==b
  result={"==":lambda:equal(actual,value),"!=":lambda:not equal(actual,value),"<=":lambda:actual<=value,">=":lambda:actual>=value,"<":lambda:actual<value,">":lambda:actual>value,"IN":lambda:any(equal(actual,item) for item in value),"NOT_IN":lambda:not any(equal(actual,item) for item in value),"CONTAINS":lambda:value.casefold() in actual.casefold() if isinstance(actual,str) and isinstance(value,str) else value in actual,"AND":lambda:all(profile.get(k)==v for k,v in value.items()),"OR":lambda:any(profile.get(k)==v for k,v in value.items())}[op]()
  return "MATCHED" if result else "FAILED"
 except (TypeError,KeyError): return "UNKNOWN"
def check(scheme:dict[str,Any],profile:dict[str,Any])->dict[str,Any]:
 checks=[{**r,"status":evaluate(r,profile)} for r in scheme["rules"]]
 required=[c for c in checks if c.get("required",True)]
 status="NEEDS_MORE_INFORMATION" if not required else "APPEARS_UNLIKELY" if any(c["status"]=="FAILED" for c in required) else "NEEDS_MORE_INFORMATION" if any(c["status"]=="UNKNOWN" for c in required) else "POTENTIAL_MATCH"
 return {"scheme_id":scheme["id"],"status":status,"checks":checks,"matched":[c["description"] for c in checks if c["status"]=="MATCHED"],"unknown":[c["description"] for c in checks if c["status"]=="UNKNOWN"],"failed":[c["description"] for c in checks if c["status"]=="FAILED"]}

def llm_extract_fields(message: str) -> dict[str, Any]:
    """Optional single-call profile extraction. No key or provider failure uses deterministic demo extraction."""
    api_key=os.getenv("OPENAI_API_KEY")
    if not api_key:return {}
    schema_fields=["age","gender","state","district","city","occupation","education","education_level","annual_income","student_status","farmer_status","widow_status","marital_status","disability_status","senior_citizen_status","entrepreneur_status","family_size","is_pregnant","employment_status","institution_type","has_bank_account","beneficiary_relationship"]
    prompt=("Extract only facts the user explicitly stated. Return JSON with keys profile and evidence. "
            "profile has only these allowed keys: "+", ".join(schema_fields)+". "
            "evidence maps each non-null profile key to an exact quote copied from the user text. "
            "Use null for unknown; never infer sensitive traits. Use false only when the user explicitly denies the trait. "
            "student_status and farmer_status are booleans. User text: "+message)
    body=json.dumps({"model":os.getenv("OPENAI_MODEL","gpt-4o-mini"),"response_format":{"type":"json_object"},
                     "messages":[{"role":"system","content":"You extract explicitly stated profile facts. You do not decide eligibility."},{"role":"user","content":prompt}]}).encode()
    request=urllib.request.Request("https://api.openai.com/v1/chat/completions",data=body,
             headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(request,timeout=8) as response: data=json.loads(response.read())
        result=json.loads(data["choices"][0]["message"]["content"])
        profile=result.get("profile",{}); evidence=result.get("evidence",{})
        local=extract(message); negatives=explicit_negatives(message); safe={}
        for key,value in profile.items():
            quote=evidence.get(key)
            if key not in schema_fields or value is None or not isinstance(quote,str) or quote.casefold() not in message.casefold():continue
            if isinstance(value,bool):
                role={"student_status":"STUDENT","farmer_status":"FARMER","widow_status":"WIDOW","disability_status":"DISABILITY","entrepreneur_status":"ENTREPRENEUR"}.get(key)
                if value is False and role not in negatives and key not in local:continue
                if value is True and key not in local and role not in detect_intent(quote)["roles"]:continue
            safe[key]=value
        return safe
    except (OSError,ValueError,KeyError,TypeError,urllib.error.URLError):
        return {}

def extract_profile_fields(message: str) -> tuple[dict[str,Any],str]:
    fields=extract(message)
    fields.update(llm_extract_fields(message))
    return fields,"openai" if os.getenv("OPENAI_API_KEY") else "demo"
def extract(message:str)->dict[str,Any]:
 text=message.casefold(); f={}; negatives=explicit_negatives(message)
 m=re.search(r"\b(\d{1,3})\s*(?:-?years?[ -]+old|yrs? old|saal(?:\s+ka|\s+ki|\s+ke)?|साल|वर्ष)",text,re.I)
 if m:f["age"]=int(m.group(1))
 income_pattern=r"(?:family\s+(?:ki\s+)?income|income|earn(?:s|ing)?|meri\s+family\s+income|कमाई|आय)\s*(?:of|is|:|hai|है)?\s*(?:₹|rs\.?\s*)?([\d,]+(?:\.\d+)?)\s*(lakh|लाख|lac|k|thousand)?\b"
 m=re.search(income_pattern,text,re.I)
 if m:
  n=float(m.group(1).replace(",","")); unit=(m.group(2) or "").lower()
  f["annual_income"]=int(n*(100000 if unit in ("lakh","लाख","lac") else 1000 if unit in ("k","thousand") else 1))
 for key in ["Uttar Pradesh","Bihar","Rajasthan","Maharashtra"]:
  if key.casefold() in text:f["state"]=key
 cities={"lucknow":"Lucknow","लखनऊ":"Lucknow","delhi":"Delhi","दिल्ली":"Delhi","jaipur":"Jaipur","जयपुर":"Jaipur","patna":"Patna","पटना":"Patna","mumbai":"Mumbai","मुंबई":"Mumbai"}
 for alias,city in cities.items():
  if alias in text:
   f["city"]=city;f["district"]=city
   if city=="Lucknow":f["state"]=f.get("state","Uttar Pradesh")
   elif city=="Jaipur":f["state"]=f.get("state","Rajasthan")
   elif city=="Patna":f["state"]=f.get("state","Bihar")
   elif city in {"Delhi","Mumbai"}:f["state"]=f.get("state",city)
   break
 relation=None
 if re.search(r"\b(mother|maa|mummy|mom)\b",text):relation="mother"
 elif re.search(r"\b(father|papa|pita|dad)\b",text):relation="father"
 if relation and re.search(r"\b(?:meri|mere|my|mother|maa|papa|father)\b",text):f["beneficiary_relationship"]=relation
 student_pattern=r"\b(student|students|studying|undergraduate|postgraduate|विद्यार्थी|छात्र|छात्रा|पढ़ता|पढ़ती|padh raha|padh rahi|padhai kar|college mein padhta|college mein padhti)\b"
 if re.search(student_pattern,text,re.I):
  f["student_status"]="STUDENT" not in negatives
  if f["student_status"]:f["occupation"]="student"
  if re.search(r"\b(college|university|degree|college fees)\b|कॉलेज",text,re.I):f["education"]="college"
  if re.search(r"\b(postgraduate|post graduate|masters|master's)\b",text,re.I):f["education_level"]="postgraduate"
  elif re.search(r"\b(undergraduate|under graduate|bachelor|college)\b",text,re.I):f["education_level"]="undergraduate"
 if re.search(r"\b(farmer|farmers|farm|farmland|cultivator|cultivation|farming|agriculture|kisan|किसान|खेती|kheti|fasal)\b",text,re.I):
  f["farmer_status"]="FARMER" not in negatives
  if f["farmer_status"]:f["occupation"]="farmer"
 if re.search(r"\b(widow|widowed|विधवा|vidhwa)\b",text,re.I):
  f["widow_status"]="WIDOW" not in negatives
  if f["widow_status"]:f["marital_status"]="Widowed"
 if f.get("age",0)>=60 or re.search(r"\b(senior citizen|elderly|old age|retired|वरिष्ठ नागरिक|बुजुर्ग|buzurg)\b",text,re.I):
  f["senior_citizen_status"]=True
 if re.search(r"\b(disabled|disability|person with disability|दिव्यांग|विकलांग)\b",text,re.I):f["disability_status"]="DISABILITY" not in negatives
 if re.search(r"\b(entrepreneur|business owner|self.employed|startup|उद्यमी)\b",text,re.I):f["entrepreneur_status"]="ENTREPRENEUR" not in negatives
 if re.search(r"\b(pregnant|maternity|गर्भवती)\b",text,re.I):f["is_pregnant"]=True
 if re.search(r"\b(woman|women|female|girl|mother|महिला|औरत)\b",text,re.I):f["gender"]="Female"
 elif re.search(r"\b(man|male|boy)\b",text,re.I):f["gender"]="Male"
 marital=re.search(r"\b(single|married|divorced|widowed)\b",text,re.I)
 if marital:f["marital_status"]={"widowed":"Widowed"}.get(marital.group(1).lower(),marital.group(1).title())
 if re.search(r"\b(unemployed|job.?seeking|looking for work|berozgar|naukri chahiye)\b",text,re.I):f["employment_status"]="unemployed"
 if re.search(r"\b(government college|govt college|सरकारी कॉलेज|sarkari college)\b",text,re.I):f["institution_type"]="government"
 elif re.search(r"\b(private college|private|niji college)\b",text,re.I):f["institution_type"]="private"
 return f

def apply_profile(f:dict[str,Any]):
 aliases={"student_status":"is_student","farmer_status":"is_farmer","disability_status":"disability","annual_income":"annual_family_income","category":"social_category"}
 for k,v in f.items():
  PROFILE[k]=v;PROFILE["_statuses"][k]="USER_REPORTED"
  if k=="senior_citizen_status" and PROFILE.get("age") is not None and int(PROFILE["age"])>=60:PROFILE["_statuses"][k]="DERIVED"
  if k=="annual_income" and v is not None and PROFILE.get("verified_annual_income") is not None and int(v)!=int(PROFILE["verified_annual_income"]):
   PROFILE["_statuses"]["verified_annual_income"]="NEEDS_REVIEW"
   for doc in DOCUMENTS:
    if doc.get("status")=="USER_CONFIRMED_CONTENT":doc["status"]="DISCREPANCY_NEEDS_REVIEW"
  if k in aliases:PROFILE[aliases[k]]=v;PROFILE["_statuses"][aliases[k]]="USER_REPORTED"
def recommendations(p:dict[str,Any],query:str=""):
 return rank_recommendations(SCHEMES,p,query,RAG_CHUNKS,check_fn=check)

@app.get("/api/health")
def health():return {"status":"ok","demo_mode":True}
@app.get("/api/profile")
def get_profile():return PROFILE
def demo_user_record(user_id: str) -> dict[str, Any] | None:
 row=next((u for u in DEMO_USERS if u["user_id"]==user_id),None)
 if not row:return None
 bool_fields={"disability","has_bank_account","is_farmer","is_student","is_pregnant"}
 profile={}
 mapping={"annual_family_income":"annual_income","social_category":"category"}
 for key,value in row.items():
  if key in {"user_id","name"}: continue
  dest=mapping.get(key,key)
  if key in {"age","annual_family_income","family_size"}: profile[dest]=int(value) if value else None
  elif key in bool_fields: profile[dest]=value.lower()=="yes"
  else: profile[dest]=value
 profile["_statuses"]={k:"DEMO_DATA" for k in profile}
 documents=[]
 for d in DEMO_USER_DOCUMENTS:
  if d["user_id"]==user_id:
   documents.append({"id":d["user_document_id"],"filename":d["document_name"],"type":d["document_name"],"status":d["status"].upper(),"demo":True,"note":"Sample CSV status only; not evidence of legal validity or verification."})
 return {"user_id":user_id,"name":row["name"],"profile":profile,"documents":documents}
@app.get("/api/demo-users")
def list_demo_users():
 return [{"user_id":u["user_id"],"name":u["name"],"occupation":u["occupation"],"district":u["district"],"state":u["state"]} for u in DEMO_USERS]
@app.get("/api/demo-users/{user_id}")
def get_demo_user(user_id:str):
 record=demo_user_record(user_id)
 if not record: raise HTTPException(404,"Demo profile not found")
 return record
@app.post("/api/demo-users/{user_id}/load")
def load_demo_user(user_id:str):
 global DOCUMENTS
 record=demo_user_record(user_id)
 if not record: raise HTTPException(404,"Demo profile not found")
 PROFILE.clear(); PROFILE.update(record["profile"])
 PROFILE["language"]="English"; PROFILE["existing_benefits"]=[]
 DOCUMENTS=record["documents"]
 return record
@app.put("/api/profile")
def put_profile(body:ProfileBody):apply_profile(body.profile);return PROFILE
@app.post("/api/profile/extract")
def extract_profile(body:ChatRequest):
 f,provider=extract_profile_fields(body.message);apply_profile(f)
 return {"extracted":f,"profile":PROFILE,"intent":detect_intent(body.message,PROFILE),"provider":provider}
@app.get("/api/schemes")
def get_schemes(category:str|None=None,state:str|None=None,q:str|None=None):
 rows=SCHEMES
 if category:rows=[s for s in rows if s["category"].lower()==category.lower()]
 if state:rows=[s for s in rows if s["state"]=="All India" or s["state"].lower()==state.lower()]
 if q:rows=[s for s in rows if q.lower() in (s["name"]+s["description"]+s["category"]).lower()]
 return rows
@app.get("/api/scheme-categories")
def get_categories(): return SCHEME_CATEGORIES
@app.get("/api/schemes/{scheme_id}")
def get_scheme(scheme_id:str):
 s=next((s for s in SCHEMES if s["id"]==scheme_id),None)
 if not s:raise HTTPException(404,"Scheme not found")
 return s
@app.post("/api/schemes/search")
def search(body:dict[str,Any]):return get_schemes(body.get("category"),body.get("state"),body.get("query"))
@app.post("/api/schemes/recommend")
def recommend(body:CheckBody):return recommendations(body.profile or PROFILE,body.query)
@app.post("/api/intent/detect")
def intent_detect(body:ContextBody):return detect_intent(body.query,body.profile or PROFILE)
@app.post("/api/schemes/retrieve")
def scheme_retrieve(body:ContextBody):
 result=retrieve_candidates(SCHEMES,body.profile or PROFILE,body.query,RAG_CHUNKS)
 result["candidate_ids"]=sorted(result["candidate_ids"])
 result["candidates"]=[{"scheme_id":sid,"name":next(s["name"] for s in SCHEMES if s["id"]==sid)} for sid in result["candidate_ids"]]
 result["rag_evidence"]=rag_search(SCHEMES,body.profile or PROFILE,body.query,RAG_CHUNKS,limit=5)
 result.pop("rag_by_scheme",None)
 return result
@app.post("/api/rag/search")
def rag_search_endpoint(body:ContextBody):
 return {"chunks":rag_search(SCHEMES,body.profile or PROFILE,body.query,RAG_CHUNKS,limit=5),"vector_store":"cached in-memory sparse vector index"}
@app.post("/api/recommendations/refresh")
def refresh_recommendations(body:ContextBody):
 return recommendations(body.profile or PROFILE,body.query)
@app.post("/api/eligibility/check")
def eligibility(body:CheckBody):
 rows=[s for s in SCHEMES if not body.scheme_id or s["id"]==body.scheme_id]
 if body.scheme_id and not rows:raise HTTPException(404,"Scheme not found")
 return [check(s,body.profile or PROFILE) for s in rows]
def run_agent_query(body:ChatRequest)->dict[str,Any]:
 detected=detect_language(body.message)
 selected=body.language if body.language in {"English","Hindi","Hinglish"} else detected
 fields,provider=extract_profile_fields(body.message)
 apply_profile(fields);PROFILE["language"]=selected
 result=recommendations(PROFILE,body.message);recs=result["recommendations"]
 unknown=next((item for scheme in recs for item in scheme["unknown_criteria"]),None)
 labels={"age":"age","annual_family_income":"annual household income","annual_income":"annual household income","is_farmer":"whether you currently farm","farmer_status":"whether you currently farm","marital_status":"marital status","widow_status":"whether you are widowed","institution_type":"college or institution type","has_bank_account":"whether you have a bank account","is_student":"whether you are currently studying","student_status":"whether you are currently studying","education":"your current education level","education_level":"your current education level","is_pregnant":"whether you are currently pregnant","disability":"whether you have a disability","disability_status":"whether you have a disability","family_size":"family size","land_ownership":"whether you own or cultivate land"}
 key=next((field for field in labels if unknown and any(field==rule["field"] for scheme in recs for rule in scheme["eligibility"]["checks"] if rule["description"]==unknown)),None)
 question=("Could you share your "+labels[key]+"?" if key else "What kind of support are you looking for?" if not recs else "Would you like to review these relevant schemes or add more details?")
 hindi_questions={"age":"क्या आप अपनी उम्र बता सकते हैं?","annual_income":"क्या आप परिवार की वार्षिक आय बता सकते हैं?","annual_family_income":"क्या आप परिवार की वार्षिक आय बता सकते हैं?","student_status":"क्या आप अभी पढ़ाई कर रहे हैं?","is_student":"क्या आप अभी पढ़ाई कर रहे हैं?","education":"आप अभी किस स्तर पर पढ़ाई कर रहे हैं?","education_level":"आप अभी किस स्तर पर पढ़ाई कर रहे हैं?","institution_type":"आपका कॉलेज सरकारी, सहायता प्राप्त या निजी है?","farmer_status":"क्या आप खेती करते हैं?","is_farmer":"क्या आप खेती करते हैं?","widow_status":"क्या आवेदक विधवा हैं?","marital_status":"क्या आवेदक की वैवाहिक स्थिति बता सकते हैं?","disability":"क्या आवेदक को दिव्यांगता है?","disability_status":"क्या आवेदक को दिव्यांगता है?","family_size":"परिवार में कुल कितने सदस्य हैं?"}
 hinglish_questions={"age":"Aap apni umar bata sakte hain?","annual_income":"Family ki saalana income bata sakte hain?","annual_family_income":"Family ki saalana income bata sakte hain?","student_status":"Kya aap abhi padhai kar rahe hain?","is_student":"Kya aap abhi padhai kar rahe hain?","education":"Aap abhi kis level par padh rahe hain?","education_level":"Aap abhi kis level par padh rahe hain?","institution_type":"Aapka college government, aided ya private hai?","farmer_status":"Kya aap kheti karte hain?","is_farmer":"Kya aap kheti karte hain?","widow_status":"Kya applicant widow hain?","marital_status":"Applicant ki marital status kya hai?","disability":"Kya applicant ko disability hai?","disability_status":"Kya applicant ko disability hai?","family_size":"Family mein kitne members hain?"}
 if selected=="Hindi":question=hindi_questions.get(key, "आप किस तरह की सहायता खोज रहे हैं?" if not recs else "क्या आप इन योजनाओं को देखना या और जानकारी जोड़ना चाहेंगे?")
 elif selected=="Hinglish":question=hinglish_questions.get(key,"Aapko kis tarah ki madad chahiye?" if not recs else "Kya aap in schemes ko dekhein ya aur details batayein?")
 response_prefix={"English":"I’ve updated your profile. These are preliminary matches, not an official eligibility decision. ","Hindi":"आपकी जानकारी अपडेट की है। ये प्रारंभिक मिलान हैं, आधिकारिक पात्रता निर्णय नहीं। ","Hinglish":"Aapki profile update kar di hai. Yeh shuruati matches hain, official eligibility decision nahi. "}[selected]
 print(f"[LANGUAGE] selected={selected} detected={detected}")
 print(f"[PROFILE] extracted_fields={len(fields)} known_fields={sum(value is not None for key,value in PROFILE.items() if key!='_statuses')}")
 print(f"[INTENT] {','.join([result['intent']['primary_category'],*result['intent']['secondary_categories']])}")
 print(f"[FILTER] candidate_count={result['candidate_count']}")
 print(f"[RAG] retrieved_count={sum(len(s.get('rag_evidence',[])) for s in recs)} available={result['rag_available']}")
 print(f"[RANKING] returned={len(recs)}")
 return {"response":response_prefix+question,"follow_up_question":question,"missing_information":[key] if key else [],
         "profile":PROFILE,"extracted":fields,"intent":result["intent"],"concepts":result["intent"]["concepts"],
         "recommendations":recs,"provider":provider,"language":selected,"detected_language":detected,
         "candidate_count":result["candidate_count"],"rag_available":result["rag_available"]}

@app.post("/api/agent/query")
def agent_query(body:ChatRequest):return run_agent_query(body)

@app.post("/api/chat")
def chat(body:ChatRequest):return run_agent_query(body)
@app.post("/api/documents/upload")
async def upload(file:UploadFile=File(...)):
 mime_by_extension={".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".txt":"text/plain"}
 extension=Path(file.filename or "").suffix.lower()
 content_type=file.content_type if file.content_type in mime_by_extension.values() else mime_by_extension.get(extension)
 if content_type not in mime_by_extension.values():raise HTTPException(415,"Upload a PDF, PNG, JPEG, or text file.")
 content=await file.read()
 if len(content)>10*1024*1024:raise HTTPException(413,"File must be 10 MB or smaller.")
 name=file.filename or "document"; kind=next((k for token,k in [("income","Income Certificate"),("student","Student Certificate"),("domicile","Domicile Certificate"),("aadhaar","Aadhaar")] if token in name.lower()),"Other")
 text_content=""; extraction_note="Image OCR is unavailable in this demo; no document values were inferred."
 if content_type=="text/plain":
  text_content=content.decode("utf-8",errors="replace")[:100000];extraction_note="Text extracted from the uploaded file. Review it before use; the file's authenticity is not verified."
 elif content_type=="application/pdf":
  try:
   from pypdf import PdfReader
   reader=PdfReader(BytesIO(content));text_content="\n".join(page.extract_text() or "" for page in reader.pages[:20])[:100000]
   extraction_note="Selectable PDF text extracted. Review values; the file's authenticity is not verified." if text_content.strip() else "No selectable text found. Scanned PDF OCR is unavailable in this demo."
  except Exception as exc:
   extraction_note="PDF text extraction was unavailable; please review the file manually."
 extracted=extract(text_content) if text_content.strip() else {}
 extracted={key:value for key,value in extracted.items() if key in {"annual_income","age","state","district","city","gender","marital_status"}}
 if text_content.strip():
  if re.search(r"income\s+certificate|आय प्रमाणपत्र",text_content,re.I):kind="Income Certificate"
  issue=re.search(r"(?:date\s+of\s+issue|issue\s+date|issued\s+on)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})",text_content,re.I)
  number=re.search(r"(?:certificate\s*(?:no\.?|number)|document\s*(?:no\.?|number))\s*[:#\-]?\s*([A-Z0-9/-]{4,})",text_content,re.I)
  if kind!="Other":extracted["certificate_type"]=kind
  if issue:extracted["issue_date"]=issue.group(1)
  if number:extracted["document_number"]=number.group(1)
 discrepancies=[]
 if "annual_income" in extracted and PROFILE.get("annual_income") is not None and int(extracted["annual_income"])!=int(PROFILE["annual_income"]):
  discrepancies.append({"field":"annual_income","user_reported":PROFILE["annual_income"],"document_extracted":extracted["annual_income"],"status":"NEEDS_USER_REVIEW"})
 doc={"id":f"doc-{len(DOCUMENTS)+1}","filename":name,"type":kind,"status":"EXTRACTED_NEEDS_REVIEW" if extracted else "NEEDS_REVIEW","size":len(content),"demo":True,"extracted_fields":extracted,"discrepancies":discrepancies,"note":extraction_note}
 DOCUMENTS.append(doc);return doc
@app.post("/api/documents/{document_id}/confirm")
def confirm_document(document_id:str,body:DocumentReviewBody):
 doc=next((item for item in DOCUMENTS if item["id"]==document_id),None)
 if not doc:raise HTTPException(404,"Document not found")
 if body.field!="annual_income" or body.field not in doc.get("extracted_fields",{}):raise HTTPException(400,"That extracted field is not available for review.")
 if not body.confirm:
  doc["status"]="REVIEW_REQUIRED";return {"document":doc,"profile":PROFILE}
 PROFILE["verified_annual_income"]=doc["extracted_fields"]["annual_income"]
 PROFILE.setdefault("_statuses",{})["verified_annual_income"]="DOCUMENT_VERIFIED"
 PROFILE.setdefault("_statuses",{})["annual_income"]=PROFILE.get("_statuses",{}).get("annual_income","USER_REPORTED" if PROFILE.get("annual_income") is not None else "UNKNOWN")
 doc["status"]="USER_CONFIRMED_CONTENT"
 doc["note"]="The user confirmed the extracted value for eligibility review. Document authenticity is not independently verified."
 return {"document":doc,"profile":PROFILE,"reported_annual_income":PROFILE.get("annual_income"),"document_income":PROFILE["verified_annual_income"],"discrepancy":PROFILE.get("annual_income") is not None and PROFILE.get("annual_income")!=PROFILE["verified_annual_income"]}
@app.post("/api/documents/analyze")
def analyze():return {"documents":DOCUMENTS,"message":"Selectable PDF/text extraction is available. Image/scanned PDF OCR and document authenticity checks are not configured."}
@app.get("/api/documents")
def documents():return DOCUMENTS
@app.get("/api/readiness/{scheme_id}")
def readiness(scheme_id:str):
 s=next((s for s in SCHEMES if s["id"]==scheme_id),None)
 if not s:raise HTTPException(404,"Scheme not found")
 docs=[]
 for required in s["documents"]:
  req_name=required["name"] if isinstance(required,dict) else required
  matched=next((d for d in DOCUMENTS if req_name.lower() in d.get("type","").lower() or d.get("type","").lower() in req_name.lower()),None)
  docs.append({"name":req_name,"status":matched.get("status","MISSING") if matched else "MISSING","requirement_level":required.get("requirement_level","Usually") if isinstance(required,dict) else "Usually","notes":required.get("notes","") if isinstance(required,dict) else ""})
 return {"scheme":s,"eligibility":check(s,PROFILE),"documents":docs,"readiness_percent":round(sum(d["status"]!="MISSING" for d in docs)/max(1,len(docs))*100)}
@app.post("/api/application/checklist")
def checklist(body:ChecklistBody):return readiness(body.scheme_id)
