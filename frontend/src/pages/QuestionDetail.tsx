import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { MASTERY_LABELS, MASTERY_COLORS, type Question, type KnowledgePoint, type Tag } from '../types';

/**
 * Displays the details of a question and its related knowledge points.
 *
 * @returns The question detail page.
 */
export default function QuestionDetail() {
  const { id } = useParams();
  const qId = Number(id);
  const navigate = useNavigate();
  const [question, setQuestion] = useState<Question | null>(null);
  const [kps, setKps] = useState<KnowledgePoint[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);

  const load = () => {
    api.questionDetail(qId).then(d => {
      const data = d as { question: Question; knowledge_points: KnowledgePoint[]; tags: Tag[] };
      setQuestion(data.question);
      setKps(data.knowledge_points);
      setTags(data.tags);
    });
  };
  useEffect(() => { load(); }, [qId]);

  const updateMastery = async (level: number) => {
    await api.updateMastery(qId, level);
    load();
  };

  const deleteQuestion = async () => {
    if (!confirm('确定删除此题？')) return;
    await api.deleteQuestion(qId);
    navigate('/questions');
  };

  if (!question) return <div className="text-center py-5"><div className="spinner-border"></div></div>;

  return (
    <>
      <nav aria-label="breadcrumb" className="mb-3">
        <ol className="breadcrumb">
          <li className="breadcrumb-item"><Link to="/questions">题目列表</Link></li>
          <li className="breadcrumb-item active">第 {question.id} 题</li>
        </ol>
      </nav>

      <div className="row">
        <div className="col-md-8">
          <div className="card mb-3">
            <div className="card-header d-flex justify-content-between align-items-center">
              <span>
                <span className="badge bg-primary">{question.subject_name}</span>
                {question.source && <span className="badge bg-light text-dark ms-1">{question.source}</span>}
              </span>
              <button className="btn btn-sm btn-outline-danger" onClick={deleteQuestion}>
                <i className="bi bi-trash"></i> 删除
              </button>
            </div>
            <div className="card-body">
              <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>{question.content}</div>
            </div>
            {question.answer && (
              <div className="card-footer"><strong>答案：</strong> {question.answer}</div>
            )}
          </div>

          <div className="card mb-3">
            <div className="card-header d-flex justify-content-between align-items-center">
              <span><i className="bi bi-diagram-3"></i> 关联知识点</span>
              <Link to={`/questions/${qId}/review`} className="btn btn-sm btn-outline-primary">
                <i className="bi bi-pencil"></i> AI分析 / 编辑
              </Link>
            </div>
            <div className="card-body">
              {tags.length > 0 && (
                <div className="mb-2">
                  <small className="text-muted">标签：</small>
                  {tags.map((t, i) => <span key={i} className="badge bg-light text-dark ms-1">{t.name}</span>)}
                </div>
              )}
              {kps.length > 0 ? (
                <div className="d-flex flex-column gap-2">
                  {kps.map((kp, i) => (
                    <div key={i} className="d-flex align-items-center gap-2">
                      <span className={`badge ${kp.role === 'primary' ? 'bg-primary' : 'bg-secondary'}`}>
                        {kp.role === 'primary' ? '主要' : '次要'}
                      </span>
                      <span className="fw-bold">{kp.name}</span>
                      <small className="text-muted">{kp.chapter_name}</small>
                      <span className="badge bg-light text-dark">权重 {kp.weight}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-muted">尚未关联知识点，<Link to={`/questions/${qId}/review`}>点击分析</Link></div>
              )}
            </div>
          </div>
        </div>

        <div className="col-md-4">
          <div className="card">
            <div className="card-header"><i className="bi bi-speedometer2"></i> 掌握度标记</div>
            <div className="card-body">
              <p className="text-muted small">你对这道题的掌握程度：</p>
              <div className="d-grid gap-2">
                {[1, 2, 3].map(level => (
                  <button key={level}
                    className={`btn btn-${MASTERY_COLORS[level]} w-100 ${question.mastery_level === level ? 'active' : ''}`}
                    onClick={() => updateMastery(level)}>
                    {level === 1 && <i className="bi bi-x-circle"></i>}
                    {level === 2 && <i className="bi bi-question-circle"></i>}
                    {level === 3 && <i className="bi bi-check-circle"></i>}
                    {' '}{MASTERY_LABELS[level]}
                  </button>
                ))}
              </div>
              {question.mastery_level > 0 && (
                <button className="btn btn-sm btn-outline-secondary w-100 mt-2" onClick={() => updateMastery(0)}>
                  清除标记
                </button>
              )}
            </div>
          </div>
          <div className="card mt-3">
            <div className="card-body text-muted small">
              <div>录入时间：{question.created_at}</div>
              <div>更新时间：{question.updated_at}</div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
