import { useEffect, useState, useCallback } from 'react';
import { api } from '../api';

interface RecQuestion {
  id: number;
  content: string;
  answer: string;
  source: string;
  source_page?: number;
  source_pages?: number[];
  question_number?: string;
  mastery_level: number;
  kp_name: string;
  score: number;
}

const MASTERY_LABELS: Record<number, string> = { 0: '未标记', 1: '知识盲区', 2: '只做了开头', 3: '易错细节', 4: '独立完成', 5: '轻松秒杀' };
const MASTERY_COLORS: Record<number, string> = { 0: 'secondary', 1: 'danger', 2: 'danger', 3: 'warning', 4: 'success', 5: 'success' };

export default function Review() {
  const [questions, setQuestions] = useState<RecQuestion[]>([]);
  const [idx, setIdx] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState('');

  const loadQuestions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getRecommend(20) as { questions: RecQuestion[] };
      setQuestions(data.questions || []);
      setIdx(0);
      setShowAnswer(false);
    } catch {
      setQuestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadQuestions(); }, [loadQuestions]);

  const markMastery = async (level: number) => {
    const q = questions[idx];
    if (!q) return;
    try {
      await api.setMastery(q.id, level);
      setToast(`已标记为「${MASTERY_LABELS[level]}」`);
      setTimeout(() => setToast(''), 2000);
      // Move to next
      if (idx < questions.length - 1) {
        setIdx(idx + 1);
        setShowAnswer(false);
      } else {
        loadQuestions();
      }
    } catch {
      setToast('标记失败');
      setTimeout(() => setToast(''), 2000);
    }
  };

  const current = questions[idx];

  if (loading) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border text-primary"></div>
        <p className="mt-2 text-muted">正在分析薄弱知识点...</p>
      </div>
    );
  }

  if (!current) {
    return (
      <div className="text-center py-5">
        <i className="bi bi-check-circle text-success" style={{ fontSize: '3rem' }}></i>
        <h5 className="mt-3">暂无需要复习的题目</h5>
        <p className="text-muted">所有题目掌握度良好，继续保持！</p>
        <button className="btn btn-outline-primary" onClick={loadQuestions}>
          <i className="bi bi-arrow-clockwise"></i> 刷新
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4 className="mb-0"><i className="bi bi-lightbulb"></i> 智能复习</h4>
        <div className="d-flex align-items-center gap-3">
          <span className="text-muted">{idx + 1} / {questions.length}</span>
          <button className="btn btn-outline-secondary btn-sm" onClick={loadQuestions}>
            <i className="bi bi-arrow-clockwise"></i> 换一批
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="progress mb-4" style={{ height: '4px' }}>
        <div className="progress-bar" role="progressbar"
          style={{ width: `${((idx + 1) / questions.length) * 100}%` }}></div>
      </div>

      {/* Question card */}
      <div className="card mb-4">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>
            <i className="bi bi-bookmark"></i> {current.kp_name}
          </span>
          <div>
            <span className={`badge bg-${MASTERY_COLORS[current.mastery_level]} me-2`}>
              {MASTERY_LABELS[current.mastery_level]}
            </span>
            {current.source && (
              <span className="badge bg-light text-dark">
                {current.source}
                {current.source_page ? `，第 ${current.source_page} 页` : ''}
              </span>
            )}
          </div>
        </div>
        <div className="card-body">
          <div className="mb-3" style={{ whiteSpace: 'pre-wrap' }}>
            {current.content}
          </div>

          {!showAnswer ? (
            <button className="btn btn-outline-primary w-100" onClick={() => setShowAnswer(true)}>
              <i className="bi bi-eye"></i> 显示答案
            </button>
          ) : (
            <div className="border-top pt-3">
              <h6 className="text-muted"><i className="bi bi-check2-square"></i> 参考答案</h6>
              <div style={{ whiteSpace: 'pre-wrap' }}>{current.answer || '暂无答案'}</div>
            </div>
          )}
        </div>
      </div>

      {/* Mastery buttons */}
      {showAnswer && (
        <div className="card">
          <div className="card-body">
            <p className="text-muted mb-3">你对这道题的掌握程度：</p>
            <div className="d-flex gap-2 flex-wrap">
              <button className="btn btn-danger flex-fill" onClick={() => markMastery(1)}>
                <i className="bi bi-x-circle"></i> 知识盲区
              </button>
              <button className="btn btn-warning flex-fill" onClick={() => markMastery(2)}>
                <i className="bi bi-question-circle"></i> 只做了开头
              </button>
              {[3, 4, 5].map(level => (
                <button key={level} className={`btn btn-${MASTERY_COLORS[level]} flex-fill`} onClick={() => markMastery(level)}>
                  <i className={level === 5 ? 'bi bi-lightning-charge' : 'bi bi-check-circle'}></i> {MASTERY_LABELS[level]}
                </button>
              ))}
            </div>
            <div className="text-center mt-2">
              <button className="btn btn-link btn-sm text-muted" onClick={() => {
                if (idx < questions.length - 1) { setIdx(idx + 1); setShowAnswer(false); }
                else loadQuestions();
              }}>
                跳过此题 <i className="bi bi-chevron-right"></i>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="position-fixed bottom-0 end-0 p-3" style={{ zIndex: 1050 }}>
          <div className="toast show align-items-center text-bg-success border-0" role="alert">
            <div className="d-flex">
              <div className="toast-body"><i className="bi bi-check-circle"></i> {toast}</div>
              <button type="button" className="btn-close btn-close-white me-2 m-auto" onClick={() => setToast('')}></button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
