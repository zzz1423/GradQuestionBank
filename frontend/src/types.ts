export interface Subject {
  id: number;
  name: string;
  created_at: string;
  chapter_count?: number;
  kp_count?: number;
  question_count?: number;
}

export interface Chapter {
  id: number;
  subject_id: number;
  name: string;
  sort_order: number;
  created_at: string;
  kp_count?: number;
  subject_name?: string;
}

export interface KnowledgePoint {
  id: number;
  chapter_id: number;
  name: string;
  description?: string;
  sort_order: number;
  created_at: string;
  chapter_name?: string;
  chapter?: string;
  subject_name?: string;
  question_count?: number;
  role?: string;
  weight?: number;
}

export interface Question {
  id: number;
  subject_id: number;
  content: string;
  answer?: string;
  source?: string;
  mastery_level: number;
  created_at: string;
  updated_at: string;
  subject_name?: string;
  knowledge_points?: KnowledgePoint[];
}

export interface Tag { name: string }

export interface WeakPoint {
  name: string;
  chapter_name: string;
  subject_name: string;
  total: number;
  weakness_score: number;
  mastery_rate: number;
  weighted_mastered: number;
  weighted_fuzzy: number;
  weighted_weak: number;
}

export interface MasteryDist { mastery_level: number; count: number }
export interface SubjectStat { name: string; mastery_level: number; count: number }

export interface DashboardData {
  stats: {
    subjects: number; chapters: number; knowledge_points: number;
    questions: number; mastered: number; fuzzy: number; weak: number;
  };
  recent_questions: Question[];
}

export interface AnalysisResult {
  content?: string; latex_content?: string; answer?: string;
  knowledge_points: { name: string; role: string; weight: number; chapter?: string; is_new?: boolean }[];
  tags: string[]; error?: string;
}

export interface ReviewData {
  question: Question;
  all_kps: KnowledgePoint[];
  linked_kps: { id: number; name: string; chapter: string; role: string; weight: number }[];
}

export const MASTERY_LABELS: Record<number, string> = {
  0: '未标记', 1: '完全不会', 2: '模糊', 3: '已掌握',
};
export const MASTERY_COLORS: Record<number, string> = {
  0: 'secondary', 1: 'danger', 2: 'warning', 3: 'success',
};

// ── PDF Import Task ────────────────────────────────────────

export interface ImportTask {
  task_id: string;
  pdf_name: string;
  pdf_path: string;
  output_directory: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  current_step: string;
  current_question: number;
  total_questions: number;
  start_time: string;
  finish_time: string;
  elapsed_seconds: number;
  error_message: string;
  created_at: string;
}

export interface PdfImportQuestion {
  subject_name: string;
  content: string;
  source: string;
  knowledge_points: {
    name: string;
    chapter: string;
    role: string;
    weight: number;
  }[];
}