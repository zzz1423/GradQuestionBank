import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { MASTERY_LABELS, MASTERY_COLORS, type DashboardData, type Question } from '../types';

export default function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    api.dashboard().then(d => setData(d as unknown as DashboardData)).catch(() => {});
  }, []);

  if (!data) return <div className="text-center py-5"><div className="spinner-border"></div></div>;

  const { stats, recent_questions } = data;

  return (
    <>
      <div className="mb-4">
        <h4>题库概览</h4>
        <p className="text-muted">欢迎使用考研智能题库系统</p>
      </div>

      <div className="row g-3 mb-4">
        {[
          { label: '学科', value: stats.subjects, color: '#0d6efd' },
          { label: '知识点', value: stats.knowledge_points, color: '#6f42c1' },
          { label: '题目总数', value: stats.questions, color: '#0dcaf0' },
          { label: '已掌握', value: stats.mastered, color: '#198754' },
        ].map(card => (
          <div className="col-md-3" key={card.label}>
            <div className="card stat-card" style={{ borderLeftColor: card.color }}>
              <div className="card-body">
                <div className="text-muted small">{card.label}</div>
                <div className="fs-4 fw-bold">{card.value}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="row g-3 mb-4">
        <div className="col-md-4">
          <Link to="/questions/add" className="btn btn-primary w-100 py-3">
            <i className="bi bi-plus-circle fs-4"></i><br />录入新题目
          </Link>
        </div>
        <div className="col-md-4">
          <Link to="/questions" className="btn btn-outline-primary w-100 py-3">
            <i className="bi bi-journal-text fs-4"></i><br />浏览题目
          </Link>
        </div>
        <div className="col-md-4">
          <Link to="/statistics" className="btn btn-outline-success w-100 py-3">
            <i className="bi bi-bar-chart fs-4"></i><br />查看统计
          </Link>
        </div>
      </div>

      {recent_questions.length > 0 ? (
        <div className="card">
          <div className="card-header"><i className="bi bi-clock-history"></i> 最近录入的题目</div>
          <div className="card-body p-0">
            <div className="table-responsive">
              <table className="table table-hover mb-0">
                <thead className="table-light">
                  <tr><th>学科</th><th>题干</th><th>掌握度</th><th>录入时间</th></tr>
                </thead>
                <tbody>
                  {recent_questions.map((q: Question) => (
                    <tr key={q.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/questions/${q.id}`)}>
                      <td><span className="badge bg-primary">{q.subject_name}</span></td>
                      <td>{q.content.length > 80 ? q.content.slice(0, 80) + '...' : q.content}</td>
                      <td>
                        <span className={`badge bg-${MASTERY_COLORS[q.mastery_level]} mastery-badge`}>
                          {MASTERY_LABELS[q.mastery_level]}
                        </span>
                      </td>
                      <td className="text-muted small">{q.created_at?.slice(0, 16)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        <div className="text-center text-muted py-5">
          <i className="bi bi-inbox fs-1"></i>
          <p className="mt-2">题库为空，点击上方按钮开始录入题目</p>
        </div>
      )}
    </>
  );
}
