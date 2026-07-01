import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { Subject } from '../types';

/**
 * Renders the batch import page for adding multiple questions to a subject.
 *
 * The page loads available subjects, accepts batch-formatted question content with an optional source, and submits the form to create the questions.
 */
export default function BatchImport() {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectId, setSubjectId] = useState('');
  const [content, setContent] = useState('');
  const [source, setSource] = useState('');
  const [autoAnalyze, setAutoAnalyze] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.subjects().then(d => setSubjects(d as Subject[])); }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    setLoading(true);
    try {
      const result = await api.batchImport({ subject_id: Number(subjectId), content, source, auto_analyze: autoAnalyze }) as { message: string };
      alert(result.message);
      navigate('/questions');
    } catch (e) { alert((e as Error).message); }
    finally { setLoading(false); }
  };

  return (
    <>
      <nav aria-label="breadcrumb" className="mb-3">
        <ol className="breadcrumb">
          <li className="breadcrumb-item"><Link to="/questions">题目列表</Link></li>
          <li className="breadcrumb-item active">批量录入</li>
        </ol>
      </nav>
      <h4 className="mb-4">批量录入题目</h4>
      <div className="card mb-3">
        <div className="card-body">
          <form onSubmit={submit}>
            <div className="mb-3">
              <label className="form-label">学科 <span className="text-danger">*</span></label>
              <select className="form-select" required value={subjectId} onChange={e => setSubjectId(e.target.value)}>
                <option value="">请选择学科</option>
                {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="mb-3">
              <label className="form-label">题目内容 <span className="text-danger">*</span></label>
              <textarea className="form-control" rows={15} required value={content} onChange={e => setContent(e.target.value)}
                placeholder="每道题之间用 --- 分隔&#10;&#10;题目1内容...&#10;答案：A&#10;---&#10;题目2内容...&#10;答案：B" />
              <div className="form-text">使用三个减号（---）分隔不同题目。答案格式为"答案：X"</div>
            </div>
            <div className="mb-3">
              <label className="form-label">来源（可选）</label>
              <input type="text" className="form-control" placeholder="如：2024年真题" value={source} onChange={e => setSource(e.target.value)} />
            </div>
            <div className="form-check mb-3">
              <input className="form-check-input" type="checkbox" id="autoAnalyze" checked={autoAnalyze} onChange={e => setAutoAnalyze(e.target.checked)} />
              <label className="form-check-label" htmlFor="autoAnalyze">录入后自动调用 AI 分析知识点</label>
            </div>
            <div className="d-flex gap-2">
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? <span className="spinner-border spinner-border-sm"></span> : <i className="bi bi-upload"></i>} 批量录入
              </button>
              <Link to="/questions" className="btn btn-outline-secondary">取消</Link>
            </div>
          </form>
        </div>
      </div>
      <div className="card">
        <div className="card-header">格式说明</div>
        <div className="card-body">
          <p>每道题之间使用 <code>---</code> 分隔，答案写在题目末尾，格式为 <code>答案：X</code></p>
          <pre className="bg-light p-3"><code>{`下列关于唯物辩证法的说法，正确的是（）\nA. 矛盾的斗争性是绝对的\nB. 矛盾的同一性是无条件的\nC. 矛盾的同一性是相对的、有条件的\nD. 矛盾的斗争性是相对的\n答案：C\n---\nTCP三次握手的正确顺序是（）\nA. SYN, SYN-ACK, ACK\nB. ACK, SYN, SYN-ACK\nC. SYN, ACK, SYN-ACK\nD. SYN-ACK, SYN, ACK\n答案：A`}</code></pre>
        </div>
      </div>
    </>
  );
}
