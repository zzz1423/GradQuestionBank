import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api';
import { MASTERY_LABELS, MASTERY_COLORS, type Question, type Subject, type Chapter } from '../types';

const MASTERY_BORDER: Record<number, string> = {
  1: '#dc3545',
  2: '#fd7e14',
  3: '#ffc107',
  4: '#198754',
  5: '#20c997',
};

export default function PracticeRecord() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [selectedSource, setSelectedSource] = useState('');
  const [search, setSearch] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [chapterId, setChapterId] = useState('');
  const [masteryFilter, setMasteryFilter] = useState('');
  const [unmarkedOnly, setUnmarkedOnly] = useState(true);
  const [sort, setSort] = useState<'question_number_asc' | 'question_number_desc'>('question_number_asc');
  const [loading, setLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [masteryMap, setMasteryMap] = useState<Map<number, number>>(new Map());
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState('');

  // Drag selection state
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartId, setDragStartId] = useState<number | null>(null);
  const [dragMode, setDragMode] = useState<'select' | 'deselect' | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Load sources
  useEffect(() => {
    api.sources().then(d => setSources(d as string[])).catch(() => {});
  }, []);

  const loadQuestions = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        mastery: unmarkedOnly ? 0 : masteryFilter,
        sort,
      };
      if (selectedSource) params.source = selectedSource;
      if (search) params.search = search;
      if (subjectId) params.subject_id = subjectId;
      if (chapterId) params.chapter_id = chapterId;
      const d = await api.questions(params);
      const data = d as { questions: Question[]; subjects: Subject[]; chapters: Chapter[] };
      setQuestions(data.questions || []);
      setSubjects(data.subjects || []);
      setChapters(data.chapters || []);
    } catch {
      // keep previous list on transient errors
    } finally {
      setLoading(false);
    }
  }, [selectedSource, search, subjectId, chapterId, masteryFilter, unmarkedOnly, sort]);

  useEffect(() => {
    void loadQuestions();
  }, [loadQuestions]);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  }, []);

  // Toggle question selection
  const toggleSelect = (id: number) => {
    const question = questions.find(q => q.id === id);
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        setMasteryMap(prev => {
          const m = new Map(prev);
          m.delete(id);
          return m;
        });
      } else {
        next.add(id);
        const defaultLevel = question && question.mastery_level > 0 ? question.mastery_level : 4;
        setMasteryMap(prev => new Map(prev).set(id, defaultLevel));
      }
      return next;
    });
  };

  // Select range (drag selection)
  const handleMouseDown = (id: number, button: number) => {
    setIsDragging(true);
    setDragStartId(id);
    setDragMode(button === 2 ? 'deselect' : 'select');
    if (button === 2) {
      setSelectedIds(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      setMasteryMap(prev => {
        const next = new Map(prev);
        next.delete(id);
        return next;
      });
    } else {
      toggleSelect(id);
    }
  };

  const handleMouseEnter = (id: number) => {
    if (!isDragging || dragStartId === null || dragMode === null) return;
    // Select all questions between dragStartId and current id
    const startIdx = questions.findIndex(q => q.id === dragStartId);
    const endIdx = questions.findIndex(q => q.id === id);
    if (startIdx === -1 || endIdx === -1) return;
    const [from, to] = startIdx < endIdx ? [startIdx, endIdx] : [endIdx, startIdx];
    const newSelected = new Set(selectedIds);
    const newMastery = new Map(masteryMap);
    for (let i = from; i <= to; i++) {
      if (dragMode === 'deselect') {
        newSelected.delete(questions[i].id);
        newMastery.delete(questions[i].id);
      } else {
        newSelected.add(questions[i].id);
        if (!newMastery.has(questions[i].id)) {
          newMastery.set(
            questions[i].id,
            questions[i].mastery_level > 0 ? questions[i].mastery_level : 4,
          );
        }
      }
    }
    setSelectedIds(newSelected);
    setMasteryMap(newMastery);
  };

  const handleMouseUp = () => {
    setIsDragging(false);
    setDragStartId(null);
    setDragMode(null);
  };

  useEffect(() => {
    document.addEventListener('mouseup', handleMouseUp);
    return () => document.removeEventListener('mouseup', handleMouseUp);
  }, []);

  // Update mastery for a single question
  const setMastery = (id: number, level: number) => {
    setMasteryMap(prev => new Map(prev).set(id, level));
  };

  // Select all / deselect all
  const selectAll = () => {
    const newSelected = new Set(questions.map(q => q.id));
    setSelectedIds(newSelected);
    const newMastery = new Map(masteryMap);
    questions.forEach(q => {
      if (!newMastery.has(q.id)) {
        newMastery.set(q.id, q.mastery_level > 0 ? q.mastery_level : 4);
      }
    });
    setMasteryMap(newMastery);
  };

  const deselectAll = () => {
    setSelectedIds(new Set());
    setMasteryMap(new Map());
  };

  // Save mastery markings
  const handleSave = async () => {
    if (selectedIds.size === 0) {
      showToast('请先选择题目');
      return;
    }
    setSaving(true);
    try {
      const promises = Array.from(selectedIds).map(id => {
        const level = masteryMap.get(id) || 0;
        if (level === 0) throw new Error('请为每道已选题目选择做题感受');
        return api.updateMastery(id, level);
      });
      await Promise.all(promises);
      showToast(`已标记 ${selectedIds.size} 道题目的掌握度`);
      // Remove saved questions from list
      setQuestions(prev => prev.filter(q => !selectedIds.has(q.id)));
      setSelectedIds(new Set());
      setMasteryMap(new Map());
    } catch (e) {
      showToast('保存失败: ' + (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const selectedCount = selectedIds.size;

  return (
    <>
      <h4 className="mb-3"><i className="bi bi-journal-check"></i> 做题记录</h4>
      <p className="text-muted mb-1">
        选择你刚做完的题目，并记录这次做题的实际感受。
      </p>
      <p className="text-muted small mb-3">
        <i className="bi bi-mouse"></i> 左键拖动批量选择，右键拖动批量取消选择
      </p>

      {/* Filters */}
      <div className="card mb-3">
        <div className="card-body py-2">
          <div className="row g-2 align-items-end">
            <div className="col-auto">
              <label className="form-label small mb-0">题号</label>
              <input type="text" className="form-control form-control-sm" placeholder="搜索题号..."
                value={search} onChange={e => setSearch(e.target.value)} style={{ width: 180 }} />
            </div>
            <div className="col-auto">
              <label className="form-label small mb-0">学科</label>
              <select className="form-select form-select-sm" value={subjectId}
                onChange={e => { setSubjectId(e.target.value); setChapterId(''); }}>
                <option value="">全部</option>
                {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            {chapters.length > 0 && (
              <div className="col-auto">
                <label className="form-label small mb-0">章节</label>
                <select className="form-select form-select-sm" value={chapterId}
                  onChange={e => setChapterId(e.target.value)}>
                  <option value="">全部</option>
                  {chapters.map(ch => <option key={ch.id} value={ch.id}>{ch.name}</option>)}
                </select>
              </div>
            )}
            <div className="col-auto">
              <label className="form-label small mb-0">掌握度</label>
              <select className="form-select form-select-sm" value={masteryFilter}
                disabled={unmarkedOnly}
                onChange={e => setMasteryFilter(e.target.value)}>
                <option value="">全部</option>
                {Object.entries(MASTERY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div className="col-auto">
              <label className="form-label small mb-0">&nbsp;</label>
              <div className="form-check">
                <input
                  className="form-check-input"
                  type="checkbox"
                  id="practiceUnmarkedOnly"
                  checked={unmarkedOnly}
                  onChange={e => {
                    setUnmarkedOnly(e.target.checked);
                    setMasteryFilter('');
                  }}
                />
                <label className="form-check-label small" htmlFor="practiceUnmarkedOnly">只看未标记</label>
              </div>
            </div>
            <div className="col-auto">
              <label className="form-label small mb-0">来源</label>
              <select className="form-select form-select-sm" value={selectedSource}
                onChange={e => setSelectedSource(e.target.value)} style={{ minWidth: 150 }}>
                <option value="">选择来源...</option>
                {sources.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="col-auto">
              <label className="form-label small mb-0">排序</label>
              <div className="btn-group btn-group-sm" role="group" aria-label="排序方式">
                <button
                  type="button"
                  className={`btn ${sort === 'question_number_asc' ? 'btn-primary' : 'btn-outline-primary'}`}
                  onClick={() => setSort('question_number_asc')}
                >
                  <i className="bi bi-sort-numeric-down"></i> 升序
                </button>
                <button
                  type="button"
                  className={`btn ${sort === 'question_number_desc' ? 'btn-primary' : 'btn-outline-primary'}`}
                  onClick={() => setSort('question_number_desc')}
                >
                  <i className="bi bi-sort-numeric-up"></i> 降序
                </button>
              </div>
            </div>
            <div className="col-auto">
              <button className="btn btn-sm btn-outline-secondary"
                onClick={() => { setSubjectId(''); setChapterId(''); setMasteryFilter(''); setUnmarkedOnly(true); setSearch(''); setSelectedSource(''); setSort('question_number_asc'); }}>重置</button>
            </div>
            {questions.length > 0 && (
              <>
                <div className="col-auto">
                  <button className="btn btn-sm btn-outline-primary" onClick={selectAll}>全选</button>
                </div>
                <div className="col-auto">
                  <button className="btn btn-sm btn-outline-secondary" onClick={deselectAll}>取消全选</button>
                </div>
                <div className="col-auto ms-auto">
                  <span className="text-muted small">已选 {selectedCount} / {questions.length} 题</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Question list */}
      {loading ? (
        <div className="text-center py-5"><div className="spinner-border"></div></div>
      ) : questions.length === 0 ? (
        <div className="text-center text-muted py-5">
          <i className="bi bi-check-circle fs-1"></i>
          <p className="mt-2">没有未标记的题目</p>
        </div>
      ) : (
        <div
          ref={listRef}
          className="list-group mb-3"
          style={{ userSelect: isDragging ? 'none' : 'auto' }}
          onContextMenu={e => e.preventDefault()}
        >
          {questions.map((q, idx) => {
            const isSelected = selectedIds.has(q.id);
            const mastery = masteryMap.get(q.id) || 0;
            return (
              <div
                key={q.id}
                className={`list-group-item ${isSelected ? 'list-group-item-primary' : ''}`}
                onMouseDown={e => handleMouseDown(q.id, e.button)}
                onMouseEnter={() => handleMouseEnter(q.id)}
                style={{
                  cursor: 'pointer',
                  ...(q.mastery_level > 0
                    ? { borderLeft: `4px solid ${MASTERY_BORDER[q.mastery_level] || '#adb5bd'}` }
                    : {}),
                }}
              >
                <div className="d-flex align-items-start gap-2">
                  <div className="form-check mt-1">
                    <input className="form-check-input" type="checkbox" checked={isSelected}
                      onMouseDown={e => e.stopPropagation()}
                      onChange={() => toggleSelect(q.id)} onClick={e => e.stopPropagation()} />
                  </div>
                  <div className="flex-grow-1">
                    <div className="mb-1">
                      <span className="badge bg-secondary me-2">{q.question_number || idx + 1}</span>
                      {q.content.length > 200 ? q.content.slice(0, 200) + '...' : q.content}
                    </div>
                    <div className="d-flex gap-2 flex-wrap">
                      <span className="badge bg-primary">{q.subject_name}</span>
                      {(q.knowledge_points || []).map(kp => <span key={kp.id} className="badge bg-secondary">{kp.name}</span>)}
                      {q.source && (
                        <span className="badge bg-light text-dark">
                          {q.source}
                          {q.source_page ? `，第 ${q.source_page} 页` : ''}
                        </span>
                      )}
                      {q.needs_review ? <span className="badge bg-warning text-dark">待复核</span> : null}
                      {q.mastery_level > 0 && (
                        <span className={`badge bg-${MASTERY_COLORS[q.mastery_level]} mastery-badge`}>
                          {MASTERY_LABELS[q.mastery_level]}
                        </span>
                      )}
                    </div>
                  </div>
                  {isSelected && (
                    <div className="d-flex gap-1 flex-shrink-0" onClick={e => e.stopPropagation()} onMouseDown={e => e.stopPropagation()}>
                      {[1, 2, 3, 4, 5].map(level => (
                        <button
                          key={level}
                          className={`btn btn-sm ${mastery === level ? `btn-${MASTERY_COLORS[level]}` : 'btn-outline-secondary'}`}
                          onClick={() => setMastery(q.id, level)}
                          title={MASTERY_LABELS[level]}
                        >
                          {level === 3 && <i className="bi bi-check-circle"></i>}
                          {level === 2 && <i className="bi bi-question-circle"></i>}
                          {level === 1 && <i className="bi bi-x-circle"></i>}
                          {level === 4 && <i className="bi bi-check-circle"></i>}
                          {level === 5 && <i className="bi bi-lightning-charge"></i>}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Save button */}
      {selectedCount > 0 && (
        <div className="position-sticky bottom-0 bg-white border-top p-3" style={{ zIndex: 100 }}>
          <div className="d-flex justify-content-between align-items-center">
            <span className="text-muted">已选择 {selectedCount} 题</span>
            <button className="btn btn-success" onClick={handleSave} disabled={saving}>
              {saving ? (
                <><span className="spinner-border spinner-border-sm me-2"></span>保存中...</>
              ) : (
                <><i className="bi bi-check-circle me-2"></i>保存标记</>
              )}
            </button>
          </div>
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
