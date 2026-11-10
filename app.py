import streamlit as st
import pandas as pd
import json
import os

from db_manager import (
    init_db, authenticate_user, register_user, change_password,
    record_attempt, get_user_attempts, save_revision_plan, get_latest_revision_plan,
    save_material_library, get_material_library, delete_material_library,
    save_uploaded_document, get_uploaded_documents, get_document_by_id,
    delete_uploaded_document, check_duplicate_document
)
from rag_engine import StudyRAGEngine
from file_extractor import extract_text_from_file, process_and_store_document

def get_active_llm_config():
    """Returns (provider, api_key) based on the user's sidebar selection."""
    provider_choice = st.session_state.get("llm_provider", "Built-in Local RAG (Free / Offline)")
    if "Groq" in provider_choice:
        return "groq", st.session_state.get("groq_api_key", os.getenv("GROQ_API_KEY", ""))
    elif "Gemini" in provider_choice:
        return "gemini", st.session_state.get("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
    return "local", ""

# Initialize database
init_db()

# Auto-load GROQ_API_KEY, GROQ_MODEL, GEMINI_API_KEY from .env if present
if os.path.exists(".env"):
    try:
        with open(".env", "r") as f:
            for line in f:
                l = line.strip()
                if l.startswith("GROQ_API_KEY="):
                    val = l.split("GROQ_API_KEY=", 1)[-1].strip()
                    if val and not os.environ.get("GROQ_API_KEY"):
                        os.environ["GROQ_API_KEY"] = val
                elif l.startswith("GROQ_MODEL="):
                    val = l.split("GROQ_MODEL=", 1)[-1].strip()
                    if val and not os.environ.get("GROQ_MODEL"):
                        os.environ["GROQ_MODEL"] = val
                elif l.startswith("GEMINI_API_KEY="):
                    val = l.split("GEMINI_API_KEY=", 1)[-1].strip()
                    if val and not os.environ.get("GEMINI_API_KEY"):
                        os.environ["GEMINI_API_KEY"] = val
    except Exception:
        pass

# Page Configuration
st.set_page_config(
    page_title="GapFinder AI | Diagnostic Assessment Platform",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom High-End Styling
st.markdown("""
<style>
    /* Global Font and Colors */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .brand-header {
        font-size: 1.85rem;
        font-weight: 700;
        color: #0F172A;
        letter-spacing: -0.02em;
        margin-bottom: 0.15rem;
    }
    .brand-caption {
        font-size: 0.95rem;
        color: #64748B;
        margin-bottom: 1.25rem;
    }
    
    /* Clean Enterprise Cards */
    .metric-card {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px;
        color: #F8FAFC !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    }
    .assessment-card {
        background-color: #1E293B !important;
        border: 1px solid #334155 !important;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 16px;
        color: #F8FAFC !important;
        box-shadow: 0 4px 10px rgba(0,0,0,0.25);
    }
    .assessment-card h4 {
        color: #FFFFFF !important;
        font-size: 1.15rem;
        font-weight: 600;
        margin: 10px 0 6px 0 !important;
    }
    .assessment-card p {
        color: #94A3B8 !important;
        margin-bottom: 8px !important;
        font-size: 0.88rem !important;
    }
    .assessment-card b {
        color: #F1F5F9 !important;
    }
    .assessment-card ul {
        color: #CBD5E1 !important;
        margin-top: 6px;
        padding-left: 20px;
    }
    .assessment-card li {
        color: #CBD5E1 !important;
        margin-bottom: 5px;
        font-size: 0.88rem;
    }
    
    /* Grounding Citation Tag */
    .citation-badge {
        display: inline-block;
        background-color: #0F172A;
        color: #38BDF8;
        border-left: 3px solid #0284C7;
        padding: 6px 12px;
        font-size: 0.82rem;
        font-weight: 500;
        border-radius: 0 6px 6px 0;
        margin: 6px 0 10px 0;
    }
    
    /* Diagnostic Priority Badges */
    .badge-critical {
        background-color: #450A0A !important;
        color: #FCA5A5 !important;
        border: 1px solid #991B1B !important;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.8rem;
        letter-spacing: 0.02em;
    }
    .badge-medium {
        background-color: #451A03 !important;
        color: #FCD34D !important;
        border: 1px solid #92400E !important;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.8rem;
        letter-spacing: 0.02em;
    }
    .badge-mastered {
        background-color: #052E16 !important;
        color: #86EFAC !important;
        border: 1px solid #166534 !important;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.8rem;
        letter-spacing: 0.02em;
    }
    .badge-untested {
        background-color: #1E293B !important;
        color: #94A3B8 !important;
        border: 1px solid #475569 !important;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.8rem;
        letter-spacing: 0.02em;
    }
    
    /* Streamlit Tab Customization */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 42px;
        font-weight: 500;
        font-size: 0.9rem;
        border-radius: 6px 6px 0 0;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- SESSION STATE -----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

if "rag_engine" not in st.session_state:
    st.session_state.rag_engine = StudyRAGEngine()

if "materials_loaded" not in st.session_state:
    st.session_state.materials_loaded = False

if "current_quiz" not in st.session_state:
    st.session_state.current_quiz = None

if "last_results" not in st.session_state:
    st.session_state.last_results = None

if "gap_report" not in st.session_state:
    st.session_state.gap_report = None

if "revision_plan" not in st.session_state:
    st.session_state.revision_plan = None

if "active_title" not in st.session_state:
    st.session_state.active_title = "None"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.markdown("### GapFinder AI")
    st.caption("Targeted Diagnostic Assessment & Adaptive Revision")

    st.markdown("---")

    # LLM Engine Configuration (Local RAG, Groq Llama, or Google Gemini)
    st.markdown("**AI Model Provider**")
    provider_choice = st.selectbox(
        "Engine",
        ["Built-in Local RAG (Free / Offline)", "Groq API + Llama", "Google Gemini"],
        index=0,
        help="Select which AI engine powers quiz generation and grounded explanations."
    )
    st.session_state.llm_provider = provider_choice

    if provider_choice == "Groq API + Llama":
        active_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        groq_key = st.text_input(
            "Groq API Key",
            type="password",
            value=st.session_state.get("groq_api_key", os.getenv("GROQ_API_KEY", "")),
            help="Get your free API key from https://console.groq.com/keys"
        )
        if groq_key:
            st.session_state.groq_api_key = groq_key
            os.environ["GROQ_API_KEY"] = groq_key
        st.caption(f"⚡ Ultra-Fast Llama RAG (`{active_model}`)")

    elif provider_choice == "Google Gemini":
        gemini_key = st.text_input(
            "Google Gemini API Key",
            type="password",
            value=st.session_state.get("gemini_api_key", os.getenv("GEMINI_API_KEY", "")),
            help="Free API key from https://aistudio.google.com/app/apikey"
        )
        if gemini_key:
            st.session_state.gemini_api_key = gemini_key
            os.environ["GEMINI_API_KEY"] = gemini_key
        st.caption("Powered by `gemini-1.5-flash` / `gemini-2.0-flash`")

    else:
        st.caption("⚡ Zero-API Mode: Grounded directly in your uploaded notes with 0 tokens or API keys needed.")

    st.markdown("---")

    # Authentication Panel
    if not st.session_state.logged_in:
        auth_mode = st.radio("Portal Access", ["Sign In", "Create Account"], horizontal=True)

        if auth_mode == "Sign In":
            st.markdown("**Student Sign In**")
            st.caption("Demo: `demo_student` / `demo123`")
            u_in = st.text_input("Username", value="demo_student", key="login_u")
            p_in = st.text_input("Password", type="password", value="demo123", key="login_p")
            if st.button("Sign In", use_container_width=True, type="primary"):
                user = authenticate_user(u_in, p_in)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
        else:
            st.markdown("**New Student Registration**")
            new_name = st.text_input("Full Name", key="reg_name")
            new_user = st.text_input("Choose Username", key="reg_u")
            new_pass = st.text_input("Choose Password", type="password", key="reg_p")
            if st.button("Create Account", use_container_width=True, type="primary"):
                if not new_name or not new_user or not new_pass:
                    st.error("All fields are required.")
                else:
                    ok, msg = register_user(new_user, new_pass, new_name)
                    if ok:
                        user = authenticate_user(new_user, new_pass)
                        st.session_state.logged_in = True
                        st.session_state.user = user
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        name_display = st.session_state.user.get("name", "Student") if isinstance(st.session_state.user, dict) else "Student"
        user_display = st.session_state.user.get("username", "demo_student") if isinstance(st.session_state.user, dict) else "demo_student"
        st.markdown(f"**{name_display}**")
        st.caption(f"Account: `{user_display}`")

        with st.expander("Account Settings"):
            new_p = st.text_input("Update Password", type="password", key="chg_p")
            if st.button("Save New Password"):
                if new_p:
                    change_password(user_display, new_p)
                    st.success("Password updated.")
                else:
                    st.warning("Enter a valid password.")

        if st.button("Log Out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()


# ----------------- MAIN VIEW (UNAUTHENTICATED) -----------------
if not st.session_state.logged_in:
    st.markdown("<div class='brand-header'>GapFinder AI</div>", unsafe_allow_html=True)
    st.markdown("<div class='brand-caption'>Diagnostic Assessment Engine — Find what you don't know and build a targeted revision plan.</div>", unsafe_allow_html=True)

    col1, col2 = st.columns([1.6, 1])
    with col1:
        st.markdown("""
        #### Systematic Diagnostic Revision
        Traditional exam preparation often leads students to re-read materials they have already mastered while overlooking critical knowledge gaps.
        
        **How GapFinder AI Works:**
        1. **Ingest Syllabus & Materials:** Maps core topics and evaluates past exam frequency.
        2. **Diagnostic Assessment:** Generates grounded test questions cited directly from your textbooks.
        3. **Clinical Gap Report:** Classifies topics into Weak, Medium, and Strong with specific diagnostic rationale.
        4. **Adaptive Revision Plan:** Dynamically budgets available study time based on weakness severity and exam weightage.
        """)
        st.info("Please sign in or use the demo credentials in the sidebar to access the platform.")
    with col2:
        st.image("https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&w=600&q=80", caption="Targeted, Evidence-Grounded Learning")
    st.stop()


# ----------------- APPLICATION DASHBOARD -----------------
student_display_name = st.session_state.user.get('name', 'Student') if isinstance(st.session_state.user, dict) else 'Student'
st.markdown("<div class='brand-header'>GapFinder AI Dashboard</div>", unsafe_allow_html=True)
st.caption(f"Student: **{student_display_name}** | Active Diagnostic Session")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Materials & Library",
    "Syllabus Map",
    "Diagnostic Quiz",
    "Gap Diagnosis Report",
    "Revision Roadmap",
    "Grounded Assistant",
    "Performance Tracker"
])


# =========================================================================
# TAB 1: MATERIALS & LIBRARY
# =========================================================================
with tab1:
    st.subheader("Course Materials & Ingestion Pipeline")
    st.caption("Upload your syllabus, notes, and past exams to extract text with `pdfjs-dist` and build your diagnostic RAG index.")

    active_user = st.session_state.user.get("username", "demo_student") if isinstance(st.session_state.user, dict) else "demo_student"

    # Active Session Status Banner
    if st.session_state.materials_loaded:
        st.markdown(f"""
        <div style='background-color: #F0FDF4; border: 1px solid #86EFAC; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px;'>
            <span style='color: #15803D; font-weight: 700; font-size: 1.05rem;'>🟢 Active RAG Session: {st.session_state.active_title}</span>
            <div style='color: #374151; font-size: 0.88rem; margin-top: 4px;'>
                <b>{len(st.session_state.rag_engine.topics)}</b> Syllabus Topics Mapped &nbsp;|&nbsp; 
                <b>{len(st.session_state.rag_engine.chunks)}</b> Grounded Chunks with PDF Page Citations &nbsp;|&nbsp; Ready for Diagnostic Quiz
            </div>
        </div>
        """, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # STEP 1: UPLOAD COURSE FILES (Clear 3-Box Layout)
    # -------------------------------------------------------------------------
    st.markdown("#### 1. Upload Course Documents")
    st.caption("Upload your course files. `pdfjs-dist` extracts text page-by-page, preserving page numbers for exact source citations.")

    col_u1, col_u2, col_u3 = st.columns(3)
    with col_u1:
        st.markdown("**📘 1. Syllabus Document**")
        st.caption("Defines exam units and core topics")
        up_syl = st.file_uploader("Syllabus (.pdf, .txt, .md)", type=["pdf", "txt", "md"], key="up_syl_single")
    with col_u2:
        st.markdown("**📚 2. Notes & Chapters**")
        st.caption("Course content to test (Multiple allowed)")
        up_notes = st.file_uploader("Study Notes (.pdf, .txt, .md)", type=["pdf", "txt", "md"], accept_multiple_files=True, key="up_notes_multi")
    with col_u3:
        st.markdown("**📝 3. Past Papers (Optional)**")
        st.caption("Maps question frequency and marks")
        up_past = st.file_uploader("Past Exam Papers (.pdf, .txt, .md)", type=["pdf", "txt", "md"], key="up_past_single")

    col_c1, col_c2 = st.columns([2, 1])
    with col_c1:
        course_name_in = st.text_input("Course Name / Topic Title", placeholder="e.g. Machine Learning, Operating Systems, Chemistry", key="course_name_input")
    with col_c2:
        st.write("")
        st.write("")
        btn_ingest = st.button("🚀 Process & Ingest Course (pdfjs-dist)", type="primary", use_container_width=True)

    if btn_ingest:
        if not up_syl and not up_notes:
            st.error("Please provide at least a Syllabus document and one Notes file.")
        else:
            with st.spinner("Extracting text with pdfjs-dist and saving to persistent storage..."):
                processed_docs = []
                c_title = course_name_in.strip() if course_name_in.strip() else (up_notes[0].name if up_notes else "Course Material")

                # 1. Process Syllabus
                if up_syl:
                    res_s = process_and_store_document(up_syl, active_user, doc_type="Syllabus")
                    processed_docs.append(res_s)

                # 2. Process Notes (Multiple)
                if up_notes:
                    for n_file in up_notes:
                        res_n = process_and_store_document(n_file, active_user, doc_type="Study Notes")
                        processed_docs.append(res_n)

                # 3. Process Past Papers
                if up_past:
                    res_p = process_and_store_document(up_past, active_user, doc_type="Previous Question Paper")
                    processed_docs.append(res_p)

                # Fetch all valid stored documents for this user and activate in RAG
                all_user_docs = get_uploaded_documents(active_user)
                valid_docs = [d for d in all_user_docs if d["status"] == "Success"]

                if valid_docs:
                    st.session_state.rag_engine.ingest_from_documents(valid_docs, title=c_title)
                    st.session_state.materials_loaded = True
                    st.session_state.active_title = c_title
                    st.session_state.current_quiz = None
                    st.session_state.gap_report = None
                    st.session_state.revision_plan = None
                    st.success(f"✅ Ingestion Complete! Indexed {len(valid_docs)} documents into active RAG session with page citations.")
                else:
                    st.warning("Uploaded files were saved, but no text layer was found. Documents may require OCR.")

                st.rerun()

    # -------------------------------------------------------------------------
    # ALTERNATIVE INPUT OPTIONS (Clean Expanders)
    # -------------------------------------------------------------------------
    with st.expander("✍️ Alternative: Paste Notes Directly as Plain Text"):
        st.caption("Great for scanned notes, lecture slides, Notion pages, or fast setup without saving files.")
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            paste_title = st.text_input("Course Title", placeholder="e.g. Machine Learning Fundamentals", key="p_title")
            paste_syl = st.text_area("Syllabus Topics", placeholder="UNIT 1: Linear Regression\nUNIT 2: Neural Networks", height=120, key="p_syl")
        with p_col2:
            paste_not = st.text_area("Notes Content", placeholder="[SOURCE: Ch 1 - Regression] Linear regression models continuous targets...\n[SOURCE: Ch 2 - Neural Nets] Backpropagation calculates gradients...", height=120, key="p_not")
            paste_pas = st.text_area("Past Questions & Marks (Optional)", placeholder="Explain backpropagation (5 Marks)", height=60, key="p_pas")

        if st.button("Index Pasted Notes", type="primary", use_container_width=True, key="btn_paste_direct"):
            if paste_syl.strip() and paste_not.strip():
                with st.spinner("Indexing content..."):
                    t_save = paste_title.strip() if paste_title.strip() else "Custom Study Notes"
                    st.session_state.rag_engine.ingest_materials(paste_syl, paste_not, paste_pas, title=t_save)
                    st.session_state.materials_loaded = True
                    st.session_state.active_title = t_save
                    st.session_state.current_quiz = None
                    st.session_state.gap_report = None
                    st.session_state.revision_plan = None
                    save_material_library(active_user, t_save, paste_syl, paste_not, paste_pas, len(st.session_state.rag_engine.topics))
                    st.success(f"Indexed and saved '{t_save}'!")
                    st.rerun()
            else:
                st.error("Please provide both Syllabus and Notes text.")

    with st.expander("📦 Alternative: 1-Click Pre-seeded Demo Courses (Biology & Python)"):
        st.caption("Instantly test the full diagnostic quiz, gap report, and revision plan with verified curricula.")
        saved_sets = get_material_library(active_user)
        if saved_sets:
            for item in saved_sets:
                is_active = st.session_state.materials_loaded and (st.session_state.active_title == item["title"])
                c_card1, c_card2, c_card3 = st.columns([3, 1.2, 0.8])
                with c_card1:
                    badge = "<span class='badge-mastered' style='margin-left: 8px;'>ACTIVE</span>" if is_active else ""
                    st.markdown(f"**{item['title']}** {badge}", unsafe_allow_html=True)
                    st.caption(f"{item['topics_count']} topics | Saved: {item['created_at'][:10]}")
                with c_card2:
                    btn_lbl = "⚡ Loaded" if is_active else "⚡ Load Course"
                    if st.button(btn_lbl, key=f"load_mat_{item['id']}", use_container_width=True, disabled=is_active):
                        st.session_state.rag_engine.ingest_materials(item["syllabus_text"], item["notes_text"], item["past_papers_text"], title=item["title"])
                        st.session_state.materials_loaded = True
                        st.session_state.active_title = item["title"]
                        st.session_state.current_quiz = None
                        st.session_state.gap_report = None
                        st.session_state.revision_plan = None
                        st.rerun()
                with c_card3:
                    if st.button("🗑️ Delete", key=f"del_mat_{item['id']}", use_container_width=True):
                        delete_material_library(item["id"], active_user)
                        st.rerun()
                st.markdown("<hr style='margin: 4px 0;'>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # STEP 2: MATERIALS REPOSITORY (Stored PDFs & Extracted Text)
    # -------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### 2. Materials Repository (Stored Documents & Extraction Status)")
    st.caption("Persistent files saved in project storage (`storage/pdfs/` and `storage/texts/`) and recorded in database.")

    user_docs = get_uploaded_documents(active_user)

    if user_docs:
        valid_docs = [d for d in user_docs if d["status"] == "Success"]

        c_top1, c_top2 = st.columns([2.5, 1.5])
        with c_top1:
            st.markdown(f"**Storage Summary:** {len(user_docs)} files stored ({len(valid_docs)} extracted with `pdfjs-dist`).")
        with c_top2:
            if st.button("⚡ Re-index All Documents in Active Session", use_container_width=True, disabled=(len(valid_docs) == 0)):
                with st.spinner("Re-building index with page citations..."):
                    st.session_state.rag_engine.ingest_from_documents(valid_docs, title=f"Stored Bundle ({len(valid_docs)} Docs)")
                    st.session_state.materials_loaded = True
                    st.session_state.active_title = f"Stored Bundle ({len(valid_docs)} Docs)"
                    st.session_state.current_quiz = None
                    st.session_state.gap_report = None
                    st.session_state.revision_plan = None
                    st.success("Re-indexed all documents successfully!")
                    st.rerun()

        # Clean document cards
        for doc in user_docs:
            with st.container():
                c_info, c_action = st.columns([3.5, 1])
                with c_info:
                    st_badge = "<span class='badge-mastered'>✅ Extracted (pdfjs-dist)</span>" if doc["status"] == "Success" else "<span class='badge-critical'>⚠️ OCR Required</span>"
                    cat_badge = f"<span class='badge-medium'>{doc['doc_type']}</span>"
                    st.markdown(f"📄 **{doc['filename']}** &nbsp; {cat_badge} &nbsp; {st_badge}", unsafe_allow_html=True)
                    st.caption(f"Pages: **{doc['page_count']}** | Uploaded: {doc['created_at'][:16]} | Storage: `{doc['file_path']}`")

                with c_action:
                    if st.button("🗑️ Delete File", key=f"del_doc_{doc['id']}", use_container_width=True):
                        delete_uploaded_document(doc["id"], active_user)
                        st.rerun()

                # View text expander (Full Width)
                with st.expander(f"👁️ View Extracted Text ({doc['page_count']} pages)"):
                    if doc["status"] == "Success":
                        st.caption(f"Saved Text Record: `{doc['text_path']}`")
                        st.text_area("Extracted Content", value=doc["extracted_text"][:3000], height=200, key=f"view_txt_{doc['id']}", disabled=True)
                    else:
                        st.warning("⚠️ No digital text layer found in this PDF. It appears to be a scanned image or photo of handwritten notes. OCR is required.")

                st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)
    else:
        st.info("No documents stored yet. Upload your Syllabus and Notes above to start.")


# =========================================================================
# TAB 2: SYLLABUS MAP & EXAM WEIGHTAGE
# =========================================================================
with tab2:
    st.subheader("Syllabus Structure & Exam Weightage")
    st.write("Syllabus topics parsed and mapped against past exam papers to calculate high-frequency exam focus areas.")

    if not st.session_state.materials_loaded:
        st.warning("Please load or ingest materials in Tab 1 first.")
    else:
        topics = st.session_state.rag_engine.topics
        weightage = st.session_state.rag_engine.topic_weightage

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Identified Topics", len(topics))
        total_marks = sum(v["total_marks"] for v in weightage.values())
        if total_marks > 0:
            col_m2.metric("Total Exam Marks", f"{total_marks} pts")
            top_topic = max(weightage.items(), key=lambda x: x[1]["total_marks"])[0] if weightage else "N/A"
            top_disp = (top_topic[:32] + "...") if len(top_topic) > 35 else top_topic
            col_m3.metric("Highest Weight Topic", top_disp)
        else:
            col_m2.metric("Total Exam Marks", "Evenly Distributed")
            col_m3.metric("Highest Weight Topic", "All Topics Equal Priority")

        table_data = []
        for t in topics:
            t_name = t["name"]
            w_info = weightage.get(t_name, {"count": 0, "total_marks": 0, "percentage": 0, "questions": []})
            table_data.append({
                "Unit / Chapter": t["unit"],
                "Topic": t_name,
                "Past Questions": w_info["count"],
                "Exam Weight (%)": w_info["percentage"]
            })

        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True)

        st.markdown("##### Exam Weight Distribution")
        st.bar_chart(df.set_index("Topic")["Exam Weight (%)"], use_container_width=True)


# =========================================================================
# TAB 3: DIAGNOSTIC QUIZ
# =========================================================================
with tab3:
    st.subheader("Diagnostic Assessment")
    st.write("Test your knowledge with questions grounded strictly in the retrieved textbook material.")

    if not st.session_state.materials_loaded:
        st.warning("Please load or ingest materials in Tab 1 first.")
    else:
        if st.session_state.current_quiz is None:
            if st.button("Generate Diagnostic Quiz", type="primary", use_container_width=True):
                with st.spinner("Formulating grounded questions from notes..."):
                    prov, key = get_active_llm_config()
                    quiz = st.session_state.rag_engine.generate_quiz(api_key=key, provider=prov)
                    st.session_state.current_quiz = quiz
                    st.rerun()
            else:
                st.info("Click above to generate a new grounded diagnostic quiz tailored to your notes.")
        else:
            with st.form("quiz_form"):
                user_answers = {}
                for idx, q in enumerate(st.session_state.current_quiz, 1):
                    st.markdown(f"**Question {idx}: [{q['topic']}]**")
                    st.write(q['question'])
                    st.markdown(f"<div class='citation-badge'>Source Citation: {q.get('citation', 'Course Notes')}</div>", unsafe_allow_html=True)

                    selected = st.radio(
                        f"Select your answer for Q{idx}:",
                        options=q["options"],
                        key=f"q_{q['id']}",
                        index=None,
                        label_visibility="collapsed"
                    )
                    user_answers[str(q["id"])] = selected
                    st.markdown("---")

                submitted = st.form_submit_button("Submit Assessment & Generate Diagnosis", type="primary", use_container_width=True)

                if submitted:
                    with st.spinner("Evaluating performance and generating diagnostic report..."):
                        prov, key = get_active_llm_config()
                        results, topic_scores = st.session_state.rag_engine.evaluate_answers(
                            user_answers, st.session_state.current_quiz, api_key=key
                        )
                        st.session_state.last_results = results

                        gap_report = st.session_state.rag_engine.generate_gap_report(topic_scores, api_key=key, provider=prov)
                        st.session_state.gap_report = gap_report

                        rev_plan = st.session_state.rag_engine.generate_revision_plan(gap_report, days=5, hours_per_day=2.0, api_key=key, provider=prov)
                        st.session_state.revision_plan = rev_plan

                        score = sum(1 for r in results if r["is_correct"])
                        total = len(results)
                        active_user = st.session_state.user.get("username", "demo_student") if isinstance(st.session_state.user, dict) else "demo_student"
                        att_num, _ = record_attempt(
                            active_user,
                            score,
                            total,
                            topic_scores
                        )
                        st.success(f"Assessment complete. Attempt #{att_num} recorded. View Tab 4 for your Gap Report.")
                        st.rerun()

            c_rst1, c_rst2 = st.columns(2)
            with c_rst1:
                if st.button("🔄 Next Quiz (Generate Brand New Questions)", use_container_width=True, type="secondary"):
                    with st.spinner("Generating fresh grounded questions..."):
                        prov, key = get_active_llm_config()
                        st.session_state.current_quiz = st.session_state.rag_engine.generate_quiz(api_key=key, provider=prov)
                        st.session_state.last_results = None
                        st.rerun()
            with c_rst2:
                if st.button("Reset Assessment", use_container_width=True):
                    st.session_state.current_quiz = None
                    st.session_state.last_results = None
                    st.session_state.gap_report = None
                    st.session_state.revision_plan = None
                    st.rerun()


# =========================================================================
# TAB 4: GAP DIAGNOSIS REPORT (CORE OUTPUT)
# =========================================================================
with tab4:
    st.subheader("Diagnostic Knowledge Gap Report")
    st.caption("Main output: Clinical diagnosis of student understanding, categorized by priority and exam impact.")

    if not st.session_state.gap_report:
        st.warning("No assessment completed yet. Please complete the diagnostic quiz in Tab 3.")
    else:
        rep = st.session_state.gap_report

        pct = rep.get("overall_percentage", 0)
        c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
        c_kpi1.metric("Overall Mastery", f"{pct}%")
        c_kpi2.metric("Critical Gaps (Weak)", len(rep["weak"]))
        c_kpi3.metric("Mastered Concepts", len(rep["strong"]))

        st.markdown(f"**Diagnostic Summary:** *{rep.get('summary', '')}*")
        st.markdown("---")

        # Weak Areas
        st.markdown("#### Critical Knowledge Gaps (High Priority)")
        if rep["weak"]:
            for item in rep["weak"]:
                st.markdown(f"""
                <div class='assessment-card'>
                    <span class='badge-critical'>Critical Gap</span>
                    <h4>{item['topic']}</h4>
                    <p>Accuracy: <b>{item['accuracy']}%</b> | Exam Weightage: <b>{item['exam_weightage']}%</b></p>
                    <p style='color: #E2E8F0; margin-bottom: 0;'><b>Diagnostic Finding:</b> {item['diagnosis']}</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No critical knowledge gaps detected in this assessment cycle.")

        # Medium Areas
        st.markdown("#### Developing Understanding (Consolidation Needed)")
        if rep["medium"]:
            for item in rep["medium"]:
                st.markdown(f"""
                <div class='assessment-card'>
                    <span class='badge-medium'>Moderate Focus</span>
                    <h4>{item['topic']}</h4>
                    <p>Accuracy: <b>{item['accuracy']}%</b> | Exam Weightage: <b>{item['exam_weightage']}%</b></p>
                    <p style='color: #E2E8F0; margin-bottom: 0;'><b>Diagnostic Finding:</b> {item['diagnosis']}</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No topics in the medium range.")

        # Strong Areas
        st.markdown("#### Mastered Concepts (Exam Ready)")
        if rep["strong"]:
            for item in rep["strong"]:
                st.markdown(f"""
                <div class='assessment-card'>
                    <span class='badge-mastered'>Mastered</span>
                    <h4>{item['topic']}</h4>
                    <p>Accuracy: <b>{item['accuracy']}%</b> | Exam Weightage: <b>{item['exam_weightage']}%</b></p>
                    <p style='color: #E2E8F0; margin-bottom: 0;'><b>Diagnostic Finding:</b> {item['diagnosis']}</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No topics reached full mastery yet.")

        # Question Breakdown
        if st.session_state.last_results:
            with st.expander("Question-Level Performance Audit & Citations"):
                for res in st.session_state.last_results:
                    status_text = "Correct" if res["is_correct"] else "Incorrect"
                    badge_class = "badge-mastered" if res["is_correct"] else "badge-critical"
                    st.markdown(f"<span class='{badge_class}'>{status_text}</span> &nbsp; <b>{res['question']}</b>", unsafe_allow_html=True)
                    st.markdown(f"- Your Answer: `{res['user_answer'] or 'Unanswered'}`")
                    st.markdown(f"- Ground Truth: `{res['correct_answer']}`")
                    st.markdown(f"- Rationale: {res['explanation']}")
                    st.markdown(f"<div class='citation-badge'>Source: {res['citation']}</div>", unsafe_allow_html=True)
                    st.write("")


# =========================================================================
# TAB 5: REVISION ROADMAP
# =========================================================================
with tab5:
    st.subheader("Targeted Revision Roadmap")
    st.write("Dynamic study schedule prioritized using: `Priority Score = (Weakness Severity) × (Exam Weightage)`.")

    if not st.session_state.gap_report:
        st.warning("Please complete the diagnostic quiz in Tab 3 to generate a revision plan.")
    else:
        st.markdown("##### Study Availability Parameters")
        c_p1, c_p2, c_p3 = st.columns(3)
        with c_p1:
            days = st.slider("Days Until Examination", min_value=1, max_value=14, value=5)
        with c_p2:
            hours = st.slider("Available Daily Hours", min_value=0.5, max_value=8.0, value=2.0, step=0.5)
        with c_p3:
            st.metric("Total Revision Budget", f"{round(days * hours, 1)} Hours")

        if st.button("Regenerate Customized Schedule", type="primary"):
            prov, key = get_active_llm_config()
            st.session_state.revision_plan = st.session_state.rag_engine.generate_revision_plan(
                st.session_state.gap_report, days=days, hours_per_day=hours, api_key=key, provider=prov
            )
            active_user = st.session_state.user.get("username", "demo_student") if isinstance(st.session_state.user, dict) else "demo_student"
            save_revision_plan(
                active_user,
                days,
                hours,
                st.session_state.revision_plan
            )
            st.success("Revision plan updated.")

        plan = st.session_state.revision_plan
        if plan:
            st.markdown("---")
            for day_info in plan["schedule"]:
                st.markdown(f"##### {day_info['day']} — {day_info['total_hours']} Hours Allocated")
                for session in day_info["sessions"]:
                    if "Weak" in session["badge"]:
                        badge_style = "badge-critical"
                    elif "Medium" in session["badge"]:
                        badge_style = "badge-medium"
                    elif "Untested" in session["badge"]:
                        badge_style = "badge-untested"
                    else:
                        badge_style = "badge-mastered"

                    st.markdown(f"""
                    <div class='assessment-card'>
                        <span class='{badge_style}'>{session['badge']}</span>
                        <h4>{session['topic']}</h4>
                        <p>
                            Allocated Study Time: <b>{session['allocated_hours']} hrs</b> &nbsp;|&nbsp; 
                            Exam Weight: <b>{session['exam_weight']}%</b> &nbsp;|&nbsp; 
                            Priority Index: <b>{session['priority_score']}</b>
                        </p>
                        <b>Action Plan:</b>
                        <ul>
                            {''.join([f"<li>{task}</li>" for task in session['tasks']])}
                        </ul>
                    </div>
                    """, unsafe_allow_html=True)


# =========================================================================
# TAB 6: GROUNDED ASSISTANT
# =========================================================================
with tab6:
    st.subheader("Grounded Explain-This-Topic Assistant")
    st.write("Ask targeted questions about your syllabus. The assistant responds strictly using verified excerpts from your uploaded notes.")

    with st.expander("AI Grounding Architecture"):
        st.markdown("""
        - **Retrieval:** Semantic and TF-IDF matching retrieves only factual chunks from uploaded notes.
        - **Generation:** Context is constrained to prevent hallucinations and reflect solely textbook content.
        - **Citations:** Every explanation includes verifiable section references.
        """)

    if not st.session_state.materials_loaded:
        st.warning("Please load or ingest materials in Tab 1 first.")
    else:
        st.markdown("**Quick Inquiries from Active Syllabus:**")
        cols = st.columns(4)
        active_topics = [t["name"] for t in st.session_state.rag_engine.topics[:4]]
        for idx, q_top in enumerate(active_topics):
            with cols[idx]:
                if st.button(q_top, key=f"quick_top_{idx}"):
                    st.session_state.selected_quick = q_top

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        user_query = st.chat_input("Ask a question regarding active course concepts...")

        if "selected_quick" in st.session_state and st.session_state.selected_quick:
            user_query = f"Explain {st.session_state.selected_quick} and its core mechanisms"
            st.session_state.selected_quick = None

        if user_query:
            st.session_state.chat_history.append({"role": "user", "content": user_query})
            with st.spinner("Retrieving notes and drafting explanation..."):
                prov, key = get_active_llm_config()
                response_data = st.session_state.rag_engine.explain_topic(user_query, api_key=key, provider=prov)
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": response_data["answer"],
                    "citations": response_data["citations"],
                    "context": response_data["retrieved_context"]
                })

        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.write(msg["content"])
            else:
                with st.chat_message("assistant"):
                    st.write(msg["content"])
                    if "citations" in msg and msg["citations"]:
                        st.markdown("<div class='citation-badge'>Verified Citation: " + ", ".join(msg["citations"]) + "</div>", unsafe_allow_html=True)
                    if "context" in msg and msg["context"]:
                        with st.expander("Source Notes Text"):
                            st.code(msg["context"])


# =========================================================================
# TAB 7: PERFORMANCE TRACKER
# =========================================================================
with tab7:
    st.subheader("Student Longitudinal Performance Tracker")
    st.write("Track test attempts and monitor how topic-level mastery progresses over successive revision cycles.")

    active_user = st.session_state.user.get("username", "demo_student") if isinstance(st.session_state.user, dict) else "demo_student"
    attempts = get_user_attempts(active_user)

    if not attempts:
        st.info("No assessment records found. Complete a diagnostic quiz in Tab 3 to initiate progress tracking.")
    else:
        c_tr1, c_tr2, c_tr3 = st.columns(3)
        c_tr1.metric("Assessments Completed", len(attempts))
        latest_pct = attempts[-1]["percentage"]
        c_tr2.metric("Latest Assessment Score", f"{latest_pct}%")

        if len(attempts) > 1:
            diff = round(attempts[-1]["percentage"] - attempts[0]["percentage"], 1)
            c_tr3.metric("Mastery Progression", f"{'+' if diff >= 0 else ''}{diff}%")
        else:
            c_tr3.metric("Mastery Progression", "Initial Baseline Established")

        att_df = pd.DataFrame([
            {
                "Assessment": f"Attempt {a['attempt_number']}",
                "Score (%)": a["percentage"],
                "Timestamp": a["created_at"][:16]
            }
            for a in attempts
        ])

        st.markdown("##### Mastery Trajectory Across Attempts")
        st.line_chart(att_df.set_index("Assessment")["Score (%)"], use_container_width=True)

        st.markdown("##### Assessment History Log")
        st.dataframe(att_df, use_container_width=True)
