import sqlite3
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "study_doctor.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add default demo user
    c.execute("""
        INSERT OR IGNORE INTO users (username, password, name)
        VALUES ('demo_student', 'demo123', 'Alex Student')
    """)

    # Attempts table
    c.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            percentage REAL NOT NULL,
            topic_scores TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Revision plans table
    c.execute("""
        CREATE TABLE IF NOT EXISTS revision_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            days INTEGER NOT NULL,
            hours_per_day REAL NOT NULL,
            plan_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Persistent Materials Library
    c.execute("""
        CREATE TABLE IF NOT EXISTS material_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            title TEXT NOT NULL,
            syllabus_text TEXT NOT NULL,
            notes_text TEXT NOT NULL,
            past_papers_text TEXT NOT NULL,
            topics_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Persistent Uploaded Documents Table (PDFs, page counts, extraction status)
    c.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            filename TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            text_path TEXT NOT NULL,
            extracted_text TEXT NOT NULL,
            page_count INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            pages_json TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed initial datasets if empty
    c.execute("SELECT COUNT(*) FROM material_library")
    if c.fetchone()[0] == 0:
        try:
            if os.path.exists("sample_data/syllabus.txt") and os.path.exists("sample_data/notes.txt"):
                with open("sample_data/syllabus.txt") as f: s_bio = f.read()
                with open("sample_data/notes.txt") as f: n_bio = f.read()
                p_bio = open("sample_data/past_papers.txt").read() if os.path.exists("sample_data/past_papers.txt") else ""
                c.execute("""
                    INSERT INTO material_library (username, title, syllabus_text, notes_text, past_papers_text, topics_count)
                    VALUES ('demo_student', '🧬 Biology: Cell Energetics & Molecular Genetics', ?, ?, ?, 10)
                """, (s_bio, n_bio, p_bio))
            if os.path.exists("test_upload_files/python_syllabus.txt") and os.path.exists("test_upload_files/python_notes.txt"):
                with open("test_upload_files/python_syllabus.txt") as f: s_py = f.read()
                with open("test_upload_files/python_notes.txt") as f: n_py = f.read()
                p_py = open("test_upload_files/python_past_papers.txt").read() if os.path.exists("test_upload_files/python_past_papers.txt") else ""
                c.execute("""
                    INSERT INTO material_library (username, title, syllabus_text, notes_text, past_papers_text, topics_count)
                    VALUES ('demo_student', '🐍 Python: Core Programming & OOP Guide', ?, ?, ?, 8)
                """, (s_py, n_py, p_py))
        except Exception:
            pass

    conn.commit()
    conn.close()

def save_material_library(username, title, syllabus_text, notes_text, past_papers_text, topics_count=0):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO material_library (username, title, syllabus_text, notes_text, past_papers_text, topics_count)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (username, title, syllabus_text, notes_text, past_papers_text, topics_count))
    conn.commit()
    mat_id = c.lastrowid
    conn.close()
    return mat_id

def get_material_library(username):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM material_library 
        WHERE username = ? OR username = 'demo_student'
        ORDER BY id DESC
    """, (username,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def delete_material_library(material_id, username):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM material_library WHERE id = ? AND (username = ? OR username = 'demo_student')", (material_id, username))
    conn.commit()
    conn.close()

# =========================================================================
# UPLOADED DOCUMENTS MANAGER
# =========================================================================
def save_uploaded_document(username, filename, doc_type, file_path, text_path, extracted_text, page_count, status, file_hash, pages_json="[]"):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO uploaded_documents (
            username, filename, doc_type, file_path, text_path, 
            extracted_text, page_count, status, file_hash, pages_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        username, filename, doc_type, file_path, text_path,
        extracted_text, page_count, status, file_hash, pages_json
    ))
    conn.commit()
    doc_id = c.lastrowid
    conn.close()
    return doc_id

def get_uploaded_documents(username):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM uploaded_documents
        WHERE username = ? OR username = 'demo_student'
        ORDER BY id DESC
    """, (username,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_document_by_id(doc_id, username):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM uploaded_documents
        WHERE id = ? AND (username = ? OR username = 'demo_student')
    """, (doc_id, username))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_uploaded_document(doc_id, username):
    init_db()
    doc = get_document_by_id(doc_id, username)
    if doc:
        # Clean up files from storage if present
        if doc.get("file_path") and os.path.exists(doc["file_path"]):
            try: os.remove(doc["file_path"])
            except Exception: pass
        if doc.get("text_path") and os.path.exists(doc["text_path"]):
            try: os.remove(doc["text_path"])
            except Exception: pass

    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM uploaded_documents WHERE id = ? AND (username = ? OR username = 'demo_student')", (doc_id, username))
    conn.commit()
    conn.close()
    return True

def check_duplicate_document(username, file_hash):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, filename, status FROM uploaded_documents
        WHERE (username = ? OR username = 'demo_student') AND file_hash = ?
        LIMIT 1
    """, (username, file_hash))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def authenticate_user(username, password):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username.strip(), password.strip()))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def register_user(username, password, name):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE username = ?", (username.strip(),))
    if c.fetchone():
        conn.close()
        return False, "Username already exists. Please choose a different one."
    
    c.execute("""
        INSERT INTO users (username, password, name)
        VALUES (?, ?, ?)
    """, (username.strip(), password.strip(), name.strip()))
    conn.commit()
    conn.close()
    return True, "Account created successfully! You can now log in."

def change_password(username, new_password):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET password = ? WHERE username = ?", (new_password.strip(), username.strip()))
    conn.commit()
    conn.close()
    return True, "Password updated successfully!"

def record_attempt(username, score, total_questions, topic_scores):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM attempts WHERE username = ?", (username,))
    count = c.fetchone()[0]
    attempt_num = count + 1
    pct = round((score / total_questions) * 100, 1) if total_questions > 0 else 0.0

    c.execute("""
        INSERT INTO attempts (username, attempt_number, score, total_questions, percentage, topic_scores)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (username, attempt_num, score, total_questions, pct, json.dumps(topic_scores)))
    
    conn.commit()
    attempt_id = c.lastrowid
    conn.close()
    return attempt_num, attempt_id

def get_user_attempts(username):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM attempts WHERE username = ? ORDER BY id ASC", (username,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for r in rows:
        r["topic_scores"] = json.loads(r["topic_scores"])
    return rows

def save_revision_plan(username, days, hours_per_day, plan_data):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO revision_plans (username, days, hours_per_day, plan_json)
        VALUES (?, ?, ?, ?)
    """, (username, days, hours_per_day, json.dumps(plan_data)))
    conn.commit()
    conn.close()

def get_latest_revision_plan(username):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM revision_plans WHERE username = ? ORDER BY id DESC LIMIT 1
    """, (username,))
    row = c.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["plan_data"] = json.loads(d["plan_json"])
        return d
    return None
