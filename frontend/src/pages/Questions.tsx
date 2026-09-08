import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { MASTERY_LABELS, MASTERY_COLORS, type Question, type Subject, type Chapter } from '../types';

export default function Questions() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);

  const [subjectId, setSubjectId] = useState('');
  const [chapterId, setChapterId] = useState('');
  const [mastery, setMastery] = useState('');
  const [unmarkedOnly, setUnmarkedOnly] = useState(true);
  const [search, setSearch] = useState('');
  const [source, setSource] = useState('');
  const [sort, setSort] = useState<'question_number_asc' | 'question_number_desc'>('question_number_asc');
  const [sources, setSources] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [batchSource, setBatchSource] = useState('');
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchMsg, setBatchMsg] = useState('');
  const [batchError, setBatchError] = useState(false);

  const loadSources = useCallback(async () => {
    try {
      const d = await api.sources() as string[];
      setSources(d);
    } catch {
      // keep previous source list on transient errors
    }
  }, []);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  const loadQuestions = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.questions({
        subject_id: subjectId,
        chapter_id: chapterId,
        mastery: unmarkedOnly ? '0' : mastery,
        search,
        source,
        sort,
      });
      const data = d as { questions: Question[]; subjects: Subject[]; chapters: Chapter[] };
      setQuestions(data.questions);
      setSubjects(data.subjects);
      setChapters(data.chapters);
    } catch {
      // keep previous list on transient errors
    } finally {
      setLoading(false);
    }
  }, [subjectId, chapterId, mastery, unmarkedOnly, search, source, sort]);

  useEffect(() => {
    void loadQuestions();
  }, [loadQuestions]);

  const toggleSelect = (id: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected(prev => {
      const allSelected = questions.length > 0 && questions.every(q => prev.has(q.id));
      return allSelected ? new Set() : new Set(questions.map(q => q.id));
    });
  };

  const runBatch = async (action: (ids: number[]) => Promise<{ message?: string }>) => {
    if (batchBusy || selected.size === 0) return;
    const ids = [...selected];
    setBatchBusy(true);
    setBatchMsg('');
    setBatchError(false);
    try {
      const result = await action(ids);
      setBatchMsg(result.message || '操作完成');
      setSelected(new Set());
      setBatchSource('');
      await loadQuestions();
      const freshSources = await api.sources() as string[];
      setSources(freshSources);
      if (source && !freshSources.includes(source)) setSource('');
    } catch (e) {
      setBatchMsg((e as Error).message);
      setBatchError(true);
    } finally {
      setBatchBusy(false);
    }
  };

  const deleteSelected = async () => {
    if (!window.confirm(`确定删除选中的 ${selected.size} 道题目？此操作不可恢复。`)) return;
    await runBatch(api.batchDeleteQuestions);
  };

  const applyBatchSource = async () => {
    if (!batchSource) return;
    await runBatch(ids => api.batchUpdateSource(ids, batchSource));
  };

  return (
    <>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4>题目列表</h4>
        <div>
          <Link to="/questions/batch" className="btn btn-outline-primary me-2">
            <i className="bi bi-upload"></i> 批量录入
          </Link>
          <Link to="/questions/add" className="btn btn-primary">
            <i className="bi bi-plus"></i> 录入新题目
          </Link>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-body py-2">
          <div className="row g-2 align-items-end">
            <div className="col-auto">
              <label className="form-label small mb-0">题号</label>
              <input type="text" className="form-control form-control-sm" placeholder="搜索题号..."
                value={search} onChange={e => setSearch(e.target.value)} style={{ width: 200 }} />
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
              <select className="form-select form-select-sm" value={mastery}
                disabled={unmarkedOnly}
                onChange={e => setMastery(e.target.value)}>
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
                  id="unmarkedOnly"
                  checked={unmarkedOnly}
                  onChange={e => {
                    setUnmarkedOnly(e.target.checked);
                    setMastery('');
                  }}
                />
                <label className="form-check-label small" htmlFor="unmarkedOnly">只看未标记</label>
              </div>
            </div>
            {sources.length > 0 && (
              <div className="col-auto">
                <label className="form-label small mb-0">来源</label>
                <select className="form-select form-select-sm" value={source}
                  onChange={e => setSource(e.target.value)}>
                  <option value="">全部</option>
                  {sources.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            )}
            <div className="col-auto">
              <label className="form-label small mb-0">排序</label>
              <div className="btn-group btn-group-sm" role="group" aria-label="排序方式">
                <button
                  type="button"
                  className={`btn ${sort === 'question_number_asc' ? 'btn-primary' : 'btn-outline-primary'}`}
                  onClick={() => setSort('question_number_asc')}
                >
                  <i className="bi bi-sort-numeric-down"></i> 题号升序
                </button>
                <button
                  type="button"
                  className={`btn ${sort === 'question_number_desc' ? 'btn-primary' : 'btn-outline-primary'}`}
                  onClick={() => setSort('question_number_desc')}
                >
                  <i className="bi bi-sort-numeric-up"></i> 题号降序
                </button>
              </div>
            </div>
            <div className="col-auto">
              <button className="btn btn-sm btn-outline-secondary"
                onClick={() => { setSubjectId(''); setChapterId(''); setMastery(''); setUnmarkedOnly(true); setSearch(''); setSource(''); setSort('question_number_asc'); }}>重置</button>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-body py-2 d-flex align-items-center gap-2 flex-wrap">
          <div className="form-check mb-0">
            <input
              className="form-check-input"
              type="checkbox"
              id="selectAll"
              checked={questions.length > 0 && questions.every(q => selected.has(q.id))}
              onChange={toggleAll}
            />
            <label className="form-check-label small" htmlFor="selectAll">全选本页</label>
          </div>
          <span className="text-muted small">已选 {selected.size} 题</span>

          <div className="vr"></div>

          <select
            className="form-select form-select-sm"
            style={{ width: 180 }}
            value={batchSource}
            onChange={e => setBatchSource(e.target.value)}
          >
            <option value="">批量来源</option>
            {sources.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <button
            className="btn btn-sm btn-outline-primary"
            disabled={selected.size === 0 || !batchSource || batchBusy}
            onClick={applyBatchSource}
          >
            <i className="bi bi-tag"></i> 改来源
          </button>

          <button
            className="btn btn-sm btn-danger"
            disabled={selected.size === 0 || batchBusy}
            onClick={deleteSelected}
          >
            <i className="bi bi-trash"></i> 删除所选
          </button>

          {selected.size > 0 && (
            <button
              className="btn btn-sm btn-outline-secondary"
              disabled={batchBusy}
              onClick={() => setSelected(new Set())}
            >
              取消选择
            </button>
          )}

          {batchMsg && (
            <span className={`badge ${batchError ? 'bg-danger' : batchBusy ? 'bg-secondary' : 'bg-success'} text-white`}>{batchMsg}</span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-5"><div className="spinner-border"></div></div>
      ) : questions.length > 0 ? (
        <div className="list-group">
          {questions.map((q, idx) => (
            <div key={q.id} className="list-group-item d-flex align-items-start">
              <div className="form-check mt-1 me-2">
                <input
                  className="form-check-input"
                  type="checkbox"
                  checked={selected.has(q.id)}
                  onChange={() => toggleSelect(q.id)}
                  aria-label={`选择题目 ${idx + 1}`}
                />
              </div>
              <Link to={`/questions/${q.id}`} className="list-group-item-action flex-grow-1 rounded text-decoration-none">
                <div className="d-flex justify-content-between align-items-start">
                  <div className="flex-grow-1">
                    <div className="mb-1">
                      <span className="badge bg-secondary me-2">{q.question_number || idx + 1}</span>
                      {q.content.length > 150 ? q.content.slice(0, 150) + '...' : q.content}
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
                    </div>
                  </div>
                  <span className={`badge bg-${MASTERY_COLORS[q.mastery_level]} mastery-badge ms-2 flex-shrink-0`}>
                    {MASTERY_LABELS[q.mastery_level]}
                  </span>
                </div>
              </Link>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center text-muted py-5">
          <i className="bi bi-inbox fs-1"></i>
          <p className="mt-2">暂无题目</p>
        </div>
      )}
    </>
  );
}
