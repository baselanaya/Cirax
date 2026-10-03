// Extracts plain text from a resume/job-description file (PDF or DOCX) so it can be
// dropped into the existing Settings textareas. No OCR — text layer only.
const fs = require('fs');
const path = require('path');

async function parseDocumentFile(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const buf = fs.readFileSync(filePath);
  let text = '';
  if (ext === '.pdf') {
    const pdfParse = require('pdf-parse');
    const res = await pdfParse(buf);
    text = (res.text || '').trim();
  } else if (ext === '.docx') {
    const mammoth = require('mammoth');
    const res = await mammoth.extractRawText({ buffer: buf });
    text = (res.value || '').trim();
  } else {
    throw new Error('Unsupported file type: ' + (ext || '(none)') + '. Use a PDF or DOCX file.');
  }
  // A scanned PDF has no text layer — importing it "successfully" with an
  // empty payload silently throws away the user's resume context.
  if (!text) {
    throw new Error('No extractable text found — the file is likely a scan or image-only export. Paste the text manually.');
  }
  return text;
}

module.exports = { parseDocumentFile };
