import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import type { Subject } from '../types';

export default function Subjects() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [name, setName] = useState('');
  const [showModal, setShowModal] = useState(false);

  const load = () => api.subjects().then(d => setSubjects(d as Subject[]));
  useEffect(() => { load(); }, []);

  const addSubject = async () => {
    if (!name.trim()) return;
    try {
      await api.addSubject(name.trim());
      setName('');
      setShowModal(false);
      load();
    } catch (e) { alert((e as Error).message); }
  };

  const deleteSubject = async (id: number, subjectName: string) => {
    if (!confirm(`确定删除「${subjectName}」及其所有章节、知识点和题目？`)) return;
    await api.deleteSubject(id);
    load();
  };

  return (
    <>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4>学科管理</h4>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          <i className="bi bi-plus"></i> 添加学科
        </button>
      </div>

      <div className="row g-3">
        {subjects.map(s => (
          <div className="col-md-6 col-lg-4" key={s.id}>
            <div className="card h-100">
              <div className="card-body">
                <h5 className="card-title">
                  <Link to={`/subjects/${s.id}`} className="text-decoration-none">{s.name}</Link>
                </h5>
                <div className="d-flex gap-3 text-muted small mt-2">
                  <span><i className="bi bi-folder"></i> {s.chapter_count} 章节</span>
                  <span><i className="bi bi-diagram-3"></i> {s.kp_count} 知识点</span>
                  <span><i className="bi bi-journal"></i> {s.question_count} 题</span>
                </div>
              </div>
              <div className="card-footer bg-transparent">
                <button className="btn btn-sm btn-outline-danger" onClick={() => deleteSubject(s.id, s.name)}>
                  <i className="bi bi-trash"></i> 删除
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {showModal && (
        <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowModal(false)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">添加学科</h5>
                <button type="button" className="btn-close" onClick={() => setShowModal(false)}></button>
              </div>
              <div className="modal-body">
                <label className="form-label">学科名称</label>
                <input type="text" className="form-control" value={name} onChange={e => setName(e.target.value)}
                  placeholder="例如：数学一、英语一" onKeyDown={e => e.key === 'Enter' && addSubject()} />
              </div>
              <div className="modal-footer">
                <button className="btn btn-secondary" onClick={() => setShowModal(false)}>取消</button>
                <button className="btn btn-primary" onClick={addSubject}>添加</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
