import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { Question, KnowledgePoint, ReviewData } from '../types';

interface SelectedKP {
  id: number; name: string; chapter: string; role: string; weight: number;
}

/**
 * Renders the knowledge-point review page for a question.
 *
 * @returns The review interface for loading, editing, and saving knowledge-point associations.
 */
export default function ReviewKnowledge() {
  const { id } = useParams();
  const qId = Number(id);
  const navigate = useNavigate();
  const [question, setQuestion] = useState<Question | null>(null);
  const [allKps, setAllKps] = useState<KnowledgePoint[]>([]);
  const [selected, setSelected] = useState<SelectedKP[]>([]);
  const [manualKpId, setManualKpId] = useState('');
  const [manualRole, setManualRole] = useState('primary');
  const [manualWeight, setManualWeight] = useState('1.0');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');

  useEffect(() => {
    api.reviewData(qId).then(d => {
      const data = d as unknown as ReviewData;
      setQuestion(data.question);
      setAllKps(data.all_kps);
      setSelected(data.linked_kps);
    });
  }, [qId]);

  const analyze = async () => {
    setAiLoading(true);
    setAiError('');
    try {
      const result = await api.analyze({
        content: question?.content || '',
        subject_name: question?.subject_name || '',
      }) as { knowledge_points?: { name: string; role?: string; weight?: number; chapter?: string }[] };
      const newKps: SelectedKP[] = (result.knowledge_points || []).map(kp => {
        const existing = allKps.find(ak => ak.name === kp.name);
        return {
          id: existing?.id || Date.now() + Math.random(),
          name: kp.name,
          chapter: existing?.chapter_name || kp.chapter || '',
          role: kp.role || 'primary',
          weight: kp.weight || 1.0,
        };
      });
      setSelected(prev => {
        const existingIds = new Set(prev.map(k => k.id));
        return [...prev, ...newKps.filter(k => !existingIds.has(k.id))];
      });
    } catch (e) { setAiError((e as Error).message); }
    finally { setAiLoading(false); }
  };

  const addManual = () => {
    if (!manualKpId) return;
    const opt = allKps.find(k => k.id === Number(manualKpId));
    if (!opt || selected.some(k => k.id === opt.id)) return;
    setSelected([...selected, { id: opt.id, name: opt.name, chapter: opt.chapter_name || '', role: manualRole, weight: parseFloat(manualWeight) }]);
    setManualKpId('');
  };

  const removeKP = (idx: number) => setSelected(selected.filter((_, i) => i !== idx));
  const updateRole = (idx: number, role: string) => {
    const next = [...selected];
    next[idx] = { ...next[idx], role, weight: role === 'primary' ? Math.max(0.5, next[idx].weight) : Math.min(0.5, next[idx].weight) };
    setSelected(next);
  };
  const updateWeight = (idx: number, weight: number) => {
    const next = [...selected];
    next[idx] = { ...next[idx], weight };
    setSelected(next);
  };

  const save = async () => {
    await api.saveReview(qId, selected);
    navigate(`/questions/${qId}`);
  };

  if (!question) return <div className="text-center py-5"><div className="spinner-border"></div></div>;

  return (
    <>
      <nav aria-label="breadcrumb" className="mb-3">
        <ol className="breadcrumb">
          <li className="breadcrumb-item"><Link to={`/questions/${qId}`}>第 {qId} 题</Link></li>
          <li className="breadcrumb-item active">审核知识点</li>
        </ol>
      </nav>
      <h4 className="mb-4">审核知识点关联</h4>
      <div className="row">
        <div className="col-md-7">
          <div className="card mb-3">
            <div className="card-header d-flex justify-content-between align-items-center">
              <span><i className="bi bi-robot"></i> AI 分析</span>
              <button className="btn btn-sm btn-outline-primary" onClick={analyze} disabled={aiLoading}>
                {aiLoading ? <span className="spinner-border spinner-border-sm"></span> : <i className="bi bi-stars"></i>}
                {' '}调用 DeepSeek 分析
              </button>
            </div>
            <div className="card-body">
              {aiError && <div className="alert alert-danger">{aiError}</div>}
              {selected.length === 0 && !aiLoading && <div className="text-muted">点击上方按钮，AI 将自动分析题目涉及的知识点</div>}
            </div>
          </div>
          <div className="card">
            <div className="card-header">题目内容</div>
            <div className="card-body" style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflowY: 'auto' }}>{question.content}</div>
          </div>
        </div>
        <div className="col-md-5">
          <div className="card mb-3">
            <div className="card-header"><i className="bi bi-check2-square"></i> 已选知识点 <small className="text-muted">（标签从知识点自动生成）</small></div>
            <div className="card-body" style={{ maxHeight: 500, overflowY: 'auto' }}>
              {selected.length === 0 ? <div className="text-muted">尚未选择知识点</div> : selected.map((kp, idx) => (
                <div key={idx} className="card mb-2">
                  <div className="card-body p-2">
                    <div className="d-flex justify-content-between align-items-center mb-1">
                      <div>
                        <span className={`badge ${kp.role === 'primary' ? 'bg-primary' : 'bg-secondary'} me-1`}>{kp.role === 'primary' ? '主要' : '次要'}</span>
                        <strong>{kp.name}</strong>
                        <small className="text-muted ms-1">{kp.chapter}</small>
                      </div>
                      <button className="btn btn-sm btn-outline-danger" onClick={() => removeKP(idx)}>&times;</button>
                    </div>
                    <div className="row g-2">
                      <div className="col-6">
                        <select className="form-select form-select-sm" value={kp.role} onChange={e => updateRole(idx, e.target.value)}>
                          <option value="primary">主要</option>
                          <option value="secondary">次要</option>
                        </select>
                      </div>
                      <div className="col-6">
                        <div className="input-group input-group-sm">
                          <input type="range" className="form-range" min={0.1} max={1} step={0.1} value={kp.weight}
                            onChange={e => updateWeight(idx, parseFloat(e.target.value))} style={{ width: '60%' }} />
                          <span className="input-group-text">{kp.weight}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="card mb-3">
            <div className="card-header"><i className="bi bi-plus-circle"></i> 手动添加知识点</div>
            <div className="card-body">
              <select className="form-select form-select-sm mb-2" value={manualKpId} onChange={e => setManualKpId(e.target.value)}>
                <option value="">选择已有知识点</option>
                {allKps.map(kp => <option key={kp.id} value={kp.id}>{kp.chapter_name} &gt; {kp.name}</option>)}
              </select>
              <div className="row g-2 mb-2">
                <div className="col-6">
                  <select className="form-select form-select-sm" value={manualRole} onChange={e => setManualRole(e.target.value)}>
                    <option value="primary">主要知识点</option>
                    <option value="secondary">次要知识点</option>
                  </select>
                </div>
                <div className="col-6">
                  <input type="number" className="form-control form-control-sm" value={manualWeight}
                    onChange={e => setManualWeight(e.target.value)} min={0.1} max={1} step={0.1} />
                </div>
              </div>
              <button className="btn btn-sm btn-outline-primary w-100" onClick={addManual}>添加知识点</button>
            </div>
          </div>
          <div className="d-grid gap-2">
            <button className="btn btn-primary" onClick={save}><i className="bi bi-check-circle"></i> 确认保存</button>
            <Link to={`/questions/${qId}`} className="btn btn-outline-secondary">取消</Link>
          </div>
        </div>
      </div>
    </>
  );
}
