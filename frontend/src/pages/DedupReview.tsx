import { useState, useRef, useCallback, useEffect } from 'react';
import { api } from '../api';
import type { DedupGroup } from '../types';

export default function DedupReview() {
  const [groups, setGroups] = useState<DedupGroup[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState('');
  const [applying, setApplying] = useState(false);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const runAnalysis = async () => {
    setAnalyzing(true);
    setError('');
    setProgress('开始分析...');
    try {
      const result = await api.dedupRun();
      const taskId = result.task_id;
      setProgress('AI 正在分析知识点...');

      // Poll for results
      const poll = async () => {
        try {
          const status = await api.dedupStatus(taskId);
          if (status.status === 'completed') {
            stopPolling();
            setGroups((status.groups || []).map(g => ({ ...g, accepted: true })));
            setAnalyzing(false);
            if (status.groups.length === 0) {
              setToast('未发现重复知识点');
              setTimeout(() => setToast(''), 3000);
            }
          } else if (status.status === 'failed') {
            stopPolling();
            setError(status.error || '分析失败');
            setAnalyzing(false);
          }
          // else keep polling
        } catch {
          // Ignore polling errors
        }
      };

      poll(); // Immediate first check
      pollRef.current = setInterval(poll, 2000);
    } catch (e) {
      setError((e as Error).message);
      setAnalyzing(false);
    }
  };

  const toggleGroup = (idx: number) => {
    setGroups(prev => prev.map((g, i) => i === idx ? { ...g, accepted: !g.accepted } : g));
  };

  const removeDuplicate = (groupIdx: number, dupIdx: number) => {
    setGroups(prev => prev.map((g, i) => {
      if (i !== groupIdx) return g;
      const newDups = g.duplicates.filter((_, j) => j !== dupIdx);
      return { ...g, duplicates: newDups };
    }).filter(g => g.duplicates.length > 0));
  };

  const applyAccepted = async () => {
    const accepted = groups.filter(g => g.accepted && g.duplicates.length > 0);
    if (accepted.length === 0) {
      setToast('没有选中任何要应用的建议');
      setTimeout(() => setToast(''), 3000);
      return;
    }
    setApplying(true);
    try {
      const result = await api.dedupApply(accepted);
      setToast(result.message);
      setTimeout(() => setToast(''), 5000);
      setGroups(prev => prev.filter(g => !g.accepted));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setApplying(false);
    }
  };

  const acceptedCount = groups.filter(g => g.accepted).length;

  return (
    <>
      <h4 className="mb-3"><i className="bi bi-search"></i> 知识点重复检测</h4>
      <p className="text-muted mb-4">
        使用 AI 自动识别重复或近义的知识点名称，审核后可批量添加到别名映射表。
      </p>

      {error && <div className="alert alert-danger"><i className="bi bi-exclamation-circle"></i> {error}</div>}

      <div className="d-flex gap-2 mb-4">
        <button className="btn btn-primary" onClick={runAnalysis} disabled={analyzing}>
          {analyzing ? (
            <><span className="spinner-border spinner-border-sm me-2"></span>AI 分析中...</>
          ) : (
            <><i className="bi bi-search me-1"></i> 开始检测</>
          )}
        </button>
        {groups.length > 0 && (
          <button className="btn btn-success" onClick={applyAccepted} disabled={applying || acceptedCount === 0}>
            {applying ? (
              <><span className="spinner-border spinner-border-sm me-2"></span>应用中...</>
            ) : (
              <><i className="bi bi-check-circle me-1"></i> 应用选中的建议 ({acceptedCount})</>
            )}
          </button>
        )}
      </div>

      {analyzing && (
        <div className="alert alert-info">
          <span className="spinner-border spinner-border-sm me-2"></span>
          {progress || 'AI 正在分析所有知识点，可能需要 30-60 秒...'}
        </div>
      )}

      {groups.length > 0 && (
        <div className="card">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span><i className="bi bi-list-check"></i> 检测结果：{groups.length} 组重复</span>
            <div className="form-check">
              <input className="form-check-input" type="checkbox" id="selectAll"
                checked={groups.every(g => g.accepted)}
                onChange={e => setGroups(prev => prev.map(g => ({ ...g, accepted: e.target.checked })))} />
              <label className="form-check-label" htmlFor="selectAll">全选</label>
            </div>
          </div>
          <div className="card-body p-0">
            {groups.map((g, idx) => (
              <div key={idx} className={`border-bottom p-3 ${g.accepted ? '' : 'bg-light opacity-50'}`}>
                <div className="d-flex justify-content-between align-items-start mb-2">
                  <div className="form-check">
                    <input className="form-check-input" type="checkbox" checked={!!g.accepted}
                      onChange={() => toggleGroup(idx)} id={`g-${idx}`} />
                    <label className="form-check-label fw-bold" htmlFor={`g-${idx}`}>
                      标准名：{g.canonical}
                    </label>
                  </div>
                  {g.subject && <span className="badge bg-secondary">{g.subject}</span>}
                </div>
                <div className="mb-2">
                  <small className="text-muted">将合并以下别名：</small>
                  <div className="d-flex flex-wrap gap-1 mt-1">
                    {g.duplicates.map((dup, j) => (
                      <span key={j} className="badge bg-warning text-dark">
                        {dup}
                        <button type="button" className="btn-close btn-close-sm ms-1" style={{ fontSize: '0.5em' }}
                          onClick={() => removeDuplicate(idx, j)} title="移除此建议" />
                      </span>
                    ))}
                  </div>
                </div>
                {g.reason && <small className="text-muted"><i className="bi bi-info-circle"></i> {g.reason}</small>}
              </div>
            ))}
          </div>
        </div>
      )}

      {!analyzing && groups.length === 0 && (
        <div className="text-center text-muted py-5">
          <i className="bi bi-diagram-3 fs-1"></i>
          <p className="mt-2">点击"开始检测"按钮，AI 将自动分析知识点库中的重复项</p>
        </div>
      )}

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
