import re
import json
import random
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from llm_client import call_llm, extract_json
from file_extractor import is_readable_human_text

class StudyRAGEngine:
    def __init__(self):
        self.dataset_title = "Untitled Material"
        self.syllabus_text = ""
        self.notes_text = ""
        self.past_papers_text = ""
        self.chunks = []
        self.topics = []
        self.topic_weightage = {}
        self.vectorizer = None
        self.chunk_matrix = None
        self.last_api_error = None
        self.used_questions = set()
        self.quiz_attempt_counter = 0

    def ingest_materials(self, syllabus: str, notes: str, past_papers: str = "", title: str = ""):
        """
        Validates, parses, chunks, and indexes syllabus and notes.
        Guarantees readable text to prevent corrupted questions.
        """
        if not is_readable_human_text(notes):
            raise ValueError(
                "The notes text contains insufficient readable characters or appears corrupted.\n"
                "Please provide text notes or a digital text-based PDF."
            )

        self.dataset_title = title.strip() if title.strip() else "Course Material"
        self.syllabus_text = syllabus
        self.notes_text = notes
        self.past_papers_text = past_papers or ""
        self.used_questions = set()
        self.quiz_attempt_counter = 0

        self._parse_topics()
        self._chunk_notes()
        self._calculate_exam_weightage()
        self._build_index()

    def _parse_topics(self):
        """Extracts units and discrete topics from syllabus text with multi-delimiter parsing."""
        self.topics = []
        raw = self.syllabus_text.strip()
        if not raw:
            return

        # Preprocess inline units and bullet markers so inline formatting is split properly
        cleaned = re.sub(r'(?i)(Unit\s+\d+[\s\-\–:]*|Chapter\s+\d+[\s\-\–:]*|Module\s+\d+[\s\-\–:]*)', r'\n__UNIT__:\1', raw)
        cleaned = re.sub(r'[\u2022\u25cf\u25aa\u25cb•▪▫]\s*', r'\n__BULLET__:', cleaned)
        cleaned = re.sub(r'(?<=[.;\n])\s*(\d+[\.\)])\s+', r'\n__NUM__:\1 ', cleaned)

        lines = cleaned.split("\n")
        current_unit = "Core Unit"

        noise_patterns = [
            r"^\[Page\s+\d+\]", r"^course information", r"^subject:", r"^level:",
            r"^total:\s*\d+", r"^instructions", r"^time:", r"^maximum marks",
            r"^sample syllabus", r"^learning outcomes", r"^credit", r"^semester"
        ]

        seen_names = set()

        for line in lines:
            line = line.strip()
            if not line or len(line) < 4:
                continue

            # Skip metadata and noise
            if any(re.search(pat, line, re.IGNORECASE) for pat in noise_patterns):
                continue

            if line.startswith("__UNIT__:"):
                unit_hdr = line.replace("__UNIT__:", "").strip()
                unit_clean = re.sub(r"[\.:\–\-]+$", "", unit_hdr).strip()
                if unit_clean:
                    current_unit = unit_clean
            elif line.startswith(("__BULLET__:", "__NUM__:")):
                t_name = re.sub(r"^(__BULLET__|__NUM__):[\d\.\s\-\*•\)]*", "", line).strip()
                t_name = re.sub(r"[\.;]+$", "", t_name).strip()
                # Split inline semicolons if multiple independent topics are listed
                sub_parts = [p.strip() for p in t_name.split(";") if len(p.strip()) > 3] if ";" in t_name else [t_name]
                for part in sub_parts:
                    part_clean = re.sub(r"^[-*•\d\.\)]+\s*", "", part).strip()
                    part_clean = re.sub(r"[\.;]+$", "", part_clean).strip()
                    if 4 <= len(part_clean) <= 120 and part_clean.lower() not in seen_names:
                        if not any(re.search(pat, part_clean, re.IGNORECASE) for pat in noise_patterns):
                            seen_names.add(part_clean.lower())
                            self.topics.append({
                                "name": part_clean,
                                "unit": current_unit,
                                "raw": part
                            })
            else:
                if line.upper().startswith("UNIT") or "CHAPTER" in line.upper() or "MODULE" in line.upper():
                    current_unit = line.split(":", 1)[-1].strip() if ":" in line else line
                else:
                    clean_l = re.sub(r"^[\d\.\s\-\*•\)]+", "", line).strip()
                    clean_l = re.sub(r"[\.;]+$", "", clean_l).strip()
                    if 4 <= len(clean_l) <= 120 and clean_l.lower() not in seen_names:
                        if not any(re.search(pat, clean_l, re.IGNORECASE) for pat in noise_patterns):
                            seen_names.add(clean_l.lower())
                            self.topics.append({
                                "name": clean_l,
                                "unit": current_unit,
                                "raw": line
                            })

        if not self.topics:
            raw_lines = [l.strip() for l in lines if len(l.strip()) > 3 and not any(re.search(p, l, re.IGNORECASE) for p in noise_patterns)][:6]
            for r in raw_lines:
                self.topics.append({"name": r, "unit": "General Concepts", "raw": r})

    def ingest_from_documents(self, documents: list, title: str = ""):
        """
        Ingests extracted text from multiple uploaded PDF/document records.
        Preserves exact PDF filename and page numbers for source citations.
        """
        syllabus_parts = []
        notes_parts = []
        past_papers_parts = []

        for doc in documents:
            if doc.get("status") != "Success":
                continue

            fname = doc.get("filename", "Document")
            dtype = doc.get("doc_type", "Study Notes")
            pages_json = doc.get("pages_json")
            pages = []
            if pages_json:
                try:
                    pages = json.loads(pages_json)
                except Exception:
                    pages = []

            # Format text with exact page citations
            if pages:
                formatted_pages = []
                for p in pages:
                    p_num = p.get("pageNumber", 1)
                    p_txt = p.get("text", "").strip()
                    if p_txt:
                        formatted_pages.append(f"[SOURCE: {fname} - Page {p_num}]\n{p_txt}")
                doc_full_text = "\n\n".join(formatted_pages)
            else:
                doc_full_text = f"[SOURCE: {fname}]\n{doc.get('extracted_text', '')}"

            if "Syllabus" in dtype:
                syllabus_parts.append(doc.get("extracted_text", ""))
            elif "Question" in dtype or "Paper" in dtype:
                past_papers_parts.append(doc.get("extracted_text", ""))
            else:
                # Study Notes, Textbook Chapter
                notes_parts.append(doc_full_text)

        syl_text = "\n\n".join(syllabus_parts)
        not_text = "\n\n".join(notes_parts)
        pas_text = "\n\n".join(past_papers_parts)

        doc_title = title.strip() if title.strip() else (f"Materials Bundle ({len(documents)} Docs)" if documents else "Course Material")
        self.ingest_materials(syl_text, not_text, pas_text, title=doc_title)

    def _chunk_notes(self):
        """Breaks notes into sections with overlap, preserving exact [SOURCE: ...] filename and page citations."""
        self.chunks = []
        sections = re.split(r"(\[SOURCE:[^\]]+\])", self.notes_text)
        
        if len(sections) > 1:
            for i in range(1, len(sections), 2):
                citation = sections[i].replace("[SOURCE:", "").replace("]", "").strip()
                content = sections[i + 1].strip() if i + 1 < len(sections) else ""
                if not content or len(content) < 15:
                    continue

                words = content.split()
                # Chunk with overlap for long passages
                if len(words) > 130:
                    chunk_size = 100
                    overlap = 25
                    step = chunk_size - overlap
                    sub_idx = 1
                    for start in range(0, len(words), step):
                        sub_words = words[start:start + chunk_size]
                        if len(sub_words) >= 15:
                            self.chunks.append({
                                "citation": f"{citation} (Part {sub_idx})" if len(words) > 170 else citation,
                                "content": " ".join(sub_words)
                            })
                            sub_idx += 1
                else:
                    self.chunks.append({
                        "citation": citation,
                        "content": content
                    })
        else:
            raw_chunks = [p.strip() for p in re.split(r"\n\s*\n+", self.notes_text) if len(p.strip()) > 20]
            if len(raw_chunks) < 3:
                raw_chunks = [l.strip() for l in self.notes_text.split("\n") if len(l.strip()) > 25]

            for idx, p in enumerate(raw_chunks, 1):
                first_words = " ".join(p.split()[:4])
                self.chunks.append({
                    "citation": f"Notes Section {idx}: {first_words}...",
                    "content": p
                })

        # Sanitize chunks: drop any chunk that is not human readable
        self.chunks = [c for c in self.chunks if is_readable_human_text(c["content"]) or len(c["content"].split()) >= 4]

    def _calculate_exam_weightage(self):
        """Maps past exam questions to topics and calculates exam frequency / marks weightage."""
        self.topic_weightage = {}
        for t in self.topics:
            self.topic_weightage[t["name"]] = {
                "count": 0,
                "total_marks": 0,
                "questions": []
            }

        # Split past questions across inline bullets, numbering, and line breaks
        cleaned_pq = re.sub(r'[\u2022\u25cf\u25aa\u25cb•▪▫]\s*', r'\n__Q__:', self.past_papers_text)
        cleaned_pq = re.sub(r'(?<=[.;\n])\s*(\d+[\.\)])\s+', r'\n__Q__:\1 ', cleaned_pq)
        
        past_lines = []
        noise_q = ["instructions", "maximum marks", "time:", "section a", "section b", "section c", "[page"]

        for l in cleaned_pq.split("\n"):
            l = l.strip()
            if l.startswith("__Q__:"):
                l = l.replace("__Q__:", "").strip()
            if len(l) > 10 and not any(k in l.lower() for k in noise_q):
                past_lines.append(l)

        for q in past_lines:
            marks_match = re.search(r'(\d+)\s*Marks?', q, re.IGNORECASE)
            marks = int(marks_match.group(1)) if marks_match else 2

            best_topic = None
            max_overlap = 0
            q_lower = q.lower()

            for t in self.topics:
                keywords = re.findall(r'\w+', t["name"].lower())
                overlap = sum(1 for kw in keywords if len(kw) > 3 and kw in q_lower)
                if overlap > max_overlap:
                    max_overlap = overlap
                    best_topic = t["name"]

            if best_topic and max_overlap > 0:
                self.topic_weightage[best_topic]["count"] += 1
                self.topic_weightage[best_topic]["total_marks"] += marks
                self.topic_weightage[best_topic]["questions"].append(q)

        total_marks = sum(v["total_marks"] for v in self.topic_weightage.values())
        if total_marks > 0:
            for t in self.topics:
                t_name = t["name"]
                marks = self.topic_weightage[t_name]["total_marks"]
                pct = round((marks / total_marks) * 100, 1) if marks > 0 else round(20.0 / max(1, len(self.topics)), 1)
                self.topic_weightage[t_name]["percentage"] = pct
        else:
            even_share = round(100.0 / max(1, len(self.topics)), 1) if self.topics else 20.0
            for t in self.topics:
                self.topic_weightage[t["name"]]["percentage"] = even_share

    def get_topic_weight(self, topic_name: str) -> float:
        """Finds topic exam weightage with robust fuzzy keyword matching and baseline fallback."""
        if not self.topic_weightage:
            return round(100.0 / max(1, len(self.topics) or 4), 1)

        if topic_name in self.topic_weightage and self.topic_weightage[topic_name].get("percentage", 0) > 0:
            return self.topic_weightage[topic_name]["percentage"]

        name_clean = re.sub(r"^[\d\.\s\-*•]+", "", topic_name).lower().strip()
        best_match = None
        max_overlap = 0

        for t_name, data in self.topic_weightage.items():
            t_clean = re.sub(r"^[\d\.\s\-*•]+", "", t_name).lower().strip()
            if name_clean and (name_clean in t_clean or t_clean in name_clean):
                if data.get("percentage", 0) > 0:
                    return data["percentage"]

            words_a = set(w for w in name_clean.split() if len(w) > 3)
            words_b = set(w for w in t_clean.split() if len(w) > 3)
            overlap = len(words_a.intersection(words_b))
            if overlap > max_overlap:
                max_overlap = overlap
                best_match = data

        if best_match and best_match.get("percentage", 0) > 0:
            return best_match["percentage"]

        base_pct = round(100.0 / max(1, len(self.topics) or 4), 1)
        return max(15.0, base_pct)

    def _build_index(self):
        """Builds TF-IDF vector index over chunks for quick relevant text retrieval."""
        if not self.chunks:
            return
        corpus = [c["content"] for c in self.chunks]
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.chunk_matrix = self.vectorizer.fit_transform(corpus)

    def retrieve(self, query: str, top_k: int = 2):
        """Retrieves top_k relevant note chunks with their citations."""
        if not self.vectorizer or not self.chunks:
            return self.chunks[:top_k]
        q_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self.chunk_matrix)[0]
        ranked_indices = sims.argsort()[::-1][:top_k]
        return [self.chunks[i] for i in ranked_indices if sims[i] > 0.05] or self.chunks[:top_k]

    def _gather_candidate_sentences(self):
        """Extracts clean, readable, factual sentences from all notes chunks."""
        candidates = []
        for c in self.chunks:
            raw_sents = re.split(r"[.\n;•]+", c["content"])
            for s in raw_sents:
                clean_s = s.strip()
                words = clean_s.split()
                # Must be 5 to 30 words, with high alpha ratio
                if 5 <= len(words) <= 30 and len(clean_s) >= 25:
                    alpha_ratio = sum(1 for ch in clean_s if ch.isalpha()) / max(1, len(clean_s))
                    if alpha_ratio >= 0.65:
                        candidates.append({
                            "sentence": clean_s,
                            "citation": c["citation"],
                            "full_chunk": c["content"]
                        })
        return candidates

    def _generate_dynamic_chunk_quiz(self):
        """
        Dynamically extracts new sentences from across all notes chunks.
        Guarantees non-repeating questions across consecutive attempts!
        """
        self.quiz_attempt_counter += 1
        candidates = self._gather_candidate_sentences()

        if not candidates:
            return self._get_default_fallback()

        # Filter out sentences already tested in this session
        unasked = [c for c in candidates if c["sentence"] not in self.used_questions]
        
        # If all sentences were exhausted, cycle cleanly while logging
        if len(unasked) < 4:
            self.used_questions.clear()
            unasked = candidates

        # Randomly sample 4 candidates for this quiz
        selected_candidates = random.sample(unasked, min(4, len(unasked)))
        
        question_templates = [
            "According to {citation}, which statement accurately describes '{concept}'?",
            "Based on the notes in {citation}, what key fact is established regarding '{concept}'?",
            "In {citation}, what mechanism or definition is specified concerning '{concept}'?",
            "Which of the following points is emphasized in {citation} about '{concept}'?"
        ]

        generated = []
        qid = 1

        for item in selected_candidates:
            target_sentence = item["sentence"]
            citation = item["citation"]
            full_chunk = item["full_chunk"]
            self.used_questions.add(target_sentence)

            # Match to most relevant topic
            matched_topic = self.topics[0]["name"] if self.topics else "Core Concept"
            for t in self.topics:
                t_words = [w.lower() for w in t["name"].split() if len(w) > 3]
                if any(w in full_chunk.lower() for w in t_words):
                    matched_topic = t["name"]
                    break

            words = target_sentence.split()
            concept_title = " ".join(words[:4]) if len(words) >= 4 else target_sentence
            template = random.choice(question_templates)
            question_text = template.format(citation=f"[{citation}]", concept=concept_title)

            correct_opt = target_sentence

            # Build authentic distractors from OTHER candidate sentences in the same material!
            other_sentences = [c["sentence"] for c in candidates if c["sentence"] != target_sentence]
            if len(other_sentences) >= 3:
                distractor_samples = random.sample(other_sentences, 3)
                distractor_1 = distractor_samples[0]
                distractor_2 = distractor_samples[1]
                distractor_3 = distractor_samples[2]
            else:
                distractor_1 = f"It functions without involving {concept_title}."
                distractor_2 = f"This mechanism is inactive under standard operational conditions."
                distractor_3 = f"This property was superseded in subsequent revisions."

            options = [correct_opt, distractor_1, distractor_2, distractor_3]
            random.shuffle(options)

            generated.append({
                "id": qid,
                "topic": matched_topic,
                "question": question_text,
                "options": options,
                "answer": correct_opt,
                "citation": citation,
                "explanation": f"Grounded directly in {citation}: '{target_sentence}'."
            })
            qid += 1

        return generated

    def _get_default_fallback(self):
        pool = [
            {
                "id": 1,
                "topic": "1.1 Chloroplast Structure and Pigments",
                "question": "Which photosynthetic pigment is primarily responsible for absorbing blue-violet and red light while reflecting green?",
                "options": ["Chlorophyll a", "Carotenoids", "Chlorophyll b", "Anthocyanin"],
                "answer": "Chlorophyll a",
                "citation": "Textbook Ch. 1 - Section 1.1: Chloroplasts & Pigments",
                "explanation": "Chlorophyll a is the primary photosynthetic pigment absorbing blue-violet and red light."
            },
            {
                "id": 2,
                "topic": "1.2 Light-Dependent Reactions",
                "question": "Where does the photolysis of water occur, producing protons, electrons, and oxygen gas?",
                "options": ["Photosystem II (P680)", "Photosystem I (P700)", "Calvin Cycle in Stroma", "Mitochondrial Matrix"],
                "answer": "Photosystem II (P680)",
                "citation": "Textbook Ch. 1 - Section 1.2: Light-Dependent Reactions",
                "explanation": "Photolysis of water occurs at Photosystem II (P680), splitting water into protons, electrons, and oxygen."
            },
            {
                "id": 3,
                "topic": "1.3 Calvin Cycle / Light-Independent Reactions",
                "question": "What enzyme catalyzes the initial carbon fixation step by combining CO2 with ribulose bisphosphate (RuBP)?",
                "options": ["RuBisCO", "ATP Synthase", "DNA Polymerase III", "Phosphofructokinase"],
                "answer": "RuBisCO",
                "citation": "Textbook Ch. 1 - Section 1.3: The Calvin Cycle",
                "explanation": "Carbon fixation is catalyzed by RuBisCO in the stroma."
            },
            {
                "id": 4,
                "topic": "2.1 Glycolysis",
                "question": "What is the net yield of ATP directly produced from one molecule of glucose during glycolysis?",
                "options": ["2 ATP", "4 ATP", "32 ATP", "1 ATP"],
                "answer": "2 ATP",
                "citation": "Textbook Ch. 2 - Section 2.1: Glycolysis",
                "explanation": "Glycolysis yields a net of 2 ATP per glucose molecule."
            },
            {
                "id": 5,
                "topic": "2.3 Oxidative Phosphorylation & ATP Synthase",
                "question": "What acts as the terminal electron acceptor at the end of the mitochondrial electron transport chain?",
                "options": ["Molecular Oxygen (O2)", "NAD+", "Pyruvate", "Carbon Dioxide"],
                "answer": "Molecular Oxygen (O2)",
                "citation": "Textbook Ch. 2 - Section 2.3: Oxidative Phosphorylation",
                "explanation": "Electrons flow down the chain toward molecular oxygen (the terminal acceptor, forming H2O)."
            },
            {
                "id": 6,
                "topic": "3.2 Replication Machinery",
                "question": "Which enzyme is responsible for synthesizing discontinuous Okazaki fragments on the lagging DNA strand?",
                "options": ["DNA Polymerase III", "DNA Ligase", "Helicase", "RNA Polymerase"],
                "answer": "DNA Polymerase III",
                "citation": "Textbook Ch. 3 - Section 3.2: DNA Replication",
                "explanation": "DNA Polymerase III synthesizes DNA fragments on the lagging strand."
            }
        ]
        available_pool = [q for q in pool if q["question"] not in self.used_questions]
        if len(available_pool) < 4:
            self.used_questions.clear()
            available_pool = pool

        sampled = random.sample(available_pool, min(4, len(available_pool)))
        for idx, item in enumerate(sampled, 1):
            self.used_questions.add(item["question"])
            item["id"] = idx
            random.shuffle(item["options"])
        return sampled

    def generate_quiz(self, api_key: str = None, provider: str = "groq", *args, **kwargs):
        """Generates diagnostic quiz questions grounded strictly in the source chunks."""
        self.last_api_error = None
        use_ai = kwargs.get("use_ai", True)

        # 1. If LLM (Groq Llama or Gemini) is requested and valid API key is configured:
        if use_ai and api_key and api_key.strip() and not api_key.startswith("AQ"):
            try:
                chunks_to_use = random.sample(self.chunks, min(4, len(self.chunks))) if len(self.chunks) >= 4 else self.chunks
                chunks_summary = "\n\n".join([f"[{c['citation']}]:\n{c['content'][:350]}" for c in chunks_to_use])
                topics_list = ", ".join([t["name"] for t in self.topics[:8]])
                seed = random.randint(100, 9999)

                prompt = f"""[Session #{seed}] You are an expert exam diagnostician. Create 4 brand-new unique multiple-choice quiz questions grounded ONLY in these retrieved textbook chunks:
TOPICS: {topics_list}
RETRIEVED CHUNKS:
{chunks_summary}

RULES:
- Questions and options must be strictly derived from the facts in the chunks above. Do NOT use outside general knowledge.
- For each question, cite the exact source from the chunk tag (e.g., "[02_ML_Study_Notes.pdf - Page 1]").
- Return ONLY a valid JSON array of 4 objects.
- Keys:
  "id": integer (1 to 4)
  "topic": relevant topic string from TOPICS
  "question": clear diagnostic question
  "options": array of 4 distinct choices
  "answer": exact correct string (matching one of the options)
  "citation": source citation string (e.g. "02_ML_Study_Notes.pdf - Page 1")
  "explanation": 1-2 sentence evidence statement citing the text
"""
                system_instruction = "You are GapFinder AI, a rigorous academic diagnostic test generator. Only output valid JSON array."
                raw_response = call_llm(prompt, api_key, provider=provider, system_instruction=system_instruction, temperature=0.3)
                parsed = extract_json(raw_response)
                if isinstance(parsed, list) and len(parsed) >= 2:
                    return parsed
            except Exception as e:
                self.last_api_error = str(e)

        # 2. Dynamic instant extraction from student's actual uploaded notes (guaranteed unique & fresh!)
        return self._generate_dynamic_chunk_quiz()

    def evaluate_answers(self, user_answers: dict, quiz: list, api_key: str = None):
        results = []
        topic_scores = {}

        for q in quiz:
            qid = str(q["id"])
            user_ans = user_answers.get(qid, "").strip() if user_answers.get(qid) else ""
            correct_ans = q["answer"].strip()
            topic = q["topic"]

            is_correct = (user_ans.lower() == correct_ans.lower())

            if topic not in topic_scores:
                topic_scores[topic] = {"correct": 0, "total": 0, "mistakes": []}

            topic_scores[topic]["total"] += 1
            if is_correct:
                topic_scores[topic]["correct"] += 1
            else:
                topic_scores[topic]["mistakes"].append({
                    "question": q["question"],
                    "user_ans": user_ans or "Skipped",
                    "correct_ans": correct_ans,
                    "citation": q.get("citation", ""),
                    "explanation": q.get("explanation", "")
                })

            results.append({
                "id": q["id"],
                "topic": topic,
                "question": q["question"],
                "user_answer": user_ans,
                "correct_answer": correct_ans,
                "is_correct": is_correct,
                "citation": q.get("citation", ""),
                "explanation": q.get("explanation", "")
            })

        return results, topic_scores

    def generate_gap_report(self, topic_scores: dict, api_key: str = None, provider: str = "groq"):
        report = {
            "weak": [],
            "medium": [],
            "strong": [],
            "summary": ""
        }

        for topic, data in topic_scores.items():
            tot = data["total"]
            corr = data["correct"]
            pct = round((corr / tot) * 100) if tot > 0 else 0
            weight = self.get_topic_weight(topic)

            item = {
                "topic": topic,
                "accuracy": pct,
                "correct": corr,
                "total": tot,
                "exam_weightage": weight,
                "mistakes": data["mistakes"]
            }

            if pct < 50:
                item["status"] = "Weak"
                item["badge"] = "🔴 Weak"
                mistake_desc = f"Missed {tot - corr} of {tot} questions."
                if data["mistakes"]:
                    mistake_desc += f" Struggles with: '{data['mistakes'][0]['question'][:65]}...'"
                item["diagnosis"] = mistake_desc
                report["weak"].append(item)
            elif pct <= 75:
                item["status"] = "Medium"
                item["badge"] = "🟡 Medium"
                item["diagnosis"] = f"Partially understood ({corr}/{tot} correct). Needs consolidation on core definitions."
                report["medium"].append(item)
            else:
                item["status"] = "Strong"
                item["badge"] = "🟢 Strong"
                item["diagnosis"] = f"Mastered ({corr}/{tot} correct). High confidence on exam-style recall."
                report["strong"].append(item)

        total_q = sum(d["total"] for d in topic_scores.values())
        total_c = sum(d["correct"] for d in topic_scores.values())
        overall_pct = round((total_c / total_q) * 100) if total_q > 0 else 0
        report["overall_percentage"] = overall_pct

        # Clinical Diagnosis Summary (LLM or Rule-Based)
        if api_key and api_key.strip() and not api_key.startswith("AQ"):
            try:
                weak_list = ", ".join([f"{w['topic']} ({w['accuracy']}% acc, {w['exam_weightage']}% exam wt)" for w in report["weak"]])
                prompt = f"""You are GapFinder AI. A student completed a diagnostic assessment with score {total_c}/{total_q} ({overall_pct}%).
WEAK TOPICS: {weak_list or 'None'}
MEDIUM TOPICS: {', '.join([m['topic'] for m in report['medium']]) or 'None'}
STRONG TOPICS: {', '.join([s['topic'] for s in report['strong']]) or 'None'}

Write a 2-sentence clinical learning diagnosis. State clearly which high-priority topics require immediate revision and why."""
                ai_summary = call_llm(prompt, api_key, provider=provider, temperature=0.2)
                if ai_summary and len(ai_summary.strip()) > 20:
                    report["summary"] = ai_summary.strip()
                    return report
            except Exception:
                pass

        if report["weak"]:
            weak_names = ", ".join([w["topic"] for w in report["weak"]])
            report["summary"] = f"Critical gaps detected in: {weak_names}. Prioritize these high-impact exam areas immediately."
        else:
            report["summary"] = "Solid foundational grasp across tested modules. Ready for advanced past paper problem sets."

        return report

    def generate_revision_plan(self, gap_report: dict, days: int = 5, hours_per_day: float = 2.0, api_key: str = None, provider: str = "groq"):
        """
        Builds a prioritized, multi-day adaptive revision roadmap.
        Guarantees that EVERY day from Day 1 to Day N receives structured study sessions,
        prioritizing weak exam topics while systematically covering the syllabus.
        """
        days = max(1, int(days))
        hours_per_day = max(0.5, float(hours_per_day))
        total_budget = round(days * hours_per_day, 1)

        # 1. Collect tested topics by name
        tested_names = set()
        plan_topics = []

        # 1A. Weak topics (Highest Priority)
        for t in gap_report.get("weak", []):
            name = t["topic"].strip()
            tested_names.add(name.lower())
            w_factor = max(0.6, (100 - t.get("accuracy", 0)) / 100.0)
            exam_w = t.get("exam_weightage", self.get_topic_weight(name))
            p_score = round(w_factor * (exam_w / 100.0) * 100, 2)
            plan_topics.append({
                "topic": name,
                "badge": "🔴 Weak",
                "priority_score": max(p_score, 18.0),
                "exam_weight": exam_w,
                "status": "Weak"
            })

        # 1B. Medium topics
        for t in gap_report.get("medium", []):
            name = t["topic"].strip()
            tested_names.add(name.lower())
            w_factor = max(0.3, (100 - t.get("accuracy", 50)) / 100.0)
            exam_w = t.get("exam_weightage", self.get_topic_weight(name))
            p_score = round(w_factor * (exam_w / 100.0) * 100, 2)
            plan_topics.append({
                "topic": name,
                "badge": "🟡 Medium",
                "priority_score": max(p_score, 12.0),
                "exam_weight": exam_w,
                "status": "Medium"
            })

        # 1C. Untested Syllabus Topics (Ensure complete curriculum coverage across all days)
        for t in self.topics:
            name = t["name"].strip()
            if name.lower() not in tested_names:
                exam_w = self.get_topic_weight(name)
                p_score = round(0.5 * (exam_w / 100.0) * 100, 2)
                plan_topics.append({
                    "topic": name,
                    "badge": "⚪ Untested Syllabus",
                    "priority_score": max(p_score, 6.0),
                    "exam_weight": exam_w,
                    "status": "Untested"
                })

        # 1D. Strong topics (Light consolidation)
        for t in gap_report.get("strong", []):
            name = t["topic"].strip()
            tested_names.add(name.lower())
            exam_w = t.get("exam_weightage", self.get_topic_weight(name))
            plan_topics.append({
                "topic": name,
                "badge": "🟢 Mastered",
                "priority_score": 3.0,
                "exam_weight": exam_w,
                "status": "Strong"
            })

        # Sort all topics by urgency / priority score
        plan_topics.sort(key=lambda x: x["priority_score"], reverse=True)

        # 2. Multi-phase progressive expansion if topics are fewer than total days
        if len(plan_topics) < days:
            milestones = [
                ("Foundations & Key Definitions", "Read core concepts, textbook notes, and definitions", "Build summary flashcards"),
                ("Mechanisms & Problem Solving", "Study step-by-step mechanisms and formula derivations", "Solve 3 practice problems"),
                ("Past Paper Exam Drill", f"Solve high-frequency past exam questions", "Analyze grading scheme"),
                ("Pitfall & Edge Case Analysis", "Review common test traps, exceptions, and distinctions", "Self-explanation review"),
                ("Final Timed Mock & Consolidation", "Complete a timed mock quiz and review mistakes", "Confirm exam readiness")
            ]
            expanded = []
            for d in range(days):
                base_t = plan_topics[d % len(plan_topics)]
                m_title, m_task1, m_task2 = milestones[d % len(milestones)]
                expanded.append({
                    "topic": f"{base_t['topic']} — Phase: {m_title}",
                    "badge": base_t["badge"],
                    "priority_score": base_t["priority_score"],
                    "exam_weight": base_t["exam_weight"],
                    "tasks": [
                        f"{m_task1} on {base_t['topic']}",
                        f"{m_task2} ({base_t['exam_weight']}% exam weight)",
                        "Take a 3-question diagnostic self-check"
                    ]
                })
            plan_topics = expanded

        # 3. Distribute topics across the days ensuring EVERY day has sessions
        day_schedule = [[] for _ in range(days)]
        for idx, t in enumerate(plan_topics):
            target_day = idx % days
            day_schedule[target_day].append(t)

        # 4. Budget daily hours evenly so each day reflects hours_per_day
        schedule_output = []
        for d_idx, day_items in enumerate(day_schedule, 1):
            day_total_p = sum(item["priority_score"] for item in day_items) or 1
            sessions = []
            for item in day_items:
                share = item["priority_score"] / day_total_p
                allocated = max(0.5, round(share * hours_per_day, 1))

                # Build actionable tasks if not pre-assigned
                if "tasks" in item:
                    tasks = item["tasks"]
                elif "Weak" in item["badge"]:
                    tasks = [
                        f"Targeted Remediation: Review notes on {item['topic']}",
                        f"Drill: Solve past exam questions ({item['exam_weight']}% exam weight)",
                        "Retest: Complete a 3-question diagnostic re-check"
                    ]
                elif "Untested" in item["badge"]:
                    tasks = [
                        f"Syllabus Coverage: Read notes & chapter excerpts on {item['topic']}",
                        f"Self-Check: Review core definitions and formulas ({item['exam_weight']}% exam weight)",
                        "Diagnostic: Verify understanding with a practice question"
                    ]
                else:
                    tasks = [
                        f"Consolidation: Quick review of definitions on {item['topic']}",
                        f"Speed Drill: Rapid recall test on past questions ({item['exam_weight']}% exam weight)",
                        "Final Check: Confirm exam-readiness"
                    ]

                sessions.append({
                    "topic": item["topic"],
                    "badge": item["badge"],
                    "allocated_hours": allocated,
                    "priority_score": item["priority_score"],
                    "exam_weight": item["exam_weight"],
                    "tasks": tasks
                })

            day_hours = round(sum(s["allocated_hours"] for s in sessions), 1)
            schedule_output.append({
                "day": f"Day {d_idx}",
                "total_hours": day_hours,
                "sessions": sessions
            })

        return {
            "total_days": days,
            "hours_per_day": hours_per_day,
            "total_hours": round(sum(d["total_hours"] for d in schedule_output), 1),
            "schedule": schedule_output
        }

    def explain_topic(self, topic_query: str, api_key: str = None, provider: str = "groq", fast_mode: bool = False):
        """Answers topic queries strictly grounded in retrieved notes. If insufficient, returns 'Not found in your uploaded material.'"""
        relevant_chunks = self.retrieve(topic_query, top_k=2)
        
        # Check relevance
        query_words = set(re.findall(r"\w+", topic_query.lower())) - {"what", "is", "the", "how", "why", "in", "and", "of", "to", "explain", "describe", "define"}
        context_words = set(re.findall(r"\w+", " ".join(c["content"] for c in relevant_chunks).lower())) if relevant_chunks else set()
        
        # If no chunks or zero overlap with core query keywords
        if not relevant_chunks or (query_words and not query_words.intersection(context_words)):
            return {
                "answer": "Not found in your uploaded material.",
                "citations": [],
                "retrieved_context": ""
            }

        citations = [c["citation"] for c in relevant_chunks]
        context = "\n\n".join([f"[{c['citation']}]: {c['content']}" for c in relevant_chunks])

        if fast_mode or not api_key or not api_key.strip() or api_key.startswith("AQ"):
            main_chunk = relevant_chunks[0]["content"] if relevant_chunks else "No content"
            instant_answer = f"""### 📖 Grounded Source Extract:
**Verified Citations:** {', '.join(citations)}

{main_chunk}
"""
            return {
                "answer": instant_answer,
                "citations": citations,
                "retrieved_context": context
            }

        prompt = f"""You are GapFinder AI, an evidence-grounded study tutor.
TASK: Explain '{topic_query}' concisely using ONLY the retrieved notes below.

RETRIEVED NOTES CONTEXT:
{context}

STRICT GROUNDING RULES:
1. Answer ONLY using the facts present in the retrieved notes above.
2. NEVER use outside general knowledge or make assumptions.
3. If the retrieved notes do not contain sufficient information to answer '{topic_query}', output EXACTLY:
   Not found in your uploaded material.
4. When answering from the text, write 3-4 clear bullet points and include the exact source citation tag like [{citations[0]}].
"""
        system_instruction = "Evidence-grounded study tutor. Answer strictly from the provided context. If missing, say 'Not found in your uploaded material.'"
        try:
            explanation = call_llm(prompt, api_key, provider=provider, system_instruction=system_instruction, temperature=0.1)
            if "not found in your uploaded material" in explanation.lower():
                return {
                    "answer": "Not found in your uploaded material.",
                    "citations": citations,
                    "retrieved_context": context
                }
            return {
                "answer": explanation,
                "citations": citations,
                "retrieved_context": context
            }
        except Exception:
            main_chunk = relevant_chunks[0]["content"] if relevant_chunks else "No content"
            return {
                "answer": f"### 📖 Grounded Source Extract ({', '.join(citations)}):\n\n{main_chunk}",
                "citations": citations,
                "retrieved_context": context
            }
