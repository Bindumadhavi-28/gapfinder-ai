export interface DocumentRecord {
  id: string;
  filename: string;
  doc_type: "Syllabus" | "Study Notes" | "Textbook Chapter" | "Previous Question Paper";
  page_count: number;
  status: "Success" | "OCR Required" | "Error";
  extracted_text: string;
  pages?: { pageNumber: number; text: string }[];
  created_at: string;
}

export interface Chunk {
  citation: string;
  content: string;
}

export interface Topic {
  name: string;
  unit: string;
  raw?: string;
}

export interface TopicWeight {
  count: number;
  total_marks: number;
  percentage: number;
  questions: string[];
}

export interface QuizQuestion {
  id: number;
  topic: string;
  question: string;
  options: string[];
  answer: string;
  citation: string;
  explanation: string;
}

export interface MistakeDetail {
  question: string;
  user_ans: string;
  correct_ans: string;
  citation: string;
  explanation: string;
}

export interface TopicScore {
  correct: number;
  total: number;
  mistakes: MistakeDetail[];
}

export interface GapTopicItem {
  topic: string;
  accuracy: number;
  correct: number;
  total: number;
  exam_weightage: number;
  status: "Weak" | "Medium" | "Strong";
  badge: string;
  diagnosis: string;
  mistakes: MistakeDetail[];
}

export interface GapReport {
  overall_percentage: number;
  weak: GapTopicItem[];
  medium: GapTopicItem[];
  strong: GapTopicItem[];
  summary: string;
}

export interface RevisionSession {
  topic: string;
  badge: string;
  allocated_hours: number;
  priority_score: number;
  exam_weight: number;
  tasks: string[];
}

export interface RevisionDay {
  day: string;
  total_hours: number;
  sessions: RevisionSession[];
}

export interface RevisionPlan {
  total_days: number;
  hours_per_day: number;
  total_hours: number;
  schedule: RevisionDay[];
}

export interface AssessmentAttempt {
  id: string;
  attempt_number: number;
  score: number;
  total_questions: number;
  percentage: number;
  created_at: string;
}

export interface UserProfile {
  name: string;
  email: string;
  role: "Student" | "Instructor" | "Evaluator";
  targetSubject?: string;
}
