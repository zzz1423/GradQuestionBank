import type { DedupGroup } from './types';
﻿const BASE = '';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60000); // 60s timeout
  try {
    const res = await fetch(BASE + url, { ...init, signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${res.status}`);
    }
    return res.json();
  } catch (e) {
    clearTimeout(timeout);
    throw e;
  }
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') s.set(k, String(v));
  }
  const str = s.toString();
  return str ? `?${str}` : '';
}

export const api = {
  constants: () => request<Record<string, unknown>>('/api/constants'),
  dashboard: () => request<Record<string, unknown>>('/api/dashboard'),
  subjects: () => request<unknown[]>('/api/subjects'),
  addSubject: (name: string) =>
    request('/api/subjects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }),
  deleteSubject: (id: number) => request(`/api/subjects/${id}`, { method: 'DELETE' }),
  subjectDetail: (id: number) => request<Record<string, unknown>>(`/api/subjects/${id}`),
  addChapter: (subjectId: number, name: string) =>
    request(`/api/subjects/${subjectId}/chapters`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }),
  chapterDetail: (id: number) => request<Record<string, unknown>>(`/api/chapters/${id}`),
  deleteChapter: (id: number) => request(`/api/chapters/${id}`, { method: 'DELETE' }),
  addKP: (chapterId: number, name: string, description?: string) =>
    request(`/api/chapters/${chapterId}/kps`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description }) }),
  deleteKP: (id: number) => request(`/api/kps/${id}`, { method: 'DELETE' }),
  knowledgeTree: (params?: { subject_id?: number; chapter_id?: number }) => {
    const qs = params ? '?' + new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)])
    ).toString() : '';
    return request(`/api/knowledge-tree${qs}`);
  },
  kpChildren: (kpId: number) => request(`/api/kps/${kpId}/children`),
  kpParent: (kpId: number) => request(`/api/kps/${kpId}/parent`),
  moveKP: (kpId: number, newParentId: number | null) =>
    request('/api/kps/move', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kp_id: kpId, new_parent_id: newParentId }) }),
  mergeKP: (sourceId: number, targetId: number) =>
    request('/api/kps/merge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_id: sourceId, target_id: targetId }) }),
  // ── Task Import ──────────────────────────────────────────
  importFromTask: (data: Record<string, unknown>) =>
    request<{ message?: string }>('/api/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  // ── Exams ────────────────────────────────────────────────
  exams: () => request<unknown[]>('/api/exams'),
  addExam: (name: string) =>
    request('/api/exams', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }),
  examDetail: (id: number) => request<Record<string, unknown>>(`/api/exams/${id}`),
  deleteExam: (id: number) => request(`/api/exams/${id}`, { method: 'DELETE' }),
  examAddSubject: (examId: number, subjectId: number) =>
    request(`/api/exams/${examId}/subjects`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ subject_id: subjectId }) }),
  examRemoveSubject: (examId: number, subjectId: number) =>
    request(`/api/exams/${examId}/subjects/${subjectId}`, { method: 'DELETE' }),
  // ── Sources ──────────────────────────────────────────────
  sources: () => request<string[]>('/api/sources'),
  // ── KP Deduplication ─────────────────────────────────────
  dedupRun: () => request<{ task_id: string; status: string }>('/api/kps/dedup', { method: 'POST' }),
  dedupStatus: (taskId: string) => request<{ status: string; groups: DedupGroup[]; error?: string }>(`/api/kps/dedup/${taskId}`),
  dedupApply: (groups: DedupGroup[]) => request<{ message: string; applied: number }>('/api/kps/dedup/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ groups }) }),
  questions: (params: Record<string, string | number | undefined | null> = {}) =>
    request<Record<string, unknown>>(`/api/questions${qs(params)}`),
  addQuestion: (data: Record<string, unknown>) =>
    request('/api/questions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  batchImport: (data: Record<string, unknown>) =>
    request('/api/questions/batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  questionDetail: (id: number) => request<Record<string, unknown>>(`/api/questions/${id}`),
  editQuestion: (id: number, data: Record<string, unknown>) =>
    request(`/api/questions/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  deleteQuestion: (id: number) => request(`/api/questions/${id}`, { method: 'DELETE' }),
  batchDeleteQuestions: (ids: number[]) =>
    request<{ message?: string; deleted: number }>('/api/questions/batch-delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) }),
  batchUpdateMastery: (ids: number[], level: number) =>
    request<{ message?: string; updated: number }>('/api/questions/batch-mastery', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids, level }) }),
  batchUpdateSource: (ids: number[], source: string) =>
    request<{ message?: string; updated: number }>('/api/questions/batch-source', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids, source }) }),
  updateMastery: (id: number, level: number) =>
    request(`/api/questions/${id}/mastery`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ level }) }),
  reviewData: (id: number) => request<Record<string, unknown>>(`/api/questions/${id}/review`),
  saveReview: (id: number, knowledgePoints: unknown[]) =>
    request(`/api/questions/${id}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ knowledge_points: knowledgePoints }) }),
  analyzeQuestion: (data: Record<string, unknown>) =>
    request('/api/analyze-question', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  analyze: (data: Record<string, unknown>) =>
    request('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  // ?? Review / Recommend ?????????????????????????????????????
  getRecommend: (limit?: number, subjectId?: number) => {
    const params = new URLSearchParams();
    if (limit) params.set('limit', String(limit));
    if (subjectId) params.set('subject_id', String(subjectId));
    const qs = params.toString();
    return request(`/api/recommend${qs ? '?' + qs : ''}`);
  },
  setMastery: (id: number, level: number) =>
    request(`/api/questions/${id}/mastery`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ level }) }),
  statistics: () => request<Record<string, unknown>>('/api/statistics'),
  // Settings
  getSettings: () => request<Record<string, string>>('/api/settings'),
  saveSettings: (data: Record<string, string>) =>
    request('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  testSettings: () => request<{ success: boolean; message?: string; error?: string }>('/api/settings/test', { method: 'POST' }),
  exportUrl: '/api/export',
  exportDownload: (subjectId?: number, chapterId?: number) =>
    `/api/export${qs({ subject_id: subjectId, chapter_id: chapterId })}`,
  importFile: async (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/import', { method: 'POST', body: fd });
    if (!res.ok) { const body = await res.json().catch(() => ({})); throw new Error(body.error || `HTTP ${res.status}`); }
    return res.json();
  },
  // ── PDF Import Tasks ─────────────────────────────────────
  pdfImport: async (file: File, subjects?: string, autoImport: boolean = true) => {
    const fd = new FormData();
    fd.append('file', file);
    if (subjects) fd.append('subjects', subjects);
    fd.append('auto_import', autoImport ? '1' : '0');
    const res = await fetch('/api/pdf/import', { method: 'POST', body: fd });
    if (!res.ok) { const body = await res.json().catch(() => ({})); throw new Error(body.error || `HTTP ${res.status}`); }
    return res.json() as Promise<{ task_id: string; status: string }>;
  },
  getTask: (taskId: string) => request<Record<string, unknown>>(`/api/tasks/${taskId}`),
  listTasks: () => request<unknown[]>('/api/tasks'),
  getTaskResult: (taskId: string) => request<Record<string, unknown>>(`/api/tasks/${taskId}/result`),
};
