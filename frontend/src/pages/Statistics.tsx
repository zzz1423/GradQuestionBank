import { useEffect, useState, useRef } from 'react';
import { api } from '../api';
import { MASTERY_LABELS, type MasteryDist, type SubjectStat, type WeakPoint } from '../types';
import { Chart, DoughnutController, BarController, ArcElement, BarElement, CategoryScale, LinearScale, Legend, Tooltip } from 'chart.js';

Chart.register(DoughnutController, BarController, ArcElement, BarElement, CategoryScale, LinearScale, Legend, Tooltip);

export default function Statistics() {
  const [masteryDist, setMasteryDist] = useState<MasteryDist[]>([]);
  const [weakPoints, setWeakPoints] = useState<WeakPoint[]>([]);
  const [subjectStats, setSubjectStats] = useState<SubjectStat[]>([]);
  const pieRef = useRef<HTMLCanvasElement>(null);
  const barRef = useRef<HTMLCanvasElement>(null);
  const pieChart = useRef<Chart | null>(null);
  const barChart = useRef<Chart | null>(null);

  useEffect(() => {
    api.statistics().then(d => {
      const data = d as { mastery_distribution: MasteryDist[]; weak_points: WeakPoint[]; subject_stats: SubjectStat[] };
      setMasteryDist(data.mastery_distribution);
      setWeakPoints(data.weak_points);
      setSubjectStats(data.subject_stats);
    });
  }, []);

  useEffect(() => {
    if (!pieRef.current || masteryDist.length === 0) return;
    pieChart.current?.destroy();
    const colors: Record<number, string> = { 0: '#6c757d', 1: '#dc3545', 2: '#fd7e14', 3: '#ffc107', 4: '#20c997', 5: '#198754' };
    pieChart.current = new Chart(pieRef.current, {
      type: 'doughnut',
      data: {
        labels: masteryDist.map(d => MASTERY_LABELS[d.mastery_level]),
        datasets: [{ data: masteryDist.map(d => d.count), backgroundColor: masteryDist.map(d => colors[d.mastery_level]) }],
      },
      options: { responsive: true, plugins: { legend: { position: 'bottom' } } },
    });
  }, [masteryDist]);

  useEffect(() => {
    if (!barRef.current || subjectStats.length === 0) return;
    barChart.current?.destroy();
    const subjects = [...new Set(subjectStats.map(d => d.name))];
    const levelColors: Record<number, string> = { 1: '#dc3545', 2: '#fd7e14', 3: '#ffc107', 4: '#20c997', 5: '#198754' };
    const levelLabels: Record<number, string> = { 1: '知识盲区', 2: '只做了开头', 3: '易错细节', 4: '独立完成', 5: '轻松秒杀' };
    barChart.current = new Chart(barRef.current, {
      type: 'bar',
      data: {
        labels: subjects,
        datasets: [1, 2, 3, 4, 5].map(level => ({
          label: levelLabels[level],
          data: subjects.map(name => subjectStats.find(d => d.name === name && d.mastery_level === level)?.count || 0),
          backgroundColor: levelColors[level],
        })),
      },
      options: { responsive: true, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } }, plugins: { legend: { position: 'bottom' } } },
    });
  }, [subjectStats]);

  // Cleanup charts on unmount
  useEffect(() => {
    return () => {
      pieChart.current?.destroy();
      barChart.current?.destroy();
    };
  }, []);

  return (
    <>
      <h4 className="mb-4">统计分析</h4>
      <div className="row g-3 mb-4">
        <div className="col-md-6">
          <div className="card h-100">
            <div className="card-header">掌握度分布</div>
            <div className="card-body">
              {masteryDist.length > 0 ? <canvas ref={pieRef} height={160}></canvas> : <div className="text-muted text-center py-5">暂无数据</div>}
            </div>
          </div>
        </div>
        <div className="col-md-6">
          <div className="card h-100">
            <div className="card-header">按学科掌握度</div>
            <div className="card-body">
              {subjectStats.length > 0 ? <canvas ref={barRef} height={160}></canvas> : <div className="text-muted text-center py-5">暂无数据</div>}
            </div>
          </div>
        </div>
      </div>
      <div className="card mb-4">
        <div className="card-header"><i className="bi bi-exclamation-triangle text-warning"></i> 知识点掌握情况</div>
        <div className="card-body p-0">
          {weakPoints.length > 0 ? (
            <div className="accordion" id="examAccordion">
              {(() => {
                const grouped: Record<string, Record<string, typeof weakPoints>> = {};
                for (const kp of weakPoints) {
                  const exam = (kp as any).exam_name || '未分类';
                  if (!grouped[exam]) grouped[exam] = {};
                  if (!grouped[exam][kp.subject_name]) grouped[exam][kp.subject_name] = [];
                  grouped[exam][kp.subject_name].push(kp);
                }
                let gi = 0;
                return Object.entries(grouped).map(([exam, subjects]) => {
                  const eid = exam.replace(/[^\w]/g, '_');
                  return (
                    <div className="accordion-item" key={eid}>
                      <h2 className="accordion-header">
                        <button className="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target={`#exam-${eid}`}>
                          <strong>{exam}</strong>
                        </button>
                      </h2>
                      <div id={`exam-${eid}`} className="accordion-collapse collapse">
                        <div className="accordion-body p-0">
                          {Object.entries(subjects).map(([subj, kps]) => (
                            <div key={subj} className="border-bottom">
                              <div className="px-3 py-2 bg-light fw-bold"><i className="bi bi-collection"></i> {subj}</div>
                              <table className="table table-sm table-hover mb-0">
                                <thead className="table-light">
                                  <tr><th style={{width:40}}>#</th><th>知识点</th><th>题目数</th><th>掌握率</th><th>薄弱指数</th></tr>
                                </thead>
                                <tbody>
                                  {kps.map((kp) => {
                                    gi++;
                                    return (
                                      <tr key={`${subj}-${kp.name}`}>
                                        <td className="text-muted">{gi}</td>
                                        <td><strong>{kp.name}</strong></td>
                                        <td>{kp.total}</td>
                                        <td>
                                          <div className="progress" style={{ minWidth: 80, height: 18 }}>
                                            <div className="progress-bar bg-success" style={{ width: `${kp.mastery_rate}%` }}>{kp.mastery_rate.toFixed(0)}%</div>
                                          </div>
                                        </td>
                                        <td>
                                          <span className={`badge ${kp.weakness_score > 0.6 ? 'bg-danger' : kp.weakness_score > 0.3 ? 'bg-warning text-dark' : 'bg-success'}`}>
                                            {kp.weakness_score.toFixed(2)}
                                          </span>
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          ) : <div className="text-center text-muted py-4">暂无做题数据</div>}
        </div>
      </div>
    </>
  );
}
