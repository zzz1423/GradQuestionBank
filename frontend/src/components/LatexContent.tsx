import katex from 'katex';
import 'katex/dist/katex.min.css';

function renderLatex(text: string): string {
  if (!text) return '';
  const esc = (t: string) =>
    t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  let html = '';
  let lastIdx = 0;
  const re = /\$\$(.+?)\$\$|\$(.+?)\$/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIdx) html += esc(text.slice(lastIdx, m.index));
    const display = m[1] !== undefined;
    let tex = m[1] ?? m[2];
    try {
      tex = decodeURIComponent(tex);
    } catch {
      // keep the raw LaTeX when it is not URI-encoded
    }
    try {
      html += katex.renderToString(tex, { displayMode: display, throwOnError: false });
    } catch {
      html += esc(`$${tex}$`);
    }
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < text.length) html += esc(text.slice(lastIdx));
  return html;
}

export default function LatexContent({ text, className }: { text: string; className?: string }) {
  return (
    <div
      className={className}
      style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}
      dangerouslySetInnerHTML={{ __html: renderLatex(text) }}
    />
  );
}
