from pathlib import Path

path = Path("outputs/frontend/app/page.tsx")
content = path.read_text(encoding="utf-8")
replacements = [
    ('</h3>{[["Age"', '</h3><label className="demoSelect">Sample profile<select value={demoId} onChange={e=>demo(e.target.value)}>{demoUsers.map((u:any)=><option key={u.user_id} value={u.user_id}>{u.user_id} · {u.name} — {u.occupation}, {u.district}</option>)}</select></label>{[["Age"'),
    ('["All","Education","Agriculture","Entrepreneurship","Senior Citizens","Disability","Employment"]', '["All",...Array.from(new Set(all.map(s=>s.category)))]'),
    ('<small>{d.type} · Needs review</small>', '<small>Sample status: {d.status} · not legal verification</small>'),
    ('{chosen.documents.join(" · ")}', '{chosen.documents.map(d=>typeof d==="string"?d:d.name).join(" · ")}'),
    ('onClick={demo}', 'onClick={()=>demo()}'),
    ('Sample records and criteria are synthetic; they do not describe real government benefits.', 'Scheme information and source links are supplied in the CSV. Matching rules are preliminary and must be checked against current official guidance.'),
    ('<b>Demo dataset:</b> Scheme names and eligibility rules are fictional. Verify schemes and current requirements using official government sources.', '<b>Demo matching:</b> Scheme records and sources came from the supplied CSV. Encoded rules may omit conditions; confirm current requirements with the linked official source.'),
    ('Synthetic demo criteria only. This is not an official scheme description or eligibility decision.', 'This is a preliminary demo match, not an official eligibility decision. Encoded rules may omit important conditions; verify current criteria at the linked source.'),
    ('docs.some(d=>d.type===x)?"Uploaded":"To prepare"', 'docs.some(d=>d.type===x)?"In sample list":"To prepare"'),
    ('["Home","Assessment","Recommendations","Documents","Readiness"]', '["Home","Assessment","Recommendations","Schemes","Documents","Readiness"]'),
    ('<div className="cards">{results.map(s=>', '<div className="refreshState">{refreshing&&<span>Updating recommendations…</span>}{!refreshing&&section==="Recommendations"&&results.length===0&&<p>No strong matches found. Tell the assistant what kind of support you are looking for.</p>}</div><div className="cards">{results.map(s=>'),
    ('</div><div className="schemeFoot"><small><Landmark size={13}/> Demo record</small>', '</div><details className="whySeeing"><summary>Why am I seeing this?</summary><p>Category: {s.recommendation_metadata?.category_key||s.category} ✓</p><p>Target group: {s.recommendation_metadata?.target_groups?.join(", ")||"General"} ✓</p><p>Rules: {s.eligibility?.matched?.length||0} matched · {s.eligibility?.unknown?.length||s.eligibility?.checks?.filter((c:any)=>c.status==="UNKNOWN").length||0} need information</p>{s.source&&<p>Source verified: {s.source.last_verified||"Date not provided"} · <a href={s.source.source_url} target="_blank" rel="noreferrer">View source</a></p>}{s.rag_evidence?.length>0&&<p>Retrieved evidence: {s.rag_evidence[0].content} <a href={s.rag_evidence[0].source_url} target="_blank" rel="noreferrer">Source</a></p>}</details><div className="schemeFoot"><small><Landmark size={13}/> CSV source</small>'),
    ('{check(chosen,profile).checks.map((c:any)=><div className="profileRow"', '{(chosen.eligibility||check(chosen,profile)).checks.map((c:any)=><div className="profileRow"'),
    ('<h3>Application details</h3><p>{chosen.description}</p>', '<h3>Application details</h3><p>{chosen.description}</p>{chosen.rag_evidence?.length>0&&<><h3>Retrieved source information</h3>{chosen.rag_evidence.map((e:any,i:number)=><p className="source" key={i}>{e.content} · <a href={e.source_url} target="_blank" rel="noreferrer">{e.source_name}</a> · Last checked {e.last_verified}</p>)}</>}'),
    ('<small className="eyebrow">{chosen.category} · SYNTHETIC DEMO</small>', '<small className="eyebrow">{chosen.category} · SOURCE-ATTRIBUTED DEMO MATCH</small>'),
]
for old, new in replacements:
    content = content.replace(old, new)
path.write_text(content, encoding="utf-8")
