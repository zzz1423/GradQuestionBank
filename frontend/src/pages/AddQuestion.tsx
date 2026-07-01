import { useEffect, useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { Subject, KnowledgePoint, AnalysisResult } from '../types';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface SelectedKP {
  id: number; name: string; chapter: string; role: string; weight: number;
}

export default function AddQuestion() {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectId, setSubjectId] = useState('');
  const [content, setContent] = useState('');
  const [answer, setAnswer] = useState('');
  const [source, setSource] = useState('');
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [aiError, setAiError] = useState('');
  const [previewHtml, setPreviewHtml] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Knowledge point state
  const [allKps, setAllKps] = useState<KnowledgePoint[]>([]);
  const [selectedKps, setSelectedKps] = useState<SelectedKP[]>([]);
  const [manualKpId, setManualKpId] = useState('');
  const [manualRole, setManualRole] = useState('primary');
  const [manualWeight, setManualWeight] = useState('1.0');

  useEffect(() => { api.subjects().then(d => setSubjects(d as Subject[])); }, []);

  // Load knowledge points when subject changes
  useEffect(() => {
    if (!subjectId) { setAllKps([]); return; }
    // We'll load KPs from the review endpoint after question is created,
    // but for now we can preload from subject detail
    api.subjectDetail(Number(subjectId)).then(d => {
      const data = d as { chapters: { id: number; name: string }[] };
      // Load KPs for each chapter
      const all: KnowledgePoint[] = [];
      Promise.all(data.chapters.map(ch =>
        api.chapterDetail(ch.id).then(dd => {
          const kps = (dd as { knowledge_points: KnowledgePoint[] }).knowledge_points;
          kps.forEach(kp => { kp.chapter_name = ch.name; all.push(kp); });
        })
      )).then(() => setAllKps(all)).catch(() => {});
    }).catch(() => {});
  }, [subjectId]);

  const escapeHtml = (str: string) =>
    str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  // LaTeX preview
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!content.trim()) { setPreviewHtml(''); return; }
      try {
        let html = content
          .replace(/\$\$([\s\S]*?)\$\$/g, (_, m) => {
            try { return katex.renderToString(m, { displayMode: true, throwOnError: false }); }
            catch { return `<span class="text-danger">${escapeHtml(m)}</span>`; }
          })
          .replace(/\$([^$]+?)\$/g, (_, m) => {
            try { return katex.renderToString(m, { displayMode: false, throwOnError: false }); }
            catch { return `<span class="text-danger">${escapeHtml(m)}</span>`; }
          })
          .replace(/\n/g, '<br>');
        setPreviewHtml(html);
      } catch { setPreviewHtml(escapeHtml(content)); }
    }, 500);
    return () => clearTimeout(timer);
  }, [content]);

  const handleImage = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => setImageBase64(e.target?.result as string);
    reader.readAsDataURL(file);
  };

  // OCR
  const ocrImage = async () => {
    if (!imageBase64) return;
    setOcrLoading(true);
    setAiError('');
    try {
      const Tesseract = await import('tesseract.js');
      const result = await Tesseract.recognize(imageBase64, 'chi_sim+eng');
      const text = result.data.text.trim();
      if (text) {
        const answerMatch = text.match(/(?:答案|答|Answer)[：:]\s*(.+?)(?:\n|$)/i);
        if (answerMatch) {
          setContent(text.substring(0, answerMatch.index).trim());
          setAnswer(answerMatch[1].trim());
        } else {
          setContent(text);
        }
      } else {
        setAiError('未能识别出文字，请确认图片清晰度');
      }
    } catch (e) {
      setAiError('OCR 识别失败：' + (e as Error).message);
    } finally {
      setOcrLoading(false);
    }
  };

  // AI: analyze knowledge points
  const analyze = async () => {
    if (!content.trim()) { setAiError('请先输入或识别题目内容'); return; }
    setAiLoading(true);
    setAiError('');
    try {
      const subjName = subjects.find(s => String(s.id) === subjectId)?.name || '';
      const result = await api.analyzeQuestion({ content, subject_name: subjName }) as AnalysisResult;
      if (result.error) { setAiError(result.error); return; }
      if (result.latex_content) setContent(result.latex_content);
      if (result.answer && !answer) setAnswer(result.answer);
      // Convert AI result to selected KPs
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
      setSelectedKps(prev => {
        const existingIds = new Set(prev.map(k => k.id));
        return [...prev, ...newKps.filter(k => !existingIds.has(k.id))];
      });
    } catch (e) { setAiError((e as Error).message); }
    finally { setAiLoading(false); }
  };

  const addManualKp = () => {
    if (!manualKpId) return;
    const opt = allKps.find(k => k.id === Number(manualKpId));
    if (!opt || selectedKps.some(k => k.id === opt.id)) return;
    setSelectedKps([...selectedKps, {
      id: opt.id, name: opt.name, chapter: opt.chapter_name || '',
      role: manualRole, weight: parseFloat(manualWeight)
    }]);
    setManualKpId('');
  };

  const removeKp = (idx: number) => setSelectedKps(selectedKps.filter((_, i) => i !== idx));
  const updateRole = (idx: number, role: string) => {
    const next = [...selectedKps];
    next[idx] = { ...next[idx], role, weight: role === 'primary' ? Math.max(0.5, next[idx].weight) : Math.min(0.5, next[idx].weight) };
    setSelectedKps(next);
  };
  const updateWeight = (idx: number, weight: number) => {
    const next = [...selectedKps];
    next[idx] = { ...next[idx], weight };
    setSelectedKps(next);
  };


  // Clean LaTeX formatting
  const cleanLatex = () => {
    let text = content;
    // Strip HTML tags
    text = text.replace(/<[^>]+>/g, '');
    // Remove document structure
    text = text.replace(/\\documentclass[^\n]*\n/g, '');
    text = text.replace(/\\usepackage[^\n]*\n/g, '');
    text = text.replace(/\\geometry[^\n]*\n/g, '');
    text = text.replace(/\\begin\{document\}/g, '');
    text = text.replace(/\\end\{document\}/g, '');
    // Remove formatting
    text = text.replace(/\\noindent\*?/g, '');
    text = text.replace(/\\textbf\{([^}]*)\}/g, '**$1**');
    text = text.replace(/\\textit\{([^}]*)\}/g, '*$1*');
    text = text.replace(/\\emph\{([^}]*)\}/g, '*$1*');
    text = text.replace(/\\(bigskip|medskip|smallskip)\*?/g, '');
    text = text.replace(/\\section\*?\{[^}]*\}/g, '');
    text = text.replace(/\\subsection\*?\{[^}]*\}/g, '');
    // Fix AI typos
    text = text.replace(/\\\$\$6pt\]/g, '\\\\[6pt]');
    text = text.replace(/\\\$\$4pt\]/g, '\\\\[4pt]');
    text = text.replace(/\\\$\$8pt\]/g, '\\\\[8pt]');
    // Convert \[...\] to $$...$$
    text = text.replace(/\\\[([^\]]+)\\\]/g, '$$$$$1$$$$');
    // Convert align* to aligned
    text = text.replace(/\\begin\{align\*\}([\\s\\S]*?)\\end\{align\*\}/g, (_, p1) => {
      return '$$\\begin{aligned}' + p1 + '\\end{aligned}$$';
    });
    // Clean whitespace
    text = text.replace(/\\qquad/g, '  ');
    text = text.replace(/\\quad/g, ' ');
    text = text.replace(/\n{3,}/g, '\n\n');
    text = text.split('\n').map((l: string) => l.trim()).join('\n').trim();
    setContent(text);
  };

  // Save question + knowledge points together
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) { alert('题目内容不能为空'); return; }
    try {
      const result = await api.addQuestion({ subject_id: Number(subjectId), content, answer, source }) as { id: number };
      // Save knowledge points if any
      if (selectedKps.length > 0) {
        await api.saveReview(result.id, selectedKps);
      }
      navigate('/questions');
    } catch (e) {
      alert('保存失败：' + (e as Error).message);
    }
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
            <select className="form-select" required value={subjectId} onChange={e => { setSubjectId(e.target.value); setSelectedKps([]); }}>
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
            <div className="d-flex justify-content-between align-items-center mb-1">
              <label className="form-label mb-0">上传题目图片（可选）</label>
                <div className="d-flex gap-1">
                  {imageBase64 && (
                    <button type="button" className="btn btn-sm btn-outline-primary" onClick={ocrImage} disabled={ocrLoading}>
                      {ocrLoading ? <><span className="spinner-border spinner-border-sm"></span> 识别中...</> : <><i className="bi bi-upc-scan"></i> OCR 识别</>}
                    </button>
                  )}
                  <button type="button" className="btn btn-sm btn-primary" onClick={analyze} disabled={aiLoading || !content.trim()}>
                    {aiLoading ? <><span className="spinner-border spinner-border-sm"></span> 分析中...</> : <><i className="bi bi-stars"></i> AI 分析知识点</>}
                  </button>
                </div>
            </div>
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
            {aiError && <div className="alert alert-danger py-1 mt-2 mb-0"><small>{aiError}</small></div>}
          </div>
          <div className="col-md-6">
            <label className="form-label">LaTeX 预览</label>
            <div className="border rounded p-3" style={{ minHeight: 200, lineHeight: 1.8, overflowY: 'auto' }}
              dangerouslySetInnerHTML={{ __html: previewHtml || '<span class="text-muted">输入内容后自动预览</span>' }} />
          </div>
        </div>

        <div className="mb-3">
          <div className="d-flex justify-content-between align-items-center mb-1">
              <label className="form-label mb-0">题目内容 <span className="text-danger">*</span></label>
              <button type="button" className="btn btn-sm btn-outline-info" onClick={cleanLatex}>
                <i className="bi bi-magic"></i> 清理 LaTeX
              </button>
            </div>
          <textarea className="form-control" rows={6} required value={content} onChange={e => setContent(e.target.value)}
            placeholder="粘贴或 OCR 识别题目内容（支持 LaTeX，如 $x^2$ 或 $$\\int_0^1 f(x)dx$$）" style={{ fontFamily: 'monospace' }} />
          <div className="form-text">支持 LaTeX 数学公式：行内 $...$，独立 $$...$$</div>
        </div>

        <div className="mb-3">
          <label className="form-label">答案</label>
          <input type="text" className="form-control" value={answer} onChange={e => setAnswer(e.target.value)}
            placeholder="填写结果即可，如：C 或 42 或简要文字答案" />
        </div>

        {/* Knowledge Points Panel */}
        <div className="card mb-3">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span><i className="bi bi-diagram-3"></i> 关联知识点</span>
            <button type="button" className="btn btn-sm btn-primary" onClick={analyze}
              disabled={aiLoading || !content.trim()}>
              {aiLoading ? <><span className="spinner-border spinner-border-sm"></span> 分析中...</> : <><i className="bi bi-stars"></i> AI 分析知识点</>}
            </button>
          </div>
          <div className="card-body">
            {/* Selected KPs */}
            {selectedKps.length > 0 ? (
              <div className="mb-3">
                {selectedKps.map((kp, idx) => (
                  <div key={idx} className="card mb-2">
                    <div className="card-body p-2">
                      <div className="d-flex justify-content-between align-items-center mb-1">
                        <div>
                          <span className={`badge ${kp.role === 'primary' ? 'bg-primary' : 'bg-secondary'} me-1`}>
                            {kp.role === 'primary' ? '主要' : '次要'}
                          </span>
                          <strong>{kp.name}</strong>
                          <small className="text-muted ms-1">{kp.chapter}</small>
                        </div>
                        <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => removeKp(idx)}>&times;</button>
                      </div>
                      <div className="row g-2">
                        <div className="col-6">
                          <select className="form-select form-select-sm" value={kp.role} onChange={e => updateRole(idx, e.target.value)}>
                            <option value="primary">主要知识点</option>
                            <option value="secondary">次要知识点</option>
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
            ) : (
              <div className="text-muted mb-3">点击上方按钮，AI 将自动分析题目涉及的知识点</div>
            )}

            {/* Manual add */}
            <div className="border-top pt-3">
              <div className="row g-2 align-items-end">
                <div className="col-md-5">
                  <select className="form-select form-select-sm" value={manualKpId} onChange={e => setManualKpId(e.target.value)}>
                    <option value="">手动添加知识点...</option>
                    {allKps.map(kp => <option key={kp.id} value={kp.id}>{kp.chapter_name} &gt; {kp.name}</option>)}
                  </select>
                </div>
                <div className="col-md-3">
                  <select className="form-select form-select-sm" value={manualRole} onChange={e => setManualRole(e.target.value)}>
                    <option value="primary">主要</option>
                    <option value="secondary">次要</option>
                  </select>
                </div>
                <div className="col-md-2">
                  <input type="number" className="form-control form-control-sm" value={manualWeight}
                    onChange={e => setManualWeight(e.target.value)} min={0.1} max={1} step={0.1} />
                </div>
                <div className="col-md-2">
                  <button type="button" className="btn btn-sm btn-outline-primary w-100" onClick={addManualKp}>添加</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="d-flex gap-2">
          <button type="submit" className="btn btn-primary btn-lg">
            <i className="bi bi-check-circle"></i> 保存题目
          </button>
          <Link to="/questions" className="btn btn-outline-secondary btn-lg">取消</Link>
        </div>
      </form>
    </>
  );
}
