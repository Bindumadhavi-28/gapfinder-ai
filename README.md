# GapFinder AI 🎯 (Find What the Student Doesn’t Know)

> **"Students often study everything equally and still miss what they don’t know. GapFinder AI works like a doctor for studying: it tests the student, finds what’s weak, and gives a prioritized revision treatment plan."**

---

## 🌟 Key Features Implemented

1. **Material Ingestion**: Upload Syllabus, Textbook Chapters/Notes, and Past Exam Papers (or load the bundled demo dataset in 1 click).
2. **Topic Map & Exam Weightage**: Extracts topics from the syllabus and links past exam questions to identify high-frequency exam concepts.
3. **Diagnostic Quiz (RAG-Grounded)**: Questions generated strictly from retrieved textbook sections with explicit citations (e.g. `[Textbook Ch. 1 - Section 1.2]`).
4. **The Gap Report (Core Diagnosis Output)**: Sorts topics into 🔴 Weak (<50%), 🟡 Medium (50-75%), and 🟢 Strong (>75%) with clear diagnostic reasons.
5. **Adaptive Revision Plan**: Prioritized using `(Weakness Severity) × (Exam Weightage)` based on the student's available days and daily study hours.
6. **Explain-This-Topic Assistant**: Strict RAG assistant that answers questions solely from uploaded notes and cites sources.
7. **Progress Dashboard**: Tracks score trajectory and topic mastery across quiz attempts using SQLite.
8. **Login & Account Management**: Demo credentials for judges (`demo_student` / `demo123`) plus full student registration and password updates.

---

## 🧠 AI Architecture: Separation of Retrieval vs. Generation

To prevent hallucinations and guarantee educational integrity, the application enforces a strict separation:

| Stage | Mechanism | Purpose |
| :--- | :--- | :--- |
| **1. Retrieval** | TF-IDF / Semantic Cosine Similarity over note chunks | Pulls **only** the factual passages from the student's textbook. |
| **2. Generation** | Google Gemini (with strict refusal prompt) | Formulates clear explanations and questions using **only** the retrieved context, refusing outside internet facts. |
| **3. Grounding & Citations** | Explicit chunk headers `[SOURCE: ...]` | Every question and chat response displays exact chapter & section metadata. |

---

## 🚀 How to Run the App

1. Open your terminal in this project folder:
   ```bash
   streamlit run app.py
   ```
2. Open your browser at the displayed URL (`http://localhost:8501`).
3. In the sidebar:
   - Enter your **Google Gemini API Key** (or leave it blank to run with rich pre-indexed demo questions).
   - Log in using `demo_student` / `demo123` or register a new account.
4. In Tab 1, click **"🚀 Load Pre-Packaged Demo Dataset (Cell Energetics & Genetics)"** to immediately test the complete diagnosis loop!
"# gapfinder-ai" 
