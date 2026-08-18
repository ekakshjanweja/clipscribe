const form = document.querySelector('#upload-form');
const input = document.querySelector('#video-input');
const dropZone = document.querySelector('#drop-zone');
const submitButton = document.querySelector('#submit-button');
const fileInfo = document.querySelector('#file-info');
const fileName = document.querySelector('#file-name');
const empty = document.querySelector('#empty-state');
const loading = document.querySelector('#loading-state');
const transcript = document.querySelector('#transcript');
const segments = document.querySelector('#segments');
const error = document.querySelector('#error-message');
const copyButton = document.querySelector('#copy-button');
const resultActions = document.querySelector('#result-actions');
const txtDownload = document.querySelector('#download-txt');
const mdDownload = document.querySelector('#download-md');
const engine = document.querySelector('#engine');
const engineNote = document.querySelector('#engine-note');
let transcriptText = '';
let transcriptRows = [];

function chooseFile(file) {
  if (!file) return;
  const transfer = new DataTransfer(); transfer.items.add(file); input.files = transfer.files;
  fileName.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
  fileInfo.hidden = false; submitButton.disabled = false; error.hidden = true;
}
input.addEventListener('change', () => chooseFile(input.files[0]));
['dragenter', 'dragover'].forEach(event => dropZone.addEventListener(event, e => { e.preventDefault(); dropZone.classList.add('is-over'); }));
['dragleave', 'drop'].forEach(event => dropZone.addEventListener(event, e => { e.preventDefault(); dropZone.classList.remove('is-over'); }));
dropZone.addEventListener('drop', e => chooseFile(e.dataTransfer.files[0]));
document.querySelector('#clear-file').addEventListener('click', () => { input.value = ''; fileInfo.hidden = true; submitButton.disabled = true; });
engine.addEventListener('change', () => {
  engineNote.textContent = engine.value === 'paddle-vl'
    ? 'PaddleOCR-VL 1.6 runs locally in a separate environment. Its first use downloads model files; expect a slower scan.'
    : 'Apple Vision is the fast, native default. PaddleOCR-VL 1.6 is slower but better for complex documents, tables, and mixed layouts.';
});

form.addEventListener('submit', async e => {
  e.preventDefault(); if (!input.files[0]) return;
  empty.hidden = true; transcript.hidden = true; error.hidden = true; resultActions.hidden = true; loading.hidden = false; submitButton.disabled = true;
  try {
    const response = await fetch('/scan', { method: 'POST', body: new FormData(form) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Something went wrong.');
    transcriptText = data.text;
    transcriptRows = data.segments;
    document.querySelector('#language').textContent = `ENGINE / ${data.language.toUpperCase()}`;
    document.querySelector('#duration').textContent = `ENDS / ${data.duration}`;
    document.querySelector('#cleanup-summary').textContent = `${data.frames_processed} FRAMES → ${data.cleaned_blocks} CLEAN BLOCKS`;
    segments.replaceChildren(...data.segments.map(row => {
      const article = document.createElement('article'); article.className = 'segment';
      article.innerHTML = `<time>${row.start}</time><p>${row.text}</p>`; return article;
    }));
    loading.hidden = true; transcript.hidden = false; resultActions.hidden = false;
  } catch (err) { loading.hidden = true; empty.hidden = false; error.textContent = err.message; error.hidden = false; }
  finally { submitButton.disabled = false; }
});
copyButton.addEventListener('click', async () => { await navigator.clipboard.writeText(transcriptText); copyButton.textContent = 'Copied'; setTimeout(() => copyButton.textContent = 'Copy text', 1500); });
function download(name, contents, type) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([contents], { type: `${type};charset=utf-8` }));
  link.download = name; link.click(); URL.revokeObjectURL(link.href);
}
txtDownload.addEventListener('click', () => download('clipscribe-text.txt', transcriptRows.map(row => `[${row.start}] ${row.text}`).join('\n\n'), 'text/plain'));
mdDownload.addEventListener('click', () => download('clipscribe-text.md', `# ClipScribe OCR export\n\n${transcriptRows.map(row => `## ${row.start}\n\n${row.text}`).join('\n\n')}`, 'text/markdown'));
