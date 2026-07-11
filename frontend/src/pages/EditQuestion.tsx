import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { Subject, Question } from '../types';

export default function EditQuestion() {
  const { id } = useParams();
  const qId = Number(id);
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [question, setQuestion] = useState<Question | null>(null);
  const [subjectId, setSubjectId] = useState('');
  const [content, setContent] = useState('');
  const [answer, setAnswer] = useState('');
  const [source, setSource] = useState('');

  useEffect(() => {
    api.subjects().then(d => setSubjects(d as Subject[]));
    api.questionDetail(qId).then(d => {
      const q = (d as { question: Question }).question;
      setQuestion(q);
      setSubjectId(String(q.subject_id));
      setContent(q.content);
      setAnswer(q.answer || '');
      setSource(q.source || '');
    });
  }, [qId]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    await api.editQuestion(qId, { subject_id: Number(subjectId), content, answer, source });
    navigate(`/questions/${qId}`);
  };

  if (!question) return <div className="text-center py-5"><div className="spinner-border"></div></div>;

  return (
    <>
      <nav aria-label="breadcrumb" className="mb-3">
        <ol className="breadcrumb">
          <li className="breadcrumb-item"><Link to={`/questions/${qId}`}>第 {qId} 题</Link></li>
          <li className="breadcrumb-item active">编辑</li>
        </ol>
      </nav>
      <h4 className="mb-4">编辑题目</h4>
      <div className="card">
        <div className="card-body">
          <form onSubmit={submit}>
            <div className="mb-3">
              <label className="form-label">学科 <span className="text-danger">*</span></label>
              <select className="form-select" required value={subjectId} onChange={e => setSubjectId(e.target.value)}>
                {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="mb-3">
              <label className="form-label">题干 <span className="text-danger">*</span></label>
              <textarea className="form-control" rows={8} required value={content} onChange={e => setContent(e.target.value)} />
            </div>
            <div className="mb-3">
              <label className="form-label">答案</label>
              <input type="text" className="form-control" value={answer} onChange={e => setAnswer(e.target.value)} />
            </div>
            <div className="mb-3">
              <label className="form-label">来源</label>
              <input type="text" className="form-control" value={source} onChange={e => setSource(e.target.value)} />
            </div>
            <div className="d-flex gap-2">
              <button type="submit" className="btn btn-primary"><i className="bi bi-check-circle"></i> 保存修改</button>
              <Link to={`/questions/${qId}`} className="btn btn-outline-secondary">取消</Link>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
