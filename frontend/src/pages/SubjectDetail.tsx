import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api';
import type { Subject, Chapter } from '../types';

export default function SubjectDetail() {
  const { id } = useParams();
  const subjectId = Number(id);
  const [subject, setSubject] = useState<Subject | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [name, setName] = useState('');
  const [showModal, setShowModal] = useState(false);

  const load = () => {
    api.subjectDetail(subjectId).then(d => {
      const data = d as { subject: Subject; chapters: Chapter[] };
      setSubject(data.subject);
      setChapters(data.chapters);
    });
  };
  useEffect(() => { load(); }, [subjectId]);

  const addChapter = async () => {
    if (!name.trim()) return;
    await api.addChapter(subjectId, name.trim());
    setName('');
    setShowModal(false);
    load();
  };

  const deleteChapter = async (chId: number) => {
    if (!confirm('确定删除此章节？')) return;
    await api.deleteChapter(chId);
    load();
  };

  if (!subject) return <div className="text-center py-5"><div className="spinner-border"></div></div>;

  return (
    <>
      <nav aria-label="breadcrumb" className="mb-3">
        <ol className="breadcrumb">
          <li className="breadcrumb-item"><Link to="/subjects">学科管理</Link></li>
          <li className="breadcrumb-item active">{subject.name}</li>
        </ol>
      </nav>

      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4>{subject.name}</h4>
        <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}>
          <i className="bi bi-plus"></i> 添加章节
        </button>
      </div>

      <div className="row g-3">
        {chapters.map(ch => (
          <div className="col-md-6 col-lg-4" key={ch.id}>
            <div className="card h-100">
              <div className="card-body">
                <h6><Link to={`/chapters/${ch.id}`} className="text-decoration-none">{ch.name}</Link></h6>
                <span className="text-muted small">{ch.kp_count} 个知识点</span>
              </div>
              <div className="card-footer bg-transparent">
                <button className="btn btn-sm btn-outline-danger" onClick={() => deleteChapter(ch.id)}>
                  <i className="bi bi-trash"></i>
                </button>
              </div>
            </div>
          </div>
        ))}
        {chapters.length === 0 && <div className="text-muted">暂无章节，请点击上方按钮添加</div>}
      </div>

      {showModal && (
        <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowModal(false)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">添加章节</h5>
                <button type="button" className="btn-close" onClick={() => setShowModal(false)}></button>
              </div>
              <div className="modal-body">
                <label className="form-label">章节名称</label>
                <input type="text" className="form-control" value={name} onChange={e => setName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addChapter()} />
              </div>
              <div className="modal-footer">
                <button className="btn btn-secondary" onClick={() => setShowModal(false)}>取消</button>
                <button className="btn btn-primary" onClick={addChapter}>添加</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
