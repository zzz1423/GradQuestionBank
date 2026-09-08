import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';

interface Exam {
  id: number;
  name: string;
  description?: string;
  subject_count: number;
}

interface Subject {
  id: number;
  name: string;
  chapter_count: number;
  kp_count: number;
  question_count: number;
}

export default function Exams() {
  const [exams, setExams] = useState<Exam[]>([]);
  const [selectedExam, setSelectedExam] = useState<number | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [examName, setExamName] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [allSubjects, setAllSubjects] = useState<Subject[]>([]);
  const [linkSubjectId, setLinkSubjectId] = useState('');

  const loadExams = () => api.exams().then(d => setExams(d as Exam[])).catch(() => {});
  const loadSubjects = (examId: number) => {
    api.examDetail(examId).then(d => {
      const data = d as { subjects: Subject[] };
      setSubjects(data.subjects);
    }).catch(() => {});
  };

  useEffect(() => { loadExams(); }, []);
  useEffect(() => {
    if (selectedExam) loadSubjects(selectedExam);
  }, [selectedExam]);

  const addExam = async () => {
    if (!examName.trim()) return;
    try {
      await api.addExam(examName.trim());
      setExamName('');
      setShowModal(false);
      loadExams();
    } catch (e) { alert((e as Error).message); }
  };

  const deleteExam = async (id: number, name: string) => {
    if (!confirm(`确定删除"${name}"？`)) return;
    try {
      await api.deleteExam(id);
      if (selectedExam === id) { setSelectedExam(null); setSubjects([]); }
      loadExams();
    } catch (e) { alert((e as Error).message); }
  };

  const openLinkModal = async () => {
    // Load all subjects for linking
    const all = await api.subjects() as Subject[];
    setAllSubjects(all);
    setShowLinkModal(true);
  };

  const linkSubject = async () => {
    if (!linkSubjectId || !selectedExam) return;
    try {
      await api.examAddSubject(selectedExam, Number(linkSubjectId));
      setLinkSubjectId('');
      setShowLinkModal(false);
      loadSubjects(selectedExam);
    } catch (e) { alert((e as Error).message); }
  };

  const unlinkSubject = async (subjectId: number) => {
    if (!selectedExam) return;
    if (!confirm('确定取消关联此学科？')) return;
    try {
      await api.examRemoveSubject(selectedExam, subjectId);
      loadSubjects(selectedExam);
    } catch (e) { alert((e as Error).message); }
  };

  return (
    <>
      <h4 className="mb-4">考试管理</h4>

      <div className="row">
        {/* Left: Exam list */}
        <div className="col-md-4">
          <div className="card">
            <div className="card-header d-flex justify-content-between align-items-center">
              <span>考试类型</span>
              <button className="btn btn-sm btn-primary" onClick={() => setShowModal(true)}>
                <i className="bi bi-plus"></i> 添加
              </button>
            </div>
            <div className="list-group list-group-flush">
              {exams.map(e => (
                <button
                  key={e.id}
                  className={`list-group-item list-group-item-action d-flex justify-content-between align-items-center ${selectedExam === e.id ? 'active' : ''}`}
                  onClick={() => setSelectedExam(e.id)}
                >
                  <div>
                    <strong>{e.name}</strong>
                    <br />
                    <small className={selectedExam === e.id ? 'text-white-50' : 'text-muted'}>
                      {e.subject_count} 个学科
                    </small>
                  </div>
                  <button
                    className={`btn btn-sm ${selectedExam === e.id ? 'btn-light' : 'btn-outline-danger'}`}
                    onClick={ev => { ev.stopPropagation(); deleteExam(e.id, e.name); }}
                  >
                    <i className="bi bi-trash"></i>
                  </button>
                </button>
              ))}
              {exams.length === 0 && (
                <div className="list-group-item text-center text-muted">暂无考试</div>
              )}
            </div>
          </div>
        </div>

        {/* Right: Subjects for selected exam */}
        <div className="col-md-8">
          {selectedExam ? (
            <div className="card">
              <div className="card-header d-flex justify-content-between align-items-center">
                <span>关联学科</span>
                <button className="btn btn-sm btn-outline-primary" onClick={openLinkModal}>
                  <i className="bi bi-plus"></i> 关联学科
                </button>
              </div>
              <div className="card-body p-0">
                <table className="table table-hover mb-0">
                  <thead className="table-light">
                    <tr><th>学科</th><th>章节数</th><th>知识点数</th><th>题目数</th><th style={{width:60}}></th></tr>
                  </thead>
                  <tbody>
                    {subjects.map(s => (
                      <tr key={s.id}>
                        <td><Link to={`/subjects/${s.id}`} className="text-decoration-none">{s.name}</Link></td>
                        <td>{s.chapter_count}</td>
                        <td>{s.kp_count}</td>
                        <td>{s.question_count}</td>
                        <td>
                          <button className="btn btn-sm btn-outline-danger" onClick={() => unlinkSubject(s.id)}>
                            <i className="bi bi-x-lg"></i>
                          </button>
                        </td>
                      </tr>
                    ))}
                    {subjects.length === 0 && (
                      <tr><td colSpan={5} className="text-center text-muted">暂未关联学科</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="text-center text-muted py-5">
              <i className="bi bi-book fs-1"></i>
              <p className="mt-2">选择左侧考试类型查看关联学科</p>
            </div>
          )}
        </div>
      </div>

      {/* Add Exam Modal */}
      {showModal && (
        <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowModal(false)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">添加考试类型</h5>
                <button type="button" className="btn-close" onClick={() => setShowModal(false)}></button>
              </div>
              <div className="modal-body">
                <label className="form-label">考试名称</label>
                <input type="text" className="form-control" value={examName} onChange={e => setExamName(e.target.value)}
                  placeholder="例如：数学一、英语一" onKeyDown={e => e.key === 'Enter' && addExam()} />
              </div>
              <div className="modal-footer">
                <button className="btn btn-secondary" onClick={() => setShowModal(false)}>取消</button>
                <button className="btn btn-primary" onClick={addExam}>添加</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Link Subject Modal */}
      {showLinkModal && (
        <div className="modal d-block" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setShowLinkModal(false)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">关联学科</h5>
                <button type="button" className="btn-close" onClick={() => setShowLinkModal(false)}></button>
              </div>
              <div className="modal-body">
                <select className="form-select" value={linkSubjectId} onChange={e => setLinkSubjectId(e.target.value)}>
                  <option value="">选择学科...</option>
                  {allSubjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div className="modal-footer">
                <button className="btn btn-secondary" onClick={() => setShowLinkModal(false)}>取消</button>
                <button className="btn btn-primary" onClick={linkSubject} disabled={!linkSubjectId}>关联</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
