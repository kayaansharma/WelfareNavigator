# Welfare Navigator 🇮🇳

### AI-Powered Multilingual Government Welfare Scheme Navigator

**Discover → Verify → Prepare → Apply**

Welfare Navigator helps citizens discover government welfare schemes, understand potential eligibility, identify missing information/documents, and prepare for applications through **AI, RAG, deterministic eligibility rules, voice, and multilingual interaction**.

---

## 🎯 Problem

Government welfare information is spread across many portals and often has complex eligibility requirements based on:

* Age
* Income
* Occupation
* Location
* Education
* Gender
* Family status
* Disability
* Other scheme-specific conditions

Citizens may find a scheme but still not know **whether it is relevant, what information is missing, which documents are required, or what to do next**.

---

## 💡 Solution

Welfare Navigator combines conversational AI with structured eligibility evaluation.

```text
Voice / Text
     ↓
Language Detection
     ↓
AI Profile Extraction
     ↓
Intent Detection
     ↓
Metadata Filtering
     ↓
RAG Retrieval
     ↓
Eligibility Rules
     ↓
Hybrid Re-ranking
     ↓
Personalized Schemes
     ↓
Documents + Missing Information
     ↓
Application Readiness
     ↓
Official Government Portal
```

### Key Differentiator

Instead of only discovering schemes, the system focuses on the **next mile**:

> **Discover → Verify → Prepare → Apply**

---

## ✨ Features

* 🤖 AI-powered citizen profile extraction
* 🔎 RAG-based government scheme retrieval
* ⚖️ Deterministic eligibility rules engine
* 🎯 Precision-first scheme recommendations
* 🎙️ Voice interaction
* 🌐 English, Hindi & Hinglish
* 📄 Document upload and information extraction
* 📋 Personalized application-readiness checklist
* 💬 Conversational follow-up questions
* 🔗 Official government application links
* 🧠 Explainable recommendations — "Why am I seeing this?"
* 🔄 Real-time recommendation updates when profile information changes

---

## 🧠 AI + RAG Architecture

The LLM is responsible for understanding the user, while deterministic components handle eligibility.

```text
LLM
 ├── Profile Extraction
 ├── Intent Detection
 ├── Query Understanding
 └── Explanation

RAG
 └── Retrieves official scheme information

Rules Engine
 └── Deterministic eligibility evaluation

Document AI
 └── Extracts and verifies information from documents
```

### Recommendation Pipeline

```text
User Input
   ↓
Structured Profile
   ↓
Intent + Concepts
   ↓
Hard Metadata Filtering
   ↓
Vector/RAG Retrieval
   ↓
Eligibility Rules
   ↓
Re-ranking
   ↓
Top Relevant Schemes
```

**Important:** RAG does not override mandatory eligibility rules.

`UNKNOWN` information is not treated as `FAILED`.

---

## 🌐 Multilingual Support

Supported languages:

* English
* Hindi
* Hinglish

Example:

```text
English:
"I am a student and need a scholarship."

Hindi:
"मैं एक छात्र हूँ और मुझे छात्रवृत्ति चाहिए।"

Hinglish:
"Main student hoon aur mujhe scholarship chahiye."
```

All languages are converted into the same language-independent structured profile.

The complete UI also changes language, including:

* Navigation
* Buttons
* Forms
* Scheme cards
* Chat
* Errors
* Checklists
* Document screens

---

## 🎙️ Voice Flow

```text
Voice
 ↓
Speech-to-Text
 ↓
Language Understanding
 ↓
Profile Extraction
 ↓
RAG + Eligibility
 ↓
Response
```

Voice and text use the same backend recommendation pipeline.

---

## 📄 Document Intelligence

Supported workflow:

```text
Upload Document
      ↓
OCR / Extraction
      ↓
Document Classification
      ↓
Structured Information
      ↓
Profile Matching
      ↓
Eligibility Verification
```

The system distinguishes:

```text
USER_REPORTED
DOCUMENT_VERIFIED
UNKNOWN
```

Example:

```text
Income reported: ₹3,00,000
Income on certificate: ₹1,50,000
→ Flag discrepancy
```

---

## 🛠️ Tech Stack

### Frontend

* Next.js
* React
* TypeScript
* Tailwind CSS
* shadcn/ui
* Lucide

### Backend

* Python
* FastAPI

### Data

* PostgreSQL
* Supabase
* pgvector
* Supabase Storage

### AI

* OpenAI API / LLM
* RAG
* Embeddings
* Structured JSON extraction

### Voice & Documents

* Speech-to-Text
* Text-to-Speech
* OCR
* PDF/Image processing

### Deployment

* Vercel
* Render / Railway
* Supabase

---

## 🗄️ Core Data Model

### `profiles`

```text
age
gender
state
district
city
annual_income
occupation
student_status
farmer_status
widow_status
disability_status
senior_citizen_status
education_level
employment_status
family_size
```

### `schemes`

```text
scheme_id
scheme_name
government
ministry
state
category
description
benefits
target_groups
keywords
synonyms
application_url
source_url
last_verified
```

### Other tables

```text
users
eligibility_rules
scheme_documents
user_documents
document_extractions
conversations
messages
application_checklists
```

---

## 🔌 Main API Endpoints

```text
POST /api/agent/query

POST /api/chat

GET  /api/profile
PUT  /api/profile

GET  /api/schemes
GET  /api/schemes/{id}
POST /api/schemes/search
POST /api/schemes/recommend

POST /api/eligibility/check

POST /api/documents/upload
POST /api/documents/analyze
GET  /api/documents

GET  /api/readiness/{scheme_id}
POST /api/application/checklist
```

`/api/agent/query` should orchestrate the complete AI → RAG → eligibility pipeline.

---

## 📊 Eligibility States

Each rule returns:

```text
MATCHED
FAILED
UNKNOWN
```

Overall scheme status:

```text
POTENTIAL_MATCH
NEEDS_MORE_INFORMATION
APPEARS_UNLIKELY
```

These are **assistance indicators**, not official government eligibility decisions.

---

## 🧪 Example

User:

> "Main 22 saal ka student hoon, Lucknow mein rehta hoon aur meri family income 1.5 lakh hai."

System extracts:

```json
{
  "age": 22,
  "student_status": true,
  "state": "Uttar Pradesh",
  "city": "Lucknow",
  "annual_income": 150000
}
```

Then:

```text
Profile
 ↓
Education Intent
 ↓
Student/State Filtering
 ↓
RAG
 ↓
Eligibility Rules
 ↓
Ranking
 ↓
Relevant Schemes
```

Farmer-only or widow-only schemes should not be recommended without supporting evidence.

---

## 📚 Data Sources

The prototype should prioritize official sources:

* [myScheme](https://www.myscheme.gov.in/)
* [myScheme Eligibility Engine](https://rules.myscheme.gov.in/)
* [India.gov.in](https://www.india.gov.in/my-government/schemes)

Each scheme should retain:

```text
source_url
source_name
last_verified
application_url
```

---

# ⚙️ Setup

## 1. Clone

```bash
git clone <repository-url>
cd welfare-navigator
```

## 2. Install Frontend

```bash
npm install
```

## 3. Install Backend

```bash
pip install -r requirements.txt
```

## 4. Environment Variables

Create `.env.local` / `.env` as required by the project.

Example:

```env
OPENAI_API_KEY=your_api_key

NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key

SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

DATABASE_URL=your_database_url
```

Never commit API keys.

## 5. Database

Configure PostgreSQL/Supabase and enable `pgvector` if RAG vector search is being used.

Load the scheme dataset and eligibility rules into the database.

## 6. Run Frontend

```bash
npm run dev
```

## 7. Run Backend

```bash
uvicorn app.main:app --reload
```

The exact backend entry point may vary depending on the repository structure.

---

## 🧪 Testing

Important regression cases:

```text
Student
→ Education schemes

Farmer
→ Agriculture schemes

Widow
→ Relevant women/social-welfare schemes

Senior citizen
→ Pension/senior-citizen schemes

Student + Farmer
→ Both relevant categories

Missing income
→ UNKNOWN + follow-up question

Failed mandatory criterion
→ Not a strong match

Hindi input
→ Hindi understanding + Hindi UI

Hinglish input
→ Hinglish understanding + Hinglish UI
```

Language dropdown must behave as:

```text
Click dropdown
     ↓
Open menu
     ↓
English / हिंदी / Hinglish
     ↓
Select language
     ↓
Update UI
     ↓
Close menu
```

Clicking the dropdown trigger itself must **not** immediately switch languages.

---

## 🔐 Responsible AI

The platform is an assistance tool, not an official government eligibility authority.

It should:

* Ground scheme information in official sources.
* Never invent eligibility criteria.
* Never fabricate application links.
* Never assume missing user information.
* Distinguish user-reported and document-verified data.
* Clearly communicate uncertainty.
* Redirect users to official government application portals.

Use:

> **Potential Match**

instead of:

> **You are definitely eligible**

---

## 🚀 Future Scope

* More Indian languages
* More state-specific schemes
* Larger verified scheme database
* Automated source updates
* Improved document verification
* Accessibility improvements
* More advanced voice interaction
* Government/NGO integrations

---

## 🏆 Project Vision

> **Make government welfare easier to discover, understand, verify, and apply for — regardless of language or technical literacy.**

### Discover → Verify → Prepare → Apply 🇮🇳
