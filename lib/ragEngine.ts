import { Chunk, DocumentRecord, GapReport, GapTopicItem, QuizQuestion, RevisionPlan, Topic, TopicScore, TopicWeight } from "./types";

/**
 * Robust multi-delimiter topic parser.
 * Extracts topics from syllabus, with automatic fallback to study notes if no syllabus is provided.
 */
export function parseTopics(syllabusText: string, notesFallbackText = ""): Topic[] {
  let topics: Topic[] = [];
  const raw = (syllabusText || "").trim();

  function extractFromText(text: string, defaultUnit: string): Topic[] {
    const list: Topic[] = [];
    let cleaned = text.replace(/(Unit\s+\d+[\s\-\–:]*|Chapter\s+\d+[\s\-\–:]*|Module\s+\d+[\s\-\–:]*)/gi, "\n__UNIT__:$1");
    cleaned = cleaned.replace(/[\u2022\u25cf\u25aa\u25cb•▪▫]\s*/g, "\n__BULLET__:");
    cleaned = cleaned.replace(/(?<=[.;\n])\s*(\d+[\.\)])\s+/g, "\n__NUM__:$1 ");

    const lines = cleaned.split("\n");
    let currentUnit = defaultUnit;
    const seenNames = new Set<string>();

    const noisePatterns = [
      /^\[Page\s+\d+\]/i, /^\[SOURCE:/i, /^course information/i, /^subject:/i, /^level:/i,
      /^total:\s*\d+/i, /^instructions/i, /^time:/i, /^maximum marks/i,
      /^sample syllabus/i, /^learning outcomes/i, /^credit/i, /^semester/i
    ];

    for (let line of lines) {
      line = line.trim();
      if (!line || line.length < 4) continue;
      if (noisePatterns.some(p => p.test(line))) continue;

      if (line.startsWith("__UNIT__:")) {
        const unitHdr = line.replace("__UNIT__:", "").trim().replace(/[\.:\–\-]+$/, "");
        if (unitHdr) currentUnit = unitHdr;
      } else if (line.startsWith("__BULLET__:") || line.startsWith("__NUM__:")) {
        let tName = line.replace(/^(__BULLET__|__NUM__):[\d\.\s\-\*•\)]*/, "").trim();
        tName = tName.replace(/[\.;]+$/, "").trim();

        const subParts = tName.includes(";") ? tName.split(";").map(p => p.trim()) : [tName];
        for (let part of subParts) {
          part = part.replace(/^[-*•\d\.\)]+\s*/, "").replace(/[\.;]+$/, "").trim();
          if (part.length >= 4 && part.length <= 120 && !seenNames.has(part.toLowerCase())) {
            if (!noisePatterns.some(p => p.test(part))) {
              seenNames.add(part.toLowerCase());
              list.push({ unit: currentUnit, name: part, raw: line });
            }
          }
        }
      } else {
        if (/^(UNIT|CHAPTER|MODULE)/i.test(line)) {
          currentUnit = line.includes(":") ? line.split(":", 2)[1].trim() : line;
        } else {
          const cleanL = line.replace(/^[\d\.\s\-\*•\)]+/, "").replace(/[\.;]+$/, "").trim();
          if (cleanL.length >= 4 && cleanL.length <= 120 && !seenNames.has(cleanL.toLowerCase())) {
            if (!noisePatterns.some(p => p.test(cleanL))) {
              seenNames.add(cleanL.toLowerCase());
              list.push({ unit: currentUnit, name: cleanL, raw: line });
            }
          }
        }
      }
    }

    return list;
  }

  if (raw) {
    topics = extractFromText(raw, "Core Unit");
  }

  // Automatic Fallback: If syllabus was not provided or empty, extract topics directly from study notes!
  if (topics.length === 0 && notesFallbackText.trim()) {
    topics = extractFromText(notesFallbackText.trim(), "Course Module");
    if (topics.length === 0) {
      const candidateLines = notesFallbackText.split("\n")
        .map(l => l.trim().replace(/^\[Page\s+\d+\]/i, "").trim())
        .filter(l => l.length > 5 && l.length < 80);
      for (const c of candidateLines.slice(0, 10)) {
        topics.push({ unit: "Course Concepts", name: c, raw: c });
      }
    }
  }

  return topics;
}

/**
 * Splits past questions on inline bullets and numbering.
 */
export function splitQuestions(pastPapersText: string): string[] {
  let cleaned = (pastPapersText || "").replace(/[\u2022\u25cf\u25aa\u25cb•▪▫]\s*/g, "\n__Q__:");
  cleaned = cleaned.replace(/(?<=[.;\n])\s*(\d+[\.\)])\s+/g, "\n__Q__:$1 ");

  const noise = ["instructions", "maximum marks", "time:", "section a", "section b", "section c", "[page"];
  const questions: string[] = [];

  for (let l of cleaned.split("\n")) {
    l = l.trim();
    if (l.startsWith("__Q__:")) l = l.replace("__Q__:", "").trim();
    if (l.length > 10 && !noise.some(k => l.toLowerCase().includes(k))) {
      questions.push(l);
    }
  }
  return questions;
}

/**
 * Calculates exam weightage and total marks by mapping questions to topics.
 */
export function calculateExamWeightage(topics: Topic[], pastPapersText: string): Record<string, TopicWeight> {
  const weightage: Record<string, TopicWeight> = {};
  for (const t of topics) {
    weightage[t.name] = { count: 0, total_marks: 0, percentage: 0, questions: [] };
  }

  const questions = splitQuestions(pastPapersText);

  for (const q of questions) {
    const marksMatch = q.match(/(\d+)\s*Marks?/i);
    const marks = marksMatch ? parseInt(marksMatch[1], 10) : 2;
    const qLower = q.toLowerCase();

    let bestTopic: string | null = null;
    let maxOverlap = 0;

    for (const t of topics) {
      const keywords = (t.name.toLowerCase().match(/\w+/g) || []).filter(w => w.length > 3);
      const overlap = keywords.filter(w => qLower.includes(w)).length;
      if (overlap > maxOverlap) {
        maxOverlap = overlap;
        bestTopic = t.name;
      }
    }

    if (bestTopic && maxOverlap > 0) {
      weightage[bestTopic].count += 1;
      weightage[bestTopic].total_marks += marks;
      weightage[bestTopic].questions.push(q);
    }
  }

  const totalMarks = Object.values(weightage).reduce((sum, v) => sum + v.total_marks, 0);
  if (totalMarks > 0) {
    for (const t of topics) {
      const marks = weightage[t.name].total_marks;
      weightage[t.name].percentage = marks > 0 ? Math.round((marks / totalMarks) * 1000) / 10 : Math.round((20.0 / Math.max(1, topics.length)) * 10) / 10;
    }
  } else {
    const evenShare = Math.round((100.0 / Math.max(1, topics.length)) * 10) / 10;
    for (const t of topics) {
      weightage[t.name].percentage = evenShare;
    }
  }

  return weightage;
}

/**
 * Chunks notes with overlap, preserving exact [SOURCE: filename - Page X] citations.
 */
export function chunkNotes(notesText: string): Chunk[] {
  const chunks: Chunk[] = [];
  const sections = notesText.split(/(\[SOURCE:[^\]]+\])/);

  if (sections.length > 1) {
    for (let i = 1; i < sections.length; i += 2) {
      const citation = sections[i].replace("[SOURCE:", "").replace("]", "").trim();
      const content = (sections[i + 1] || "").trim();
      if (!content || content.length < 15) continue;

      const words = content.split(/\s+/);
      if (words.length > 130) {
        const chunkSize = 100;
        const overlap = 25;
        const step = chunkSize - overlap;
        let subIdx = 1;
        for (let start = 0; start < words.length; start += step) {
          const subWords = words.slice(start, start + chunkSize);
          if (subWords.length >= 15) {
            chunks.push({
              citation: words.length > 170 ? `${citation} (Part ${subIdx})` : citation,
              content: subWords.join(" ")
            });
            subIdx += 1;
          }
        }
      } else {
        chunks.push({ citation, content });
      }
    }
  } else {
    const rawChunks = notesText.split(/\n\s*\n+/).filter(p => p.trim().length > 20);
    rawChunks.forEach((p, idx) => {
      const firstWords = p.trim().split(/\s+/).slice(0, 4).join(" ");
      chunks.push({
        citation: `Notes Section ${idx + 1}: ${firstWords}...`,
        content: p.trim()
      });
    });
  }

  return chunks;
}

/**
 * Simple word-overlap retrieval returning topK relevant chunks.
 */
export function retrieveRelevantChunks(chunks: Chunk[], query: string, topK = 2): Chunk[] {
  if (!chunks || chunks.length === 0) return [];
  const queryTerms = (query.toLowerCase().match(/\w+/g) || []).filter(w => w.length > 3);
  if (queryTerms.length === 0) return chunks.slice(0, topK);

  const scored = chunks.map(chunk => {
    const chunkLower = chunk.content.toLowerCase();
    const score = queryTerms.reduce((acc, term) => acc + (chunkLower.includes(term) ? 1 : 0), 0);
    return { chunk, score };
  });

  scored.sort((a, b) => b.score - a.score);
  const relevant = scored.filter(s => s.score > 0).map(s => s.chunk);
  return relevant.length > 0 ? relevant.slice(0, topK) : chunks.slice(0, topK);
}

/**
 * Generates local diagnostic quiz directly from student's notes chunks.
 */
export function generateQuizLocal(chunks: Chunk[], topics: Topic[]): QuizQuestion[] {
  if (!chunks || chunks.length === 0) {
    const topicName = topics[0]?.name || "Core Subject Principles";
    return [
      {
        id: 1,
        topic: topicName,
        question: `Based on your course materials in '${topicName}', which statement accurately represents the core definition?`,
        options: [
          `Core foundational rule and mechanism established in '${topicName}'.`,
          `Auxiliary concept unrelated to the primary subject matter.`,
          `Deprecated syntax no longer supported in current implementations.`,
          `Isolated sub-routine executed strictly outside normal execution flow.`
        ],
        answer: `Core foundational rule and mechanism established in '${topicName}'.`,
        citation: "Uploaded Notes",
        explanation: `Diagnostic verification for understanding of '${topicName}'.`
      }
    ];
  }

  // Gather clean candidate sentences
  const candidates: { sentence: string; citation: string; fullChunk: string }[] = [];
  for (const c of chunks) {
    const sents = c.content.split(/[.\n;•]+/);
    for (const s of sents) {
      const clean = s.trim();
      const words = clean.split(/\s+/);
      if (words.length >= 6 && words.length <= 30 && clean.length >= 25) {
        const letters = clean.replace(/[^a-zA-Z]/g, "").length;
        if (letters / clean.length > 0.65) {
          candidates.push({ sentence: clean, citation: c.citation, fullChunk: c.content });
        }
      }
    }
  }

  const pool = candidates.length >= 4 ? candidates : chunks.map(c => ({ sentence: c.content.slice(0, 100), citation: c.citation, fullChunk: c.content }));
  const shuffled = [...pool].sort(() => 0.5 - Math.random());
  const selected = shuffled.slice(0, 4);

  return selected.map((item, idx) => {
    let matchedTopic = topics.length > 0 ? topics[0].name : "Core Concept";
    for (const t of topics) {
      const tWords = (t.name.toLowerCase().match(/\w+/g) || []).filter(w => w.length > 3);
      if (tWords.some(w => item.fullChunk.toLowerCase().includes(w))) {
        matchedTopic = t.name;
        break;
      }
    }

    const words = item.sentence.split(/\s+/);
    const concept = words.slice(0, 4).join(" ");
    const questionText = `According to [${item.citation}], which statement accurately describes '${concept}'?`;
    const correctOpt = item.sentence;

    const distractors = [
      `It operates independently without applying ${concept}.`,
      `This mechanism is superseded under standard linear assumptions.`,
      `The system bypasses this stage to minimize computation.`
    ];

    const options = [correctOpt, ...distractors].sort(() => 0.5 - Math.random());

    return {
      id: idx + 1,
      topic: matchedTopic,
      question: questionText,
      options,
      answer: correctOpt,
      citation: item.citation,
      explanation: `Grounded directly in ${item.citation}: '${item.sentence}'`
    };
  });
}

/**
 * Evaluates student quiz answers.
 */
export function evaluateAnswers(userAnswers: Record<string, string>, quiz: QuizQuestion[]) {
  const results = [];
  const topicScores: Record<string, TopicScore> = {};

  for (const q of quiz) {
    const qid = String(q.id);
    const userAns = (userAnswers[qid] || "").trim();
    const isCorrect = userAns.toLowerCase() === q.answer.trim().toLowerCase();

    if (!topicScores[q.topic]) {
      topicScores[q.topic] = { correct: 0, total: 0, mistakes: [] };
    }

    topicScores[q.topic].total += 1;
    if (isCorrect) {
      topicScores[q.topic].correct += 1;
    } else {
      topicScores[q.topic].mistakes.push({
        question: q.question,
        user_ans: userAns || "Skipped",
        correct_ans: q.answer,
        citation: q.citation,
        explanation: q.explanation
      });
    }

    results.push({
      id: q.id,
      topic: q.topic,
      question: q.question,
      user_answer: userAns,
      correct_answer: q.answer,
      is_correct: isCorrect,
      citation: q.citation,
      explanation: q.explanation
    });
  }

  return { results, topicScores };
}

/**
 * Builds the clinical Gap Report with Weak, Medium, and Strong categorizations.
 */
export function generateGapReport(
  topicScores: Record<string, TopicScore>,
  topics: Topic[],
  weightage: Record<string, TopicWeight>
): GapReport {
  const report: GapReport = {
    overall_percentage: 0,
    weak: [],
    medium: [],
    strong: [],
    summary: ""
  };

  let totalQ = 0;
  let totalC = 0;

  for (const [topic, data] of Object.entries(topicScores)) {
    totalQ += data.total;
    totalC += data.correct;
    const accuracy = data.total > 0 ? Math.round((data.correct / data.total) * 100) : 0;
    const examWeight = weightage[topic]?.percentage || Math.round((100 / Math.max(1, topics.length)) * 10) / 10;

    const item: GapTopicItem = {
      topic,
      accuracy,
      correct: data.correct,
      total: data.total,
      exam_weightage: examWeight,
      status: accuracy < 50 ? "Weak" : accuracy <= 75 ? "Medium" : "Strong",
      badge: accuracy < 50 ? "🔴 Weak" : accuracy <= 75 ? "🟡 Medium" : "🟢 Mastered",
      diagnosis:
        accuracy < 50
          ? `Critical Gap: Missed ${data.total - data.correct} of ${data.total} questions. Prioritize review.`
          : accuracy <= 75
          ? `Moderate Focus: Understood ${data.correct}/${data.total} concepts. Consolidate formulas.`
          : `Mastered: Strong recall (${data.correct}/${data.total} correct). Ready for advanced problems.`,
      mistakes: data.mistakes
    };

    if (item.status === "Weak") report.weak.push(item);
    else if (item.status === "Medium") report.medium.push(item);
    else report.strong.push(item);
  }

  report.overall_percentage = totalQ > 0 ? Math.round((totalC / totalQ) * 100) : 0;

  if (report.weak.length > 0) {
    const names = report.weak.map(w => w.topic).join(", ");
    report.summary = `Critical exam gaps detected in: ${names}. Focus study hours on these high-weight sections immediately.`;
  } else {
    report.summary = "Solid foundational grasp across tested modules. Ready for full exam simulations.";
  }

  return report;
}

/**
 * Generates balanced multi-day revision roadmap ensuring EVERY day receives sessions.
 */
export function generateRevisionPlan(
  gapReport: GapReport,
  allTopics: Topic[],
  weightage: Record<string, TopicWeight>,
  days = 5,
  hoursPerDay = 2.0
): RevisionPlan {
  days = Math.max(1, Math.floor(days));
  hoursPerDay = Math.max(0.5, hoursPerDay);

  const testedNames = new Set<string>();
  const planTopics: {
    topic: string;
    badge: string;
    priority_score: number;
    exam_weight: number;
    status: string;
    tasks?: string[];
  }[] = [];

  // 1. Weak topics
  for (const t of gapReport.weak) {
    testedNames.add(t.topic.toLowerCase());
    const examW = t.exam_weightage;
    const wFactor = (100 - t.accuracy) / 100.0;
    const pScore = Math.round(wFactor * (examW / 100.0) * 1000) / 10;
    planTopics.push({
      topic: t.topic,
      badge: "🔴 Weak",
      priority_score: Math.max(pScore, 18.0),
      exam_weight: examW,
      status: "Weak"
    });
  }

  // 2. Medium topics
  for (const t of gapReport.medium) {
    testedNames.add(t.topic.toLowerCase());
    const examW = t.exam_weightage;
    const wFactor = (100 - t.accuracy) / 100.0;
    const pScore = Math.round(wFactor * (examW / 100.0) * 1000) / 10;
    planTopics.push({
      topic: t.topic,
      badge: "🟡 Medium",
      priority_score: Math.max(pScore, 12.0),
      exam_weight: examW,
      status: "Medium"
    });
  }

  // 3. Untested syllabus topics (Coverage)
  for (const t of allTopics) {
    if (!testedNames.has(t.name.toLowerCase())) {
      const examW = weightage[t.name]?.percentage || Math.round((100 / Math.max(1, allTopics.length)) * 10) / 10;
      const pScore = Math.round(0.5 * (examW / 100.0) * 1000) / 10;
      planTopics.push({
        topic: t.name,
        badge: "⚪ Untested Syllabus",
        priority_score: Math.max(pScore, 6.0),
        exam_weight: examW,
        status: "Untested"
      });
    }
  }

  // 4. Strong topics
  for (const t of gapReport.strong) {
    testedNames.add(t.topic.toLowerCase());
    const examW = t.exam_weightage;
    planTopics.push({
      topic: t.topic,
      badge: "🟢 Mastered",
      priority_score: 3.0,
      exam_weight: examW,
      status: "Strong"
    });
  }

  planTopics.sort((a, b) => b.priority_score - a.priority_score);

  // Progressive milestone expansion if fewer topics than days
  let finalTopics = planTopics;
  if (finalTopics.length < days && finalTopics.length > 0) {
    const milestones = [
      ["Foundations & Definitions", "Read core textbook definitions", "Build flashcards"],
      ["Mechanism & Steps", "Study step-by-step mechanisms", "Solve 3 practice problems"],
      ["Exam Drill & Past Papers", "Practice past questions", "Check answer keys"],
      ["Pitfall & Trap Review", "Review common mistakes and edge cases", "Self-explanation"],
      ["Mock Test & Final Review", "Take a timed diagnostic assessment", "Confirm exam readiness"]
    ];
    finalTopics = [];
    for (let d = 0; d < days; d++) {
      const base = planTopics[d % planTopics.length];
      const m = milestones[d % milestones.length];
      finalTopics.push({
        topic: `${base.topic} — Phase: ${m[0]}`,
        badge: base.badge,
        priority_score: base.priority_score,
        exam_weight: base.exam_weight,
        status: base.status,
        tasks: [
          `${m[1]} on ${base.topic}`,
          `${m[2]} (${base.exam_weight}% exam weight)`,
          "Take a 3-question diagnostic self-check"
        ]
      });
    }
  }

  const daySchedule: any[][] = Array.from({ length: days }, () => []);
  finalTopics.forEach((t, idx) => {
    daySchedule[idx % days].push(t);
  });

  const scheduleOutput = daySchedule.map((dayItems, dIdx) => {
    const dayTotalP = dayItems.reduce((acc, item) => acc + item.priority_score, 0) || 1;
    const sessions = dayItems.map(item => {
      const share = item.priority_score / dayTotalP;
      const allocated = Math.max(0.5, Math.round(share * hoursPerDay * 10) / 10);
      const tasks = item.tasks || [
        `Review notes on ${item.topic}`,
        `Solve past questions (${item.exam_weight}% exam weight)`,
        `Complete a 3-question diagnostic self-check`
      ];
      return {
        topic: item.topic,
        badge: item.badge,
        allocated_hours: allocated,
        priority_score: item.priority_score,
        exam_weight: item.exam_weight,
        tasks
      };
    });

    const dayHours = Math.round(sessions.reduce((acc, s) => acc + s.allocated_hours, 0) * 10) / 10;
    return {
      day: `Day ${dIdx + 1}`,
      total_hours: dayHours,
      sessions
    };
  });

  const totalAllocated = Math.round(scheduleOutput.reduce((acc, d) => acc + d.total_hours, 0) * 10) / 10;

  return {
    total_days: days,
    hours_per_day: hoursPerDay,
    total_hours: totalAllocated,
    schedule: scheduleOutput
  };
}
