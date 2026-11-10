"use client";

import React, { useState, useEffect } from "react";
import {
  BookOpen,
  FileText,
  HelpCircle,
  BarChart3,
  Calendar,
  MessageSquare,
  Award,
  Upload,
  CheckCircle2,
  AlertTriangle,
  Trash2,
  Eye,
  RefreshCw,
  Sparkles,
  Zap,
  Clock,
  Key,
  Layers,
  ChevronRight,
  ShieldCheck
} from "lucide-react";
import {
  DocumentRecord,
  Chunk,
  Topic,
  TopicWeight,
  QuizQuestion,
  GapReport,
  RevisionPlan,
  AssessmentAttempt
} from "@/lib/types";
import { DEMO_DOCUMENTS } from "@/lib/demoData";
import {
  parseTopics,
  calculateExamWeightage,
  chunkNotes,
  retrieveRelevantChunks,
  generateQuizLocal,
  evaluateAnswers,
  generateGapReport,
  generateRevisionPlan
} from "@/lib/ragEngine";

export default function GapFinderApp() {
  const [activeTab, setActiveTab] = useState<number>(0);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [weightage, setWeightage] = useState<Record<string, TopicWeight>>({});
  const [chunks, setChunks] = useState<Chunk[]>([]);
  
  // AI Settings
  const [aiProvider, setAiProvider] = useState<"groq" | "local">("groq");
  const [groqKey, setGroqKey] = useState<string>("");
  const [showKeyModal, setShowKeyModal] = useState<boolean>(false);

  // Quiz & Assessment State
  const [quiz, setQuiz] = useState<QuizQuestion[] | null>(null);
  const [userAnswers, setUserAnswers] = useState<Record<string, string>>({});
  const [quizSubmitted, setQuizSubmitted] = useState<boolean>(false);
  const [quizResults, setQuizResults] = useState<any[]>([]);
  const [gapReport, setGapReport] = useState<GapReport | null>(null);
  const [revisionPlan, setRevisionPlan] = useState<RevisionPlan | null>(null);

  // Revision Sliders
  const [revDays, setRevDays] = useState<number>(5);
  const [revHours, setRevHours] = useState<number>(2.0);

  // Grounded Chat State
  const [chatMessages, setChatMessages] = useState<
    { role: "user" | "assistant"; content: string; citations?: string[] }[]
  >([]);
  const [chatInput, setChatInput] = useState<string>("");
  const [chatLoading, setChatLoading] = useState<boolean>(false);

  // Performance Attempts
  const [attempts, setAttempts] = useState<AssessmentAttempt[]>([]);

  // UI Modal for Viewing Document Text
  const [viewingDoc, setViewingDoc] = useState<DocumentRecord | null>(null);
  const [loadingAction, setLoadingAction] = useState<string>("");

  // Paste Text Modal State
  const [showPasteModal, setShowPasteModal] = useState<boolean>(false);
  const [pasteDocType, setPasteDocType] = useState<DocumentRecord["doc_type"]>("Study Notes");
  const [pasteTitle, setPasteTitle] = useState<string>("");
  const [pasteContent, setPasteContent] = useState<string>("");

  // Extract text from file (PDF using pdf.js or TXT)
  async function extractFileContent(file: File): Promise<{ text: string; pageCount: number; status: "Success" | "OCR Required" }> {
    if (file.name.toLowerCase().endsWith(".pdf")) {
      try {
        if (typeof window !== "undefined" && !(window as any).pdfjsLib) {
          await new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
            script.onload = () => {
              (window as any).pdfjsLib.GlobalWorkerOptions.workerSrc =
                "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
              resolve(true);
            };
            script.onerror = () => reject(new Error("Failed to load PDF extraction engine"));
            document.head.appendChild(script);
          });
        }

        const pdfjs = (window as any).pdfjsLib;
        const arrayBuffer = await file.arrayBuffer();
        const loadingTask = pdfjs.getDocument({ data: arrayBuffer });
        const pdf = await loadingTask.promise;
        const pageCount = pdf.numPages;
        let extractedText = "";

        for (let i = 1; i <= pageCount; i++) {
          const page = await pdf.getPage(i);
          const textContent = await page.getTextContent();
          let pageText = "";
          let lastY: number | null = null;

          for (const item of textContent.items) {
            if (!item || !item.str) continue;
            const currentY = item.transform && item.transform.length >= 6 ? item.transform[5] : null;
            if (lastY !== null && currentY !== null && Math.abs(currentY - lastY) > 5) {
              pageText += "\n";
            } else if (item.hasEOL) {
              pageText += "\n";
            } else if (pageText.length > 0 && !pageText.endsWith("\n") && !pageText.endsWith(" ") && !item.str.startsWith(" ")) {
              pageText += " ";
            }
            pageText += item.str;
            lastY = currentY;
          }

          pageText = pageText.trim();
          if (pageText) {
            extractedText += `[Page ${i}]\n${pageText}\n\n`;
          }
        }

        const cleanText = extractedText.trim();
        const status = cleanText.length > 15 ? "Success" : "OCR Required";
        return { text: cleanText, pageCount, status };
      } catch (err) {
        console.error("PDF extraction error:", err);
        return { text: "", pageCount: 1, status: "OCR Required" };
      }
    } else {
      const text = await file.text();
      const pageCount = Math.max(1, Math.ceil(text.length / 1500));
      return { text: text.trim(), pageCount, status: text.trim().length > 15 ? "Success" : "OCR Required" };
    }
  }

  // Load Initial Demo Course on Mount
  useEffect(() => {
    const savedDocs = localStorage.getItem("gapfinder_docs");
    const savedAttempts = localStorage.getItem("gapfinder_attempts");

    if (savedAttempts) {
      try {
        setAttempts(JSON.parse(savedAttempts));
      } catch (e) {}
    }

    if (savedDocs) {
      try {
        const parsed = JSON.parse(savedDocs);
        if (parsed.length > 0) {
          loadDocumentsIntoRAG(parsed);
          return;
        }
      } catch (e) {}
    }

    // Default: Load Sample ML Course
    loadDocumentsIntoRAG(DEMO_DOCUMENTS);
  }, []);

  function loadDocumentsIntoRAG(docs: DocumentRecord[]) {
    setDocuments(docs);
    localStorage.setItem("gapfinder_docs", JSON.stringify(docs));

    if (docs.length === 0) {
      setTopics([]);
      setWeightage({});
      setChunks([]);
      return;
    }

    // Combine syllabus, notes, past papers
    let sylText = "";
    let notText = "";
    let pasText = "";

    docs.forEach(doc => {
      if (doc.status !== "Success") return;
      if (doc.doc_type === "Syllabus") {
        sylText += doc.extracted_text + "\n\n";
      } else if (doc.doc_type === "Previous Question Paper") {
        pasText += doc.extracted_text + "\n\n";
      } else {
        notText += `[SOURCE: ${doc.filename}]\n${doc.extracted_text}\n\n`;
      }
    });

    const parsedTopics = parseTopics(sylText, notText || pasText);
    const parsedWeight = calculateExamWeightage(parsedTopics, pasText);

    let combinedNotesForChunking = notText;
    if (!combinedNotesForChunking.trim()) {
      // If user only uploaded syllabus or past paper, chunk whatever is available so quiz can be generated
      docs.forEach(doc => {
        if (doc.status === "Success" && doc.extracted_text) {
          combinedNotesForChunking += `[SOURCE: ${doc.filename}]\n${doc.extracted_text}\n\n`;
        }
      });
    }
    const parsedChunks = chunkNotes(combinedNotesForChunking);

    setTopics(parsedTopics);
    setWeightage(parsedWeight);
    setChunks(parsedChunks);
  }

  function handleResetToSample() {
    loadDocumentsIntoRAG(DEMO_DOCUMENTS);
    setQuiz(null);
    setQuizSubmitted(false);
    setUserAnswers({});
    setGapReport(null);
    setRevisionPlan(null);
  }

  function handleClearAll() {
    loadDocumentsIntoRAG([]);
    setQuiz(null);
    setQuizSubmitted(false);
    setUserAnswers({});
    setGapReport(null);
    setRevisionPlan(null);
    setChatMessages([]);
  }

  // Handle Document Delete
  function handleDeleteDocument(id: string) {
    const updated = documents.filter(d => d.id !== id);
    loadDocumentsIntoRAG(updated);
  }

  // Handle Text/File Ingestion with PDF Extraction
  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>, docType: DocumentRecord["doc_type"]) {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setLoadingAction(`Extracting ${files.length} document(s) with pdfjs-dist...`);
    const newDocs: DocumentRecord[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const { text, pageCount, status } = await extractFileContent(file);

      newDocs.push({
        id: `doc_${Date.now()}_${i}`,
        filename: file.name,
        doc_type: docType,
        page_count: pageCount,
        status: status,
        extracted_text: text,
        created_at: new Date().toISOString()
      });
    }

    // Automatically replace demo documents when user uploads their custom files
    const isOnlyDemo = documents.length > 0 && documents.every(d => d.id.startsWith("demo_doc_"));
    const all = isOnlyDemo ? newDocs : [...documents.filter(d => !d.id.startsWith("demo_doc_")), ...newDocs];

    loadDocumentsIntoRAG(all);
    setQuiz(null);
    setQuizSubmitted(false);
    setUserAnswers({});
    setGapReport(null);
    setRevisionPlan(null);
    setLoadingAction("");
    e.target.value = "";
  }

  // Handle Pasted Text
  function handleSavePastedText() {
    if (!pasteContent.trim()) return;
    const title = pasteTitle.trim() || `${pasteDocType} (Pasted Text)`;
    const newDoc: DocumentRecord = {
      id: `doc_paste_${Date.now()}`,
      filename: title.endsWith(".txt") ? title : `${title}.txt`,
      doc_type: pasteDocType,
      page_count: Math.max(1, Math.ceil(pasteContent.length / 1500)),
      status: "Success",
      extracted_text: pasteContent.trim(),
      created_at: new Date().toISOString()
    };

    const isOnlyDemo = documents.length > 0 && documents.every(d => d.id.startsWith("demo_doc_"));
    const all = isOnlyDemo ? [newDoc] : [...documents.filter(d => !d.id.startsWith("demo_doc_")), newDoc];

    loadDocumentsIntoRAG(all);
    setQuiz(null);
    setQuizSubmitted(false);
    setUserAnswers({});
    setGapReport(null);
    setRevisionPlan(null);
    setPasteTitle("");
    setPasteContent("");
    setShowPasteModal(false);
  }

  // Generate Diagnostic Quiz
  async function handleGenerateQuiz() {
    setLoadingAction("Formulating grounded diagnostic questions...");
    setUserAnswers({});
    setQuizSubmitted(false);

    if (aiProvider === "groq") {
      try {
        const sampleChunks = chunks.slice(0, 4).map(c => `[${c.citation}]:\n${c.content.slice(0, 300)}`).join("\n\n");
        const topicsStr = topics.slice(0, 8).map(t => t.name).join(", ");
        const res = await fetch("/api/groq", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode: "quiz",
            prompt: `Create 4 diagnostic multiple-choice questions for topics: ${topicsStr}`,
            context: sampleChunks,
            customKey: groqKey || undefined
          })
        });
        if (res.ok) {
          const data = await res.json();
          if (data.quiz && Array.isArray(data.quiz) && data.quiz.length >= 2) {
            setQuiz(data.quiz);
            setLoadingAction("");
            return;
          }
        }
      } catch (err) {}
    }

    // High quality local RAG fallback
    const localQuiz = generateQuizLocal(chunks, topics);
    setQuiz(localQuiz);
    setLoadingAction("");
  }

  // Submit Quiz & Evaluate
  function handleSubmitQuiz() {
    if (!quiz) return;
    const { results, topicScores } = evaluateAnswers(userAnswers, quiz);
    setQuizResults(results);
    setQuizSubmitted(true);

    const report = generateGapReport(topicScores, topics, weightage);
    setGapReport(report);

    const plan = generateRevisionPlan(report, topics, weightage, revDays, revHours);
    setRevisionPlan(plan);

    // Save attempt
    const score = results.filter(r => r.is_correct).length;
    const attemptItem: AssessmentAttempt = {
      id: `attempt_${Date.now()}`,
      attempt_number: attempts.length + 1,
      score,
      total_questions: results.length,
      percentage: Math.round((score / results.length) * 100),
      created_at: new Date().toLocaleDateString() + " " + new Date().toLocaleTimeString()
    };
    const updatedAttempts = [...attempts, attemptItem];
    setAttempts(updatedAttempts);
    localStorage.setItem("gapfinder_attempts", JSON.stringify(updatedAttempts));
  }

  // Regenerate Revision Plan with Custom Hours
  function handleRegeneratePlan() {
    if (!gapReport) return;
    const plan = generateRevisionPlan(gapReport, topics, weightage, revDays, revHours);
    setRevisionPlan(plan);
  }

  // Ask Question in Grounded Assistant
  async function handleSendMessage(queryOverride?: string) {
    const query = queryOverride || chatInput;
    if (!query.trim()) return;

    const userMsg = { role: "user" as const, content: query };
    setChatMessages(prev => [...prev, userMsg]);
    if (!queryOverride) setChatInput("");
    setChatLoading(true);

    const relevant = retrieveRelevantChunks(chunks, query, 2);
    const citations = relevant.map(r => r.citation);
    const context = relevant.map(r => `[${r.citation}]:\n${r.content}`).join("\n\n");

    if (aiProvider === "groq") {
      try {
        const res = await fetch("/api/groq", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode: "explain",
            prompt: query,
            context,
            customKey: groqKey || undefined
          })
        });
        if (res.ok) {
          const data = await res.json();
          setChatMessages(prev => [
            ...prev,
            {
              role: "assistant",
              content: data.answer || "Not found in your uploaded material.",
              citations: data.answer?.includes("Not found") ? [] : citations
            }
          ]);
          setChatLoading(false);
          return;
        }
      } catch (e) {}
    }

    // Local Grounded Answer
    if (relevant.length > 0) {
      setChatMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: `### 📖 Grounded Source Extract:\n\n${relevant[0].content}`,
          citations
        }
      ]);
    } else {
      setChatMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: "Not found in your uploaded material."
        }
      ]);
    }
    setChatLoading(false);
  }

  const totalMarks = Object.values(weightage).reduce((sum, v) => sum + v.total_marks, 0);
  const highestTopic = Object.entries(weightage).sort((a, b) => b[1].total_marks - a[1].total_marks)[0]?.[0] || "All Topics Balanced";

  const tabs = [
    { name: "Materials & Library", icon: BookOpen },
    { name: "Syllabus Map", icon: Layers },
    { name: "Diagnostic Quiz", icon: HelpCircle },
    { name: "Gap Diagnosis", icon: AlertTriangle },
    { name: "Revision Roadmap", icon: Calendar },
    { name: "Grounded Assistant", icon: MessageSquare },
    { name: "Performance", icon: BarChart3 }
  ];

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100">
      {/* Top Navigation */}
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-sky-500/20">
              GF
            </div>
            <div>
              <div className="font-bold text-lg tracking-tight text-white flex items-center gap-2">
                GapFinder AI
                <span className="text-[10px] font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded-full px-2 py-0.5">
                  Diagnostic Platform
                </span>
              </div>
              <p className="text-xs text-slate-400">Find what you don't know • Evidence-grounded revision</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleClearAll}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-red-950/30 text-red-400 border border-red-800/40 hover:bg-red-900/40 transition flex items-center gap-1.5"
              title="Clear all stored documents and start fresh on a new subject"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Clear All (New Subject)</span>
            </button>

            <button
              onClick={handleResetToSample}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 transition flex items-center gap-1.5"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>🚀 Load Demo ML Course</span>
            </button>

            <button
              onClick={() => setShowKeyModal(true)}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 transition flex items-center gap-1.5"
            >
              <Key className="w-3.5 h-3.5 text-amber-400" />
              <span>{groqKey ? "Groq Key Configured" : "Add Groq Key"}</span>
            </button>
          </div>
        </div>

        {/* Tab Navigation Bar */}
        <div className="max-w-7xl mx-auto px-4 flex space-x-1 overflow-x-auto scrollbar-none border-t border-slate-800/60">
          {tabs.map((tab, idx) => {
            const Icon = tab.icon;
            const active = activeTab === idx;
            return (
              <button
                key={tab.name}
                onClick={() => setActiveTab(idx)}
                className={`py-3 px-3.5 text-xs font-medium flex items-center gap-2 border-b-2 whitespace-nowrap transition-colors ${
                  active
                    ? "border-sky-500 text-sky-400 bg-sky-500/5 font-semibold"
                    : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700"
                }`}
              >
                <Icon className={`w-4 h-4 ${active ? "text-sky-400" : "text-slate-400"}`} />
                <span>{tab.name}</span>
                {idx === 1 && topics.length > 0 && (
                  <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.2 rounded-full">
                    {topics.length}
                  </span>
                )}
                {idx === 3 && gapReport?.weak && gapReport.weak.length > 0 && (
                  <span className="text-[10px] bg-rose-500/20 text-rose-400 px-1.5 py-0.2 rounded-full font-bold">
                    {gapReport.weak.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 py-6 flex-1 w-full">
        {/* Active Session Ribbon */}
        {topics.length > 0 && (
          <div className="mb-6 p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-3 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <div>
                <span className="text-sm font-semibold text-slate-200">Active RAG Study Bundle</span>
                <p className="text-xs text-slate-400">
                  <b className="text-sky-400">{topics.length}</b> Syllabus Topics Mapped &bull;{" "}
                  <b className="text-emerald-400">{chunks.length}</b> Grounded Note Chunks with Page Citations &bull;{" "}
                  <b className="text-purple-400">{totalMarks} pts</b> Exam Focus
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setActiveTab(2)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 border border-sky-500/20 transition"
              >
                Start Diagnostic Quiz &rarr;
              </button>
            </div>
          </div>
        )}

        {/* =========================================================================
            TAB 0: MATERIALS & INGESTION PIPELINE
           ========================================================================= */}
        {activeTab === 0 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <h2 className="text-lg font-bold text-white">Course Materials & Ingestion Pipeline</h2>
                <p className="text-xs text-slate-400">
                  Upload your digital syllabus, notes, and past exam papers to extract page-by-page text with pdfjs-dist.
                </p>
              </div>
              <button
                onClick={() => setShowPasteModal(true)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-500/10 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/20 transition flex items-center gap-1.5"
              >
                <FileText className="w-3.5 h-3.5" />
                <span>📝 Paste Text Directly</span>
              </button>
            </div>

            {/* 3 Clear Upload Boxes */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition">
                <div className="flex items-center gap-2 mb-2 text-sky-400 font-semibold text-sm">
                  <FileText className="w-4 h-4" />
                  <span>📘 1. Syllabus Document</span>
                </div>
                <p className="text-xs text-slate-400 mb-4">Defines examination units and core curriculum topics.</p>
                <label className="block w-full py-2.5 px-3 rounded-lg border border-dashed border-slate-700 hover:border-sky-500 text-center text-xs text-slate-300 cursor-pointer bg-slate-950 transition">
                  <Upload className="w-4 h-4 mx-auto mb-1 text-slate-400" />
                  <span>Upload Syllabus (.pdf, .txt)</span>
                  <input
                    type="file"
                    className="hidden"
                    accept=".pdf,.txt,.md"
                    onChange={e => handleFileUpload(e, "Syllabus")}
                  />
                </label>
              </div>

              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition">
                <div className="flex items-center gap-2 mb-2 text-emerald-400 font-semibold text-sm">
                  <BookOpen className="w-4 h-4" />
                  <span>📚 2. Notes & Textbook Chapters</span>
                </div>
                <p className="text-xs text-slate-400 mb-4">Grounded course text for citations and test question formulation.</p>
                <label className="block w-full py-2.5 px-3 rounded-lg border border-dashed border-slate-700 hover:border-emerald-500 text-center text-xs text-slate-300 cursor-pointer bg-slate-950 transition">
                  <Upload className="w-4 h-4 mx-auto mb-1 text-slate-400" />
                  <span>Upload Notes / Chapters</span>
                  <input
                    type="file"
                    className="hidden"
                    multiple
                    accept=".pdf,.txt,.md"
                    onChange={e => handleFileUpload(e, "Study Notes")}
                  />
                </label>
              </div>

              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition">
                <div className="flex items-center gap-2 mb-2 text-purple-400 font-semibold text-sm">
                  <Award className="w-4 h-4" />
                  <span>📝 3. Previous Question Papers</span>
                </div>
                <p className="text-xs text-slate-400 mb-4">Maps past questions to calculate high-frequency exam weightage.</p>
                <label className="block w-full py-2.5 px-3 rounded-lg border border-dashed border-slate-700 hover:border-purple-500 text-center text-xs text-slate-300 cursor-pointer bg-slate-950 transition">
                  <Upload className="w-4 h-4 mx-auto mb-1 text-slate-400" />
                  <span>Upload Past Exam Papers</span>
                  <input
                    type="file"
                    className="hidden"
                    accept=".pdf,.txt,.md"
                    onChange={e => handleFileUpload(e, "Previous Question Paper")}
                  />
                </label>
              </div>
            </div>

            {/* Document Library Repository */}
            <div className="rounded-xl bg-slate-900 border border-slate-800 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-sm text-slate-200 flex items-center gap-2">
                  <span>Course Material Repository</span>
                  <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full font-mono">
                    {documents.length} Files Stored
                  </span>
                </h3>
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleClearAll}
                    className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1 font-medium"
                    title="Clear all documents"
                  >
                    <Trash2 className="w-3 h-3" />
                    <span>Clear All</span>
                  </button>
                  <button
                    onClick={handleResetToSample}
                    className="text-xs text-sky-400 hover:text-sky-300 flex items-center gap-1 font-medium"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>Reset to Demo Course</span>
                  </button>
                </div>
              </div>

              {documents.length === 0 ? (
                <div className="py-8 text-center text-slate-500 text-xs">
                  No materials uploaded. Click "Load Demo ML Course" above or upload your PDF files.
                </div>
              ) : (
                <div className="divide-y divide-slate-800">
                  {documents.map(doc => (
                    <div key={doc.id} className="py-3 flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center text-slate-300">
                          <FileText className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="text-xs font-semibold text-slate-200 flex items-center gap-2">
                            {doc.filename}
                            <span className="text-[10px] font-medium bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded">
                              {doc.doc_type}
                            </span>
                            <span className="text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3" /> pdfjs-dist
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 mt-0.5">
                            Pages: <b className="text-slate-400">{doc.page_count}</b> &bull; Added:{" "}
                            {doc.created_at.slice(0, 10)}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setViewingDoc(doc)}
                          className="px-2.5 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition flex items-center gap-1"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>View Text</span>
                        </button>
                        <button
                          onClick={() => handleDeleteDocument(doc.id)}
                          className="p-1 text-slate-500 hover:text-rose-400 transition"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* =========================================================================
            TAB 1: SYLLABUS MAP & EXAM WEIGHTAGE
           ========================================================================= */}
        {activeTab === 1 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold text-white">Syllabus Structure & Exam Weightage</h2>
              <p className="text-xs text-slate-400">
                Syllabus topics parsed and mapped against past exam questions to calculate topic frequency and mark allocation.
              </p>
            </div>

            {/* Metrics Row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
                <span className="text-xs text-slate-400">Identified Syllabus Topics</span>
                <div className="text-2xl font-bold text-white mt-1">{topics.length}</div>
                <span className="text-[11px] text-slate-500">Discrete academic modules</span>
              </div>
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
                <span className="text-xs text-slate-400">Total Exam Marks Mapped</span>
                <div className="text-2xl font-bold text-emerald-400 mt-1">
                  {totalMarks > 0 ? `${totalMarks} pts` : "Balanced Distribution"}
                </div>
                <span className="text-[11px] text-slate-500">
                  {totalMarks > 0 ? "From uploaded past papers" : "Equal curriculum weight"}
                </span>
              </div>
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
                <span className="text-xs text-slate-400">Highest Weight Exam Topic</span>
                <div className="text-sm font-semibold text-sky-400 mt-1 truncate" title={highestTopic}>
                  {highestTopic}
                </div>
                <span className="text-[11px] text-slate-500">Key exam driver</span>
              </div>
            </div>

            {/* Topic & Weightage Table */}
            <div className="rounded-xl bg-slate-900 border border-slate-800 overflow-hidden shadow-sm">
              <div className="p-4 border-b border-slate-800 font-semibold text-sm text-slate-200">
                Course Topics & Exam Priority Ranking
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider text-[10px]">
                    <tr>
                      <th className="py-3 px-4">Unit / Chapter</th>
                      <th className="py-3 px-4">Topic Name</th>
                      <th className="py-3 px-4 text-center">Past Questions</th>
                      <th className="py-3 px-4 text-right">Exam Weight (%)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {topics.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="py-8 text-center text-slate-500 text-xs">
                          No topics found yet. Upload your syllabus or notes in Tab 1, or click "Load Demo ML Course".
                        </td>
                      </tr>
                    ) : (
                      topics.map(t => {
                        const w = weightage[t.name] || { count: 0, total_marks: 0, percentage: 0 };
                        return (
                          <tr key={t.name} className="hover:bg-slate-800/40 transition">
                            <td className="py-3 px-4 text-slate-400 font-medium">{t.unit}</td>
                            <td className="py-3 px-4 text-slate-200 font-medium">{t.name}</td>
                            <td className="py-3 px-4 text-center font-mono text-slate-300">{w.count}</td>
                            <td className="py-3 px-4 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <div className="w-16 bg-slate-800 h-2 rounded-full overflow-hidden">
                                  <div
                                    className="bg-sky-500 h-full rounded-full"
                                    style={{ width: `${Math.min(100, w.percentage * 4)}%` }}
                                  />
                                </div>
                                <span className="font-mono font-bold text-sky-400 w-10 text-right">
                                  {w.percentage}%
                                </span>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            TAB 2: DIAGNOSTIC QUIZ
           ========================================================================= */}
        {activeTab === 2 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <h2 className="text-lg font-bold text-white">Diagnostic Assessment</h2>
                <p className="text-xs text-slate-400">
                  Questions are generated directly from your uploaded materials with exact textbook citations.
                </p>
              </div>

              <button
                onClick={handleGenerateQuiz}
                disabled={loadingAction.length > 0}
                className="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-white font-medium text-xs transition flex items-center gap-2 shadow-lg shadow-sky-500/20"
              >
                <Sparkles className="w-4 h-4" />
                <span>{quiz ? "Generate New Questions" : "Generate Diagnostic Quiz"}</span>
              </button>
            </div>

            {loadingAction && (
              <div className="p-8 rounded-xl bg-slate-900 border border-slate-800 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin text-sky-400" />
                <span>{loadingAction}</span>
              </div>
            )}

            {!quiz && !loadingAction && (
              <div className="p-12 text-center rounded-xl bg-slate-900 border border-slate-800">
                <HelpCircle className="w-10 h-10 mx-auto text-slate-600 mb-3" />
                <h3 className="font-semibold text-sm text-slate-200">No active test session</h3>
                <p className="text-xs text-slate-500 mt-1 mb-4">
                  Click the button above to formulate diagnostic questions grounded strictly in your notes.
                </p>
                <button
                  onClick={handleGenerateQuiz}
                  className="px-4 py-2 rounded-lg bg-sky-500 text-white text-xs font-medium hover:bg-sky-400 transition"
                >
                  Start Assessment
                </button>
              </div>
            )}

            {quiz && !loadingAction && (
              <div className="space-y-4">
                {quiz.map((q, qIdx) => (
                  <div key={q.id} className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-sky-400">Question {qIdx + 1} of {quiz.length}</span>
                      <span className="text-[11px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">
                        Topic: {q.topic}
                      </span>
                    </div>

                    <h4 className="text-sm font-semibold text-slate-100">{q.question}</h4>

                    <div className="space-y-2 pt-1">
                      {q.options.map((opt, optIdx) => {
                        const isSelected = userAnswers[String(q.id)] === opt;
                        let optionStyle = "border-slate-800 hover:border-slate-700 bg-slate-950/60";
                        if (quizSubmitted) {
                          if (opt === q.answer) optionStyle = "border-emerald-500 bg-emerald-500/10 text-emerald-300";
                          else if (isSelected && opt !== q.answer) optionStyle = "border-rose-500 bg-rose-500/10 text-rose-300";
                        } else if (isSelected) {
                          optionStyle = "border-sky-500 bg-sky-500/10 text-sky-300";
                        }

                        return (
                          <button
                            key={optIdx}
                            disabled={quizSubmitted}
                            onClick={() => setUserAnswers(prev => ({ ...prev, [String(q.id)]: opt }))}
                            className={`w-full text-left p-3 rounded-lg border text-xs transition flex items-center justify-between ${optionStyle}`}
                          >
                            <span>{opt}</span>
                            {isSelected && <span className="w-2 h-2 rounded-full bg-sky-400 ml-2" />}
                          </button>
                        );
                      })}
                    </div>

                    <div className="pt-2 flex items-center justify-between text-[11px] text-slate-500 border-t border-slate-800/80">
                      <span className="inline-flex items-center gap-1 text-slate-400">
                        <ShieldCheck className="w-3.5 h-3.5 text-sky-400" />
                        Grounded Citation: <b className="text-slate-300">[{q.citation}]</b>
                      </span>
                      {quizSubmitted && (
                        <span className="text-emerald-400 font-medium">
                          {userAnswers[String(q.id)] === q.answer ? "✅ Correct" : "❌ Missed"}
                        </span>
                      )}
                    </div>
                  </div>
                ))}

                {!quizSubmitted ? (
                  <div className="pt-2">
                    <button
                      onClick={handleSubmitQuiz}
                      className="w-full py-3 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 font-bold text-white text-sm shadow-lg shadow-sky-500/20 transition"
                    >
                      Submit Assessment & Diagnose Gaps &rarr;
                    </button>
                  </div>
                ) : (
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
                    <div>
                      <span className="text-xs text-slate-400">Assessment Complete</span>
                      <div className="text-sm font-bold text-white">
                        Score: {quizResults.filter(r => r.is_correct).length} / {quiz.length}
                      </div>
                    </div>
                    <button
                      onClick={() => setActiveTab(3)}
                      className="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-xs font-semibold transition"
                    >
                      View Gap Diagnosis Report &rarr;
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* =========================================================================
            TAB 3: GAP DIAGNOSIS REPORT (CORE OUTPUT)
           ========================================================================= */}
        {activeTab === 3 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold text-white">Diagnostic Knowledge Gap Report</h2>
              <p className="text-xs text-slate-400">
                Main Diagnosis: Identifies what the student doesn't know, classified by weakness severity and exam impact.
              </p>
            </div>

            {!gapReport ? (
              <div className="p-12 text-center rounded-xl bg-slate-900 border border-slate-800">
                <AlertTriangle className="w-10 h-10 mx-auto text-amber-500 mb-2" />
                <h3 className="font-semibold text-sm text-slate-200">No Assessment Completed Yet</h3>
                <p className="text-xs text-slate-500 mt-1 mb-4">
                  Complete the diagnostic quiz in Tab 3 to initiate your clinical learning diagnosis.
                </p>
                <button
                  onClick={() => setActiveTab(2)}
                  className="px-4 py-2 rounded-lg bg-sky-500 text-white text-xs font-medium hover:bg-sky-400 transition"
                >
                  Take Diagnostic Quiz
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Metric KPIs */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
                    <span className="text-xs text-slate-400">Overall Mastery</span>
                    <div className="text-2xl font-bold text-sky-400 mt-1">{gapReport.overall_percentage}%</div>
                    <span className="text-[11px] text-slate-500">Based on grounded test recall</span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
                    <span className="text-xs text-slate-400">Critical Knowledge Gaps</span>
                    <div className="text-2xl font-bold text-rose-400 mt-1">{gapReport.weak.length}</div>
                    <span className="text-[11px] text-slate-500">Require immediate revision</span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
                    <span className="text-xs text-slate-400">Mastered Concepts</span>
                    <div className="text-2xl font-bold text-emerald-400 mt-1">{gapReport.strong.length}</div>
                    <span className="text-[11px] text-slate-500">Exam ready recall</span>
                  </div>
                </div>

                {/* Clinical Diagnosis Statement */}
                <div className="p-4 rounded-xl bg-slate-900/80 border border-sky-500/30 text-xs text-slate-200">
                  <b className="text-sky-400">Clinical Diagnosis Summary:</b> {gapReport.summary}
                </div>

                {/* Weak Knowledge Gaps */}
                <div className="space-y-3">
                  <h3 className="font-bold text-sm text-rose-400 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" />
                    <span>Critical Knowledge Gaps (High Priority)</span>
                  </h3>
                  {gapReport.weak.length === 0 ? (
                    <div className="p-3 text-xs text-slate-500 rounded-lg bg-slate-900 border border-slate-800">
                      No critical gaps detected in tested modules.
                    </div>
                  ) : (
                    gapReport.weak.map(item => (
                      <div key={item.topic} className="p-4 rounded-xl bg-slate-900 border border-rose-500/30 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 rounded">
                            {item.badge}
                          </span>
                          <span className="text-xs text-slate-400 font-mono">
                            Exam Weight: <b className="text-white">{item.exam_weightage}%</b> &bull; Accuracy:{" "}
                            <b className="text-rose-400">{item.accuracy}%</b>
                          </span>
                        </div>
                        <h4 className="text-sm font-semibold text-slate-100">{item.topic}</h4>
                        <p className="text-xs text-slate-300">
                          <b className="text-slate-400">Diagnostic Finding:</b> {item.diagnosis}
                        </p>
                      </div>
                    ))
                  )}
                </div>

                {/* Medium Focus Areas */}
                <div className="space-y-3">
                  <h3 className="font-bold text-sm text-amber-400 flex items-center gap-2">
                    <Clock className="w-4 h-4" />
                    <span>Developing Understanding (Consolidation Needed)</span>
                  </h3>
                  {gapReport.medium.length === 0 ? (
                    <div className="p-3 text-xs text-slate-500 rounded-lg bg-slate-900 border border-slate-800">
                      No topics in the medium range.
                    </div>
                  ) : (
                    gapReport.medium.map(item => (
                      <div key={item.topic} className="p-4 rounded-xl bg-slate-900 border border-amber-500/30 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded">
                            {item.badge}
                          </span>
                          <span className="text-xs text-slate-400 font-mono">
                            Exam Weight: <b className="text-white">{item.exam_weightage}%</b> &bull; Accuracy:{" "}
                            <b className="text-amber-400">{item.accuracy}%</b>
                          </span>
                        </div>
                        <h4 className="text-sm font-semibold text-slate-100">{item.topic}</h4>
                        <p className="text-xs text-slate-300">
                          <b className="text-slate-400">Diagnostic Finding:</b> {item.diagnosis}
                        </p>
                      </div>
                    ))
                  )}
                </div>

                {/* Button to proceed to revision plan */}
                <div className="pt-2">
                  <button
                    onClick={() => setActiveTab(4)}
                    className="w-full py-3 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 text-white font-bold text-xs shadow-md transition"
                  >
                    View Targeted Multi-Day Revision Plan &rarr;
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =========================================================================
            TAB 4: REVISION ROADMAP
           ========================================================================= */}
        {activeTab === 4 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold text-white">Targeted Adaptive Revision Plan</h2>
              <p className="text-xs text-slate-400">
                Budgets available revision time dynamically based on weakness severity and exam weightage across all days.
              </p>
            </div>

            {/* Availability Sliders */}
            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-2">
                  Days Until Examination: <b className="text-sky-400">{revDays} Days</b>
                </label>
                <input
                  type="range"
                  min="1"
                  max="14"
                  value={revDays}
                  onChange={e => setRevDays(parseInt(e.target.value))}
                  className="w-full accent-sky-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-2">
                  Available Daily Hours: <b className="text-emerald-400">{revHours} hrs / day</b>
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="8.0"
                  step="0.5"
                  value={revHours}
                  onChange={e => setRevHours(parseFloat(e.target.value))}
                  className="w-full accent-emerald-500"
                />
              </div>

              <div className="flex items-center justify-between md:justify-end gap-3">
                <div className="text-right">
                  <span className="text-[11px] text-slate-500 block">Total Budget</span>
                  <span className="text-lg font-bold text-white font-mono">{Math.round(revDays * revHours * 10) / 10} hrs</span>
                </div>
                <button
                  onClick={handleRegeneratePlan}
                  className="px-3.5 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-xs font-semibold transition"
                >
                  Recalculate
                </button>
              </div>
            </div>

            {!revisionPlan ? (
              <div className="p-8 text-center rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-400">
                Complete a diagnostic quiz or click "Recalculate" to generate your roadmap.
              </div>
            ) : (
              <div className="space-y-6">
                {revisionPlan.schedule.map(dayItem => (
                  <div key={dayItem.day} className="space-y-3">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                      <h3 className="font-bold text-sm text-white flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-sky-400" />
                        <span>{dayItem.day}</span>
                      </h3>
                      <span className="text-xs font-mono font-bold text-sky-400 bg-sky-500/10 px-2.5 py-0.5 rounded-full border border-sky-500/20">
                        {dayItem.total_hours} Hours Allocated
                      </span>
                    </div>

                    <div className="grid grid-cols-1 gap-3">
                      {dayItem.sessions.map((session, sIdx) => {
                        let badgeColor = "bg-slate-800 text-slate-400 border-slate-700";
                        if (session.badge.includes("Weak")) badgeColor = "bg-rose-500/10 text-rose-400 border-rose-500/20";
                        else if (session.badge.includes("Medium")) badgeColor = "bg-amber-500/10 text-amber-400 border-amber-500/20";
                        else if (session.badge.includes("Mastered")) badgeColor = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";

                        return (
                          <div
                            key={sIdx}
                            className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2 hover:border-slate-700 transition"
                          >
                            <div className="flex items-center justify-between flex-wrap gap-2">
                              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${badgeColor}`}>
                                {session.badge}
                              </span>
                              <span className="text-xs font-mono text-slate-400">
                                Allocated: <b className="text-emerald-400">{session.allocated_hours} hrs</b> &bull; Exam Weight:{" "}
                                <b className="text-slate-200">{session.exam_weight}%</b>
                              </span>
                            </div>

                            <h4 className="font-semibold text-sm text-slate-100">{session.topic}</h4>

                            <div className="pt-2">
                              <span className="text-[11px] font-semibold text-slate-400 block mb-1">Action Plan:</span>
                              <ul className="space-y-1 text-xs text-slate-300">
                                {session.tasks.map((task, tIdx) => (
                                  <li key={tIdx} className="flex items-start gap-2">
                                    <span className="text-sky-400 font-bold">&bull;</span>
                                    <span>{task}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* =========================================================================
            TAB 5: GROUNDED ASSISTANT
           ========================================================================= */}
        {activeTab === 5 && (
          <div className="space-y-4 max-w-4xl mx-auto">
            <div>
              <h2 className="text-lg font-bold text-white">Grounded Explain-This-Topic Assistant</h2>
              <p className="text-xs text-slate-400">
                Answers strictly from retrieved textbook notes. If information is absent, returns "Not found in your uploaded material."
              </p>
            </div>

            {/* Quick Topic Chips */}
            {topics.length > 0 && (
              <div className="space-y-1.5">
                <span className="text-[11px] text-slate-400 font-semibold">Quick Inquiries from Syllabus:</span>
                <div className="flex flex-wrap gap-1.5">
                  {topics.slice(0, 6).map(t => (
                    <button
                      key={t.name}
                      onClick={() => handleSendMessage(`Explain ${t.name} and its core mechanisms`)}
                      className="px-2.5 py-1 text-xs rounded-lg bg-slate-900 border border-slate-800 text-slate-300 hover:border-sky-500 hover:text-sky-300 transition"
                    >
                      {t.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Chat Messages */}
            <div className="min-h-[350px] max-h-[500px] overflow-y-auto space-y-3 p-4 rounded-xl bg-slate-900 border border-slate-800">
              {chatMessages.length === 0 ? (
                <div className="h-48 flex flex-col items-center justify-center text-slate-500 text-xs">
                  <MessageSquare className="w-8 h-8 mb-2 text-slate-600" />
                  <span>Ask any question regarding your syllabus. Answers are strictly evidence-grounded.</span>
                </div>
              ) : (
                chatMessages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`p-3.5 rounded-xl text-xs ${
                      msg.role === "user"
                        ? "bg-sky-500/10 border border-sky-500/20 text-sky-200 ml-8"
                        : "bg-slate-950 border border-slate-800 text-slate-200 mr-8 space-y-2"
                    }`}
                  >
                    <div className="whitespace-pre-line leading-relaxed">{msg.content}</div>
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="pt-2 text-[11px] text-sky-400 border-t border-slate-800/80 flex items-center gap-1 font-medium">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        <span>Verified Citations: {msg.citations.join(", ")}</span>
                      </div>
                    )}
                  </div>
                ))
              )}
              {chatLoading && (
                <div className="p-3 text-xs text-slate-400 flex items-center gap-2">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-sky-400" />
                  <span>Retrieving notes and drafting grounded explanation...</span>
                </div>
              )}
            </div>

            {/* Input Bar */}
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Ask about a syllabus concept..."
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSendMessage()}
                className="flex-1 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
              />
              <button
                onClick={() => handleSendMessage()}
                disabled={chatLoading || !chatInput.trim()}
                className="px-4 py-2.5 rounded-xl bg-sky-500 hover:bg-sky-400 disabled:opacity-50 text-white font-semibold text-xs transition"
              >
                Send
              </button>
            </div>
          </div>
        )}

        {/* =========================================================================
            TAB 6: PERFORMANCE TRACKER
           ========================================================================= */}
        {activeTab === 6 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold text-white">Student Longitudinal Performance Tracker</h2>
              <p className="text-xs text-slate-400">
                Track how test accuracy and diagnostic gaps evolve over successive assessment cycles.
              </p>
            </div>

            {attempts.length === 0 ? (
              <div className="p-12 text-center rounded-xl bg-slate-900 border border-slate-800">
                <Award className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                <h3 className="font-semibold text-sm text-slate-200">No Assessment Records Yet</h3>
                <p className="text-xs text-slate-500 mt-1 mb-4">
                  Complete a diagnostic quiz to start tracking your knowledge improvement across attempts.
                </p>
                <button
                  onClick={() => setActiveTab(2)}
                  className="px-4 py-2 rounded-lg bg-sky-500 text-white text-xs font-medium hover:bg-sky-400 transition"
                >
                  Take First Quiz
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
                    <span className="text-xs text-slate-400">Assessments Completed</span>
                    <div className="text-2xl font-bold text-white mt-1">{attempts.length}</div>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
                    <span className="text-xs text-slate-400">Latest Assessment Score</span>
                    <div className="text-2xl font-bold text-emerald-400 mt-1">
                      {attempts[attempts.length - 1].percentage}%
                    </div>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
                    <span className="text-xs text-slate-400">Average Historical Mastery</span>
                    <div className="text-2xl font-bold text-sky-400 mt-1">
                      {Math.round(attempts.reduce((a, b) => a + b.percentage, 0) / attempts.length)}%
                    </div>
                  </div>
                </div>

                <div className="rounded-xl bg-slate-900 border border-slate-800 overflow-hidden shadow-sm">
                  <div className="p-4 border-b border-slate-800 font-semibold text-sm text-slate-200">
                    Assessment History Log
                  </div>
                  <div className="divide-y divide-slate-800 text-xs">
                    {attempts.map(att => (
                      <div key={att.id} className="p-3.5 flex items-center justify-between">
                        <div>
                          <span className="font-bold text-white">Attempt #{att.attempt_number}</span>
                          <span className="text-slate-500 text-[11px] ml-3">{att.created_at}</span>
                        </div>
                        <div className="flex items-center gap-3 font-mono">
                          <span className="text-slate-400">
                            {att.score} / {att.total_questions} correct
                          </span>
                          <span className="font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                            {att.percentage}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Modal: View Extracted Document Text */}
      {viewingDoc && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 space-y-4 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="font-bold text-sm text-white">{viewingDoc.filename}</h3>
                <span className="text-xs text-slate-400">
                  {viewingDoc.doc_type} &bull; {viewingDoc.page_count} Pages
                </span>
              </div>
              <button
                onClick={() => setViewingDoc(null)}
                className="text-slate-400 hover:text-white text-sm font-bold"
              >
                &times;
              </button>
            </div>
            <div className="flex-1 overflow-y-auto bg-slate-950 p-4 rounded-xl border border-slate-800/80 text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">
              {viewingDoc.extracted_text}
            </div>
            <div className="flex justify-end pt-2">
              <button
                onClick={() => setViewingDoc(null)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Groq API Key Configuration */}
      {showKeyModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <Key className="w-4 h-4 text-amber-400" />
                <span>Configure Groq API Key</span>
              </h3>
              <button
                onClick={() => setShowKeyModal(false)}
                className="text-slate-400 hover:text-white text-sm font-bold"
              >
                &times;
              </button>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Enter your Groq key from{" "}
              <a href="https://console.groq.com/keys" target="_blank" className="text-sky-400 underline">
                console.groq.com/keys
              </a>
              . Powered by <code className="text-amber-300">llama-3.3-70b-versatile</code> for sub-second diagnostic generation.
            </p>

            <input
              type="password"
              placeholder="gsk_..."
              value={groqKey}
              onChange={e => setGroqKey(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-sky-500"
            />

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowKeyModal(false)}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 transition"
              >
                Cancel
              </button>
              <button
                onClick={() => setShowKeyModal(false)}
                className="px-3.5 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-xs text-white font-medium transition"
              >
                Save Key
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Modal: Paste Text Directly */}
      {showPasteModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-400" />
                <span>Paste Study Material Text</span>
              </h3>
              <button
                onClick={() => setShowPasteModal(false)}
                className="text-slate-400 hover:text-white text-sm font-bold"
              >
                &times;
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Document Category</label>
                <select
                  value={pasteDocType}
                  onChange={e => setPasteDocType(e.target.value as any)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-sky-500"
                >
                  <option value="Syllabus">📘 Syllabus (Units & Topics)</option>
                  <option value="Study Notes">📚 Study Notes & Textbook Excerpts</option>
                  <option value="Previous Question Paper">📝 Previous Question Paper</option>
                </select>
              </div>

              <div>
                <label className="text-xs text-slate-400 block mb-1">Document Title</label>
                <input
                  type="text"
                  placeholder="e.g. Unit 1 Machine Learning Notes"
                  value={pasteTitle}
                  onChange={e => setPasteTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="text-xs text-slate-400 block mb-1">Paste Course Content</label>
                <textarea
                  rows={8}
                  placeholder="Paste your syllabus outline, chapter text, lecture notes, or exam questions here..."
                  value={pasteContent}
                  onChange={e => setPasteContent(e.target.value)}
                  className="w-full p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-sky-500 font-mono"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowPasteModal(false)}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleSavePastedText}
                disabled={!pasteContent.trim()}
                className="px-4 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 disabled:opacity-50 text-xs text-white font-medium transition"
              >
                Save & Ingest
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
