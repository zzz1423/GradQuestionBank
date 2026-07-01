import { useEffect, useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { Subject, AnalysisResult } from '../types';
import katex from 'katex';
import 'katex/dist/katex.min.css';

/**
 * Renders the form for creating a new question.
 *
 * @returns The add-question page with subject selection, question content, optional image upload, AI analysis, and submission actions.
 */
export default function AddQuestion() {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectId, setSubjectId] = useState('');
  const [content, setContent] = useState('');
  const [answer, setAnswer] = useState('');
  const [source, setSource] = useState('');
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<AnalysisResult | null>(null);
  const [aiError, setAiError] = useState('');
  const [previewHtml, setPreviewHtml] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { api.subjects().then(d => setSubjects(d as Subject[])); }, []);

  // LaTeX preview
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!content.trim()) { setPreviewHtml(''); return; }
      try {
        let html = content
          .replace(/\$\$([\s\S]*?)\$\$/g, (_, m) => {
            try { return katex.renderToString(m, { displayMode: true, throwOnError: false }); }
            catch { return `<span class="text-danger">${m}</span>`; }
          })
          .replace(/\$([^$]+?)\$/g, (_, m) => {
            try { return katex.renderToString(m, { displayMode: false, throwOnError: false }); }
            catch { return `<span class="text-danger">${m}</span>`; }
          })
          .replace(/\n/g, '<br>');
        setPreviewHtml(html);
      } catch { setPreviewHtml(content); }
    }, 500);
    return () => clearTimeout(timer);
  }, [content]);

  const handleImage = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => setImageBase64(e.target?.result as string);
    reader.readAsDataURL(file);
  };

  const analyze = async () => {
    setAiLoading(true);
    setAiError('');
    setAiResult(null);
    try {
      const subjName = subjects.find(s => String(s.id) === subjectId)?.name || '';
      const body: Record<string, unknown> = { content, subject_name: subjName };
      if (imageBase64) body.image = imageBase64;
      const result = await api.analyzeQuestion(body) as AnalysisResult;
      setAiResult(result);
      if (result.latex_content) setContent(result.latex_content);
      if (result.answer) setAnswer(result.answer);
    } catch (e) { setAiError((e as Error).message); }
    finally { setAiLoading(false); }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) { alert('题干不能为空'); return; }
    const result = await api.addQuestion({ subject_id: Number(subjectId), content, answer, source }) as { id: number };
    navigate(`/questions/${result.id}/review`);
  };

  return (
    <>
      <nav aria-label="breadcrumb" className="mb-3">
        <ol className="breadcrumb">
          <li className="breadcrumb-item"><Link to="/questions">题目列表</Link></li>
          <li className="breadcrumb-item active">录入新题目</li>
        </ol>
      </nav>

      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4>录入新题目</h4>
        <Link to="/questions/batch" className="btn btn-outline-primary">
          <i className="bi bi-upload"></i> 批量录入
        </Link>
      </div>

      <form onSubmit={submit}>
        <div className="row g-3 mb-3">
          <div className="col-md-6">
            <label className="form-label">学科 <span className="text-danger">*</span></label>
            <select className="form-select" required value={subjectId} onChange={e => setSubjectId(e.target.value)}>
              <option value="">请选择学科</option>
              {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="col-md-6">
            <label className="form-label">来源</label>
            <input type="text" className="form-control" placeholder="如：2024年真题" value={source} onChange={e => setSource(e.target.value)} />
          </div>
        </div>

        <div className="row g-3 mb-3">
          <div className="col-md-6">
            <label className="form-label">上传题目图片（可选）</label>
            {imageBase64 ? (
              <>
                <div className="border rounded p-2 text-center">
                  <img src={imageBase64} alt="预览" style={{ maxWidth: '100%', maxHeight: 300, borderRadius: 4 }} />
                </div>
                <button type="button" className="btn btn-sm btn-outline-danger mt-1" onClick={() => setImageBase64(null)}>
                  <i className="bi bi-trash"></i> 移除图片
                </button>
              </>
            ) : (
              <div className="border border-2 border-dashed rounded p-4 text-center" style={{ cursor: 'pointer', minHeight: 200 }}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); if (e.dataTransfer.files[0]) handleImage(e.dataTransfer.files[0]); }}>
                <i className="bi bi-cloud-arrow-up fs-1 text-muted"></i>
                <p className="text-muted mb-0">拖拽图片到此处，或点击上传</p>
                <small className="text-muted">支持 JPG、PNG、GIF</small>
              </div>
            )}
            <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={e => { if (e.target.files?.[0]) handleImage(e.target.files[0]); }} />
          </div>
          <div className="col-md-6">
            <label className="form-label">LaTeX 预览</label>
            <div className="border rounded p-3" style={{ minHeight: 200, lineHeight: 1.8, overflowY: 'auto' }}
              dangerouslySetInnerHTML={{ __html: previewHtml || '<span class="text-muted">输入内容后自动预览</span>' }} />
          </div>
        </div>

        <div className="mb-3">
          <label className="form-label">题目内容 <span className="text-danger">*</span></label>
          <textarea className="form-control" rows={6} required value={content} onChange={e => setContent(e.target.value)}
            placeholder="粘贴题目内容（支持 LaTeX，如 $x^2$ 或 $$\\int_0^1 f(x)dx$$）" style={{ fontFamily: 'monospace' }} />
          <div className="form-text">支持 LaTeX 数学公式：行内 $...$ ，独立 $$...$$</div>
        </div>

        <div className="mb-3">
          <label className="form-label">答案</label>
          <input type="text" className="form-control" value={answer} onChange={e => setAnswer(e.target.value)}
            placeholder="填写结果即可，如：C 或 42 或简要文字答案" />
        </div>

        {/* AI Panel */}
        <div className="bg-light rounded p-3 mb-3">
          <div className="d-flex justify-content-between align-items-center mb-2">
            <h6 className="mb-0"><i className="bi bi-robot"></i> AI 辅助分析</h6>
            <button type="button" className="btn btn-primary" onClick={analyze} disabled={aiLoading}>
              {aiLoading ? <><span className="spinner-border spinner-border-sm"></span> 分析中...</> : <><i className="bi bi-stars"></i> AI 分析题目</>}
            </button>
          </div>
          {aiError && <div className="alert alert-danger py-1 mt-2">{aiError}</div>}
          {aiResult && (
            <div className="mt-2">
              <div className="row g-3">
                <div className="col-md-6">
                  <label className="form-label small">AI 识别的题目内容</label>
                  <div className="bg-white p-2 rounded border" style={{ maxHeight: 150, overflowY: 'auto' }}>{aiResult.latex_content || aiResult.content}</div>
                </div>
                <div className="col-md-6">
                  <label className="form-label small">AI 建议的知识点</label>
                  <div className="bg-white p-2 rounded border" style={{ maxHeight: 150, overflowY: 'auto' }}>
                    {(aiResult.knowledge_points || []).map((kp, i) => (
                      <span key={i} className={`badge ${kp.role === 'primary' ? 'bg-primary' : 'bg-secondary'} me-1 mb-1`}>
                        {kp.name} ({kp.weight})
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="d-flex gap-2">
          <button type="submit" className="btn btn-primary"><i className="bi bi-check-circle"></i> 保存题目</button>
          <Link to="/questions" className="btn btn-outline-secondary">取消</Link>
        </div>
      </form>
    </>
  );
}
