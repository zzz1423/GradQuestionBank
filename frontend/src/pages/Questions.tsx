import { useEffect, useState } from 'react';
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
  const [search, setSearch] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.questions({ subject_id: subjectId, chapter_id: chapterId, mastery, search })
      .then(d => {
        if (cancelled) return;
        const data = d as { questions: Question[]; subjects: Subject[]; chapters: Chapter[] };
        setQuestions(data.questions);
        setSubjects(data.subjects);
        setChapters(data.chapters);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [subjectId, chapterId, mastery, search]);

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
              <label className="form-label small mb-0">搜索</label>
              <input type="text" className="form-control form-control-sm" placeholder="搜索题干..."
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
                onChange={e => setMastery(e.target.value)}>
                <option value="">全部</option>
                {Object.entries(MASTERY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div className="col-auto">
              <button className="btn btn-sm btn-outline-secondary"
                onClick={() => { setSubjectId(''); setChapterId(''); setMastery(''); setSearch(''); }}>重置</button>
            </div>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-5"><div className="spinner-border"></div></div>
      ) : questions.length > 0 ? (
        <div className="list-group">
          {questions.map(q => (
            <Link key={q.id} to={`/questions/${q.id}`} className="list-group-item list-group-item-action">
              <div className="d-flex justify-content-between align-items-start">
                <div className="flex-grow-1">
                  <div className="mb-1">{q.content.length > 150 ? q.content.slice(0, 150) + '...' : q.content}</div>
                  <div className="d-flex gap-2 flex-wrap">
                    <span className="badge bg-primary">{q.subject_name}</span>
                    {(q.knowledge_points || []).map(kp => <span key={kp.id} className="badge bg-secondary">{kp.name}</span>)}
                    {q.source && <span className="badge bg-light text-dark">{q.source}</span>}
                  </div>
                </div>
                <span className={`badge bg-${MASTERY_COLORS[q.mastery_level]} mastery-badge ms-2 flex-shrink-0`}>
                  {MASTERY_LABELS[q.mastery_level]}
                </span>
              </div>
            </Link>
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
