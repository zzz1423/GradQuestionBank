const BASE = '';

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
  updateMastery: (id: number, level: number) =>
    request(`/api/questions/${id}/mastery`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ level }) }),
  reviewData: (id: number) => request<Record<string, unknown>>(`/api/questions/${id}/review`),
  saveReview: (id: number, knowledgePoints: unknown[]) =>
    request(`/api/questions/${id}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ knowledge_points: knowledgePoints }) }),
  analyzeQuestion: (data: Record<string, unknown>) =>
    request('/api/analyze-question', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  analyze: (data: Record<string, unknown>) =>
    request('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  statistics: () => request<Record<string, unknown>>('/api/statistics'),
  // Settings
  getSettings: () => request<Record<string, string>>('/api/settings'),
  saveSettings: (data: Record<string, string>) =>
    request('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  testSettings: () => request<{ success: boolean; message?: string; error?: string }>('/api/settings/test', { method: 'POST' }),
  exportUrl: '/api/export',
  importFile: async (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/import', { method: 'POST', body: fd });
    if (!res.ok) { const body = await res.json().catch(() => ({})); throw new Error(body.error || `HTTP ${res.status}`); }
    return res.json();
  },
};
