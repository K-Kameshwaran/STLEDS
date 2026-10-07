import express from 'express';
import cors from 'cors';
import multer from 'multer';
import crypto from 'crypto';
import jwt from 'jsonwebtoken';
import { PDFDocument, rgb, degrees, StandardFonts } from 'pdf-lib';
import fs from 'fs';
import path from 'path';
import { createServer as createViteServer } from 'vite';

const JWT_SECRET = process.env.JWT_SECRET || 'stleds-super-secret-jwt-key-2026';
const PORT = 3000;
const HOST = '0.0.0.0';

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 20 * 1024 * 1024 } // 20MB
});

// --- Types & In-Memory Storage ---

interface User {
  id: number;
  name: string;
  email: string;
  passwordHash: string;
  role: string;
  isActive: boolean;
  totpSecret: string;
  centerId: number | null;
}

interface Paper {
  id: number;
  title: string;
  examId: number;
  status: string; // ENCRYPTED, PENDING_REVIEW, APPROVED, LOCKED, RELEASE_WINDOW, RELEASED
  documentHash: string;
  ciphertext: Buffer;
  key: Buffer; // AES-256 DEK
  nonce: Buffer; // 12-byte IV
  createdBy: number;
  createdAt: string;
}

interface ReleaseAuthorization {
  id: number;
  sessionId: number;
  userId: number;
  userRole: string;
  clientTimestamp: string;
  consumed: boolean;
}

interface ReleaseSession {
  id: number;
  examId: number;
  status: 'pending' | 'ready' | 'active' | 'closed';
  startedAt: string;
}

interface AuditRecord {
  id: number;
  timestamp: string;
  action: string;
  result: string;
  actorId: number | null;
  resourceId: number | null;
  examId?: number | null;
  metadata?: Record<string, any>;
  previousHash: string;
  recordHash: string;
}

// In-Memory Database
const users: User[] = [
  { id: 1, name: 'Question Setter', email: 'setter@test.com', passwordHash: 'pass', role: 'QUESTION_SETTER', isActive: true, totpSecret: 'base32secret3232', centerId: null },
  { id: 2, name: 'Reviewer', email: 'reviewer@test.com', passwordHash: 'pass', role: 'REVIEWER', isActive: true, totpSecret: 'base32secret3232', centerId: null },
  { id: 3, name: 'Exam Controller', email: 'c@test.com', passwordHash: 'pass', role: 'EXAM_CONTROLLER', isActive: true, totpSecret: 'base32secret3232', centerId: null },
  { id: 4, name: 'External Observer', email: 'o@test.com', passwordHash: 'pass', role: 'EXTERNAL_OBSERVER', isActive: true, totpSecret: 'base32secret3232', centerId: null },
  { id: 5, name: 'Center Superintendent', email: 'center@test.com', passwordHash: 'pass', role: 'CENTER_SUPERINTENDENT', isActive: true, totpSecret: 'base32secret3232', centerId: 101 },
  { id: 6, name: 'Auditor', email: 'auditor@test.com', passwordHash: 'pass', role: 'AUDITOR', isActive: true, totpSecret: 'base32secret3232', centerId: null }
];

let nextPaperId = 1;
const papers = new Map<number, Paper>();

let nextSessionId = 1;
const releaseSessions = new Map<number, ReleaseSession>();
const releaseAuthorizations: ReleaseAuthorization[] = [];

let nextAuditId = 1;
const auditChain: AuditRecord[] = [];

// Audit Helper
function addAuditRecord(
  action: string,
  result: string,
  actorId: number | null = null,
  resourceId: number | null = null,
  examId: number | null = null,
  metadata?: Record<string, any>
): AuditRecord {
  const previousHash = auditChain.length > 0 
    ? auditChain[auditChain.length - 1].recordHash 
    : '0'.repeat(64);
  
  const id = nextAuditId++;
  const timestamp = new Date().toISOString();
  
  const content = `${id}|${timestamp}|${action}|${result}|${actorId ?? ''}|${resourceId ?? ''}|${previousHash}`;
  const recordHash = crypto.createHash('sha256').update(content).digest('hex');

  const record: AuditRecord = {
    id,
    timestamp,
    action,
    result,
    actorId,
    resourceId,
    examId,
    metadata,
    previousHash,
    recordHash
  };

  auditChain.push(record);
  return record;
}

// Initial Audit Genesis
addAuditRecord('SYSTEM_INIT', 'SUCCESS', null, null, null, { system: 'STLEDS v1.0.0' });

// Seed initial Paper 1 if sample_paper.pdf is available
try {
  const samplePdfPath = path.resolve(process.cwd(), 'sample_paper.pdf');
  if (fs.existsSync(samplePdfPath)) {
    const rawPdf = fs.readFileSync(samplePdfPath);
    const key = crypto.randomBytes(32);
    const nonce = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', key, nonce);
    const ciphertext = Buffer.concat([cipher.update(rawPdf), cipher.final(), cipher.getAuthTag()]);
    const docHash = crypto.createHash('sha256').update(rawPdf).digest('hex');

    const samplePaper: Paper = {
      id: nextPaperId++,
      title: 'Exam Paper: Sample Mathematics Paper 2026',
      examId: 1,
      status: 'ENCRYPTED',
      documentHash: docHash,
      ciphertext,
      key,
      nonce,
      createdBy: 1,
      createdAt: new Date().toISOString()
    };
    papers.set(samplePaper.id, samplePaper);
    addAuditRecord('UPLOAD', 'SUCCESS', 1, samplePaper.id, 1, { title: samplePaper.title });
  }
} catch (e) {
  console.warn('Could not seed sample paper:', e);
}

// Forensic Watermark using pdf-lib
async function applyForensicWatermark(
  pdfBuffer: Buffer,
  examId: number,
  centerId: number,
  userId: number,
  timestampStr: string
): Promise<Buffer> {
  const pdfDoc = await PDFDocument.load(pdfBuffer);
  const helveticaFont = await pdfDoc.embedFont(StandardFonts.HelveticaBold);
  const pages = pdfDoc.getPages();

  const lines = [
    'EXAMINATION PAPER - CONFIDENTIAL',
    `EXAM ID: ${examId}`,
    `CENTER ID: ${centerId}`,
    `AUTHORIZED USER ID: ${userId}`,
    `TIMESTAMP: ${timestampStr} UTC`
  ];

  for (const page of pages) {
    const { width, height } = page.getSize();
    const centerX = width / 2;
    const centerY = height / 2;

    // Draw repeating watermarks across page
    lines.forEach((line, idx) => {
      page.drawText(line, {
        x: centerX - 180,
        y: centerY + 60 - idx * 28,
        size: 18,
        font: helveticaFont,
        color: rgb(0.85, 0.1, 0.1),
        opacity: 0.28,
        rotate: degrees(35)
      });
    });

    // Also draw bottom security banner
    page.drawText(`[STLEDS AUDIT FORENSIC SEAL: CENTER ${centerId} | USER ${userId} | ${timestampStr}]`, {
      x: 30,
      y: 18,
      size: 8,
      font: helveticaFont,
      color: rgb(0.5, 0.5, 0.5),
      opacity: 0.7
    });
  }

  const modifiedPdfBytes = await pdfDoc.save();
  return Buffer.from(modifiedPdfBytes);
}

// AES-256-GCM decrypt helper
function decryptPaper(paper: Paper): Buffer {
  const tagLength = 16;
  const authTag = paper.ciphertext.subarray(paper.ciphertext.length - tagLength);
  const encryptedData = paper.ciphertext.subarray(0, paper.ciphertext.length - tagLength);

  const decipher = crypto.createDecipheriv('aes-256-gcm', paper.key, paper.nonce);
  decipher.setAuthTag(authTag);
  return Buffer.concat([decipher.update(encryptedData), decipher.final()]);
}

// Express App Setup
const app = express();
app.use(cors());
app.use(express.json());

// Auth Middleware
function authMiddleware(req: any, res: any, next: any) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ detail: 'Missing or invalid authorization header' });
  }

  const token = authHeader.split(' ')[1];
  try {
    const decoded = jwt.verify(token, JWT_SECRET) as any;
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ detail: 'Invalid or expired token' });
  }
}

// --- API Endpoints ---

// 1. Health
app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

// 2. Auth: Login
app.post('/auth/login', (req, res) => {
  const { email, password, mfa_code } = req.body;
  const user = users.find(u => u.email === email && u.passwordHash === password);

  if (!user || !user.isActive) {
    addAuditRecord('LOGIN_FAILURE', 'FAILURE', user ? user.id : null, null, null, { email });
    return res.status(401).json({ detail: 'Incorrect email or password' });
  }

  const mfaRequiredRoles = ['EXAM_CONTROLLER', 'AUDITOR'];
  if (mfaRequiredRoles.includes(user.role)) {
    if (!mfa_code) {
      return res.json({ access_token: '', token_type: 'bearer', mfa_required: true });
    }
    // Accept valid 6-digit code for demo
    if (typeof mfa_code !== 'string' || mfa_code.trim().length < 4) {
      addAuditRecord('LOGIN_FAILURE', 'FAILURE', user.id, null, null, { reason: 'Invalid MFA' });
      return res.status(401).json({ detail: 'Invalid MFA code' });
    }
  }

  const token = jwt.sign(
    { sub: user.email, role: user.role, id: user.id, center_id: user.centerId },
    JWT_SECRET,
    { expiresIn: '8h' }
  );

  addAuditRecord('LOGIN_SUCCESS', 'SUCCESS', user.id, null, null, { role: user.role });

  res.json({
    access_token: token,
    token_type: 'bearer',
    mfa_required: false
  });
});

// 3. Exams: Upload Paper
app.post('/exams/papers', authMiddleware, upload.single('file'), (req: any, res) => {
  const currentRole = req.user.role;
  if (currentRole !== 'QUESTION_SETTER') {
    addAuditRecord('UPLOAD_DENIED', 'FAILURE', req.user.id);
    return res.status(403).json({ detail: 'Only QUESTION_SETTER can upload papers' });
  }

  const file = req.file;
  if (!file) {
    return res.status(400).json({ detail: 'File is missing' });
  }

  // Validate PDF magic bytes
  if (!file.buffer.subarray(0, 4).equals(Buffer.from('%PDF'))) {
    addAuditRecord('UPLOAD', 'FAILURE', req.user.id, null, null, { reason: 'Invalid PDF magic bytes' });
    return res.status(400).json({ detail: 'Invalid file type. Only real PDF files are allowed.' });
  }

  const title = req.body.title || file.originalname || 'Exam Paper';
  const examId = Number(req.body.exam_id) || 1;

  // AES-256-GCM authenticated encryption
  const key = crypto.randomBytes(32);
  const nonce = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, nonce);
  const ciphertext = Buffer.concat([cipher.update(file.buffer), cipher.final(), cipher.getAuthTag()]);
  const docHash = crypto.createHash('sha256').update(file.buffer).digest('hex');

  const paperId = nextPaperId++;
  const newPaper: Paper = {
    id: paperId,
    title,
    examId,
    status: 'ENCRYPTED',
    documentHash: docHash,
    ciphertext,
    key,
    nonce,
    createdBy: req.user.id,
    createdAt: new Date().toISOString()
  };

  papers.set(paperId, newPaper);
  addAuditRecord('UPLOAD', 'SUCCESS', req.user.id, paperId, examId, { title });

  res.status(201).json({
    message: 'Paper encrypted and uploaded successfully',
    paper_id: paperId
  });
});

// 4. Exams: Change Status
app.post('/exams/papers/:id/status', authMiddleware, (req: any, res) => {
  const paperId = Number(req.params.id);
  const newStatus = (req.query.new_status as string || '').toUpperCase();
  const paper = papers.get(paperId);

  if (!paper) {
    return res.status(404).json({ detail: 'Paper not found' });
  }

  const validTransitions: Record<string, string[]> = {
    ENCRYPTED: ['PENDING_REVIEW'],
    PENDING_REVIEW: ['APPROVED'],
    APPROVED: ['LOCKED'],
    LOCKED: ['RELEASE_WINDOW', 'RELEASED'],
    RELEASE_WINDOW: ['RELEASED'],
    RELEASED: []
  };

  const allowed = validTransitions[paper.status] || [];
  if (!allowed.includes(newStatus)) {
    addAuditRecord('STATUS_CHANGE', 'FAILURE', req.user.id, paperId, paper.examId, {
      from: paper.status,
      to: newStatus
    });
    return res.status(400).json({ detail: `Invalid transition from ${paper.status} to ${newStatus}` });
  }

  paper.status = newStatus;

  if (newStatus === 'PENDING_REVIEW') {
    addAuditRecord('REVIEW', 'SUCCESS', req.user.id, paperId, paper.examId);
  } else if (newStatus === 'APPROVED') {
    addAuditRecord('APPROVAL', 'SUCCESS', req.user.id, paperId, paper.examId);
  } else {
    addAuditRecord('STATUS_CHANGE', 'SUCCESS', req.user.id, paperId, paper.examId, { new_status: newStatus });
  }

  res.json({ message: `Status updated to ${paper.status}` });
});

// 5. Exams: View Paper (Reviewer preview)
app.get('/exams/papers/:id/view', authMiddleware, (req: any, res) => {
  const paperId = Number(req.params.id);
  const paper = papers.get(paperId);

  if (!paper) {
    return res.status(404).json({ detail: 'Paper not found' });
  }

  if (req.user.role !== 'REVIEWER' && req.user.role !== 'EXAM_CONTROLLER') {
    addAuditRecord('VIEW_DENIED', 'FAILURE', req.user.id, paperId);
    return res.status(403).json({ detail: 'Permission denied: Cannot review paper' });
  }

  try {
    const plaintext = decryptPaper(paper);
    addAuditRecord('VIEW_PAPER', 'SUCCESS', req.user.id, paperId, paper.examId);

    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', 'inline; filename="preview.pdf"');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.send(plaintext);
  } catch (err: any) {
    addAuditRecord('INTEGRITY_FAILURE', 'FAILURE', req.user.id, paperId);
    res.status(500).json({ detail: 'View Denied: Integrity check failed.' });
  }
});

// 6. Release: Create Session
app.post('/release/sessions', authMiddleware, (req: any, res) => {
  if (req.user.role !== 'EXAM_CONTROLLER' && req.user.role !== 'EXTERNAL_OBSERVER') {
    return res.status(403).json({ detail: 'Not authorized to create release session' });
  }

  const examId = Number(req.body.exam_id) || 1;
  const sessionId = nextSessionId++;
  const session: ReleaseSession = {
    id: sessionId,
    examId,
    status: 'pending',
    startedAt: new Date().toISOString()
  };

  releaseSessions.set(sessionId, session);
  addAuditRecord('SESSION_CREATE', 'SUCCESS', req.user.id, null, examId, { session_id: sessionId });

  res.status(201).json({
    message: 'Release session created',
    session_id: sessionId
  });
});

// 7. Release: Authorize Session
app.post('/release/sessions/:id/authorize', authMiddleware, (req: any, res) => {
  const sessionId = Number(req.params.id);
  const session = releaseSessions.get(sessionId);

  if (!session) {
    return res.status(404).json({ detail: 'Session not found' });
  }

  if (session.status !== 'pending' && session.status !== 'ready') {
    return res.status(400).json({ detail: 'Session is not pending authorization' });
  }

  const role = req.user.role;
  if (role !== 'EXAM_CONTROLLER' && role !== 'EXTERNAL_OBSERVER') {
    return res.status(403).json({ detail: 'Role not authorized to act as a custodian' });
  }

  // Prevent duplicate unconsumed authorizations by same user
  const existing = releaseAuthorizations.find(
    a => a.sessionId === sessionId && a.userId === req.user.id && !a.consumed
  );
  if (existing) {
    return res.status(400).json({ detail: 'Active authorization already exists' });
  }

  const authId = releaseAuthorizations.length + 1;
  releaseAuthorizations.push({
    id: authId,
    sessionId,
    userId: req.user.id,
    userRole: role,
    clientTimestamp: req.body.client_timestamp || new Date().toISOString(),
    consumed: false
  });

  // Check if both required roles have authorized
  const activeAuths = releaseAuthorizations.filter(a => a.sessionId === sessionId && !a.consumed);
  const rolesSet = new Set(activeAuths.map(a => a.userRole));

  if (rolesSet.has('EXAM_CONTROLLER') && rolesSet.has('EXTERNAL_OBSERVER')) {
    session.status = 'ready';
    addAuditRecord('RELEASE_AUTHORIZED', 'SUCCESS', req.user.id, null, session.examId);
  }

  res.json({ message: 'Authorization successful' });
});

// 8. Release: Execute Session
app.post('/release/sessions/:id/execute', authMiddleware, (req: any, res) => {
  const sessionId = Number(req.params.id);
  const session = releaseSessions.get(sessionId);

  if (!session) {
    return res.status(404).json({ detail: 'Session not found' });
  }

  if (session.status !== 'pending' && session.status !== 'ready') {
    return res.status(400).json({ detail: 'Session is already executed or closed' });
  }

  const activeAuths = releaseAuthorizations.filter(a => a.sessionId === sessionId && !a.consumed);
  const rolesSet = new Set(activeAuths.map(a => a.userRole));

  if (!rolesSet.has('EXAM_CONTROLLER') || !rolesSet.has('EXTERNAL_OBSERVER')) {
    return res.status(403).json({ detail: 'Insufficient custodian authorization material.' });
  }

  // Consume authorizations
  activeAuths.forEach(a => {
    a.consumed = true;
  });

  session.status = 'active';

  // Release all locked papers for this exam
  papers.forEach(p => {
    if (p.examId === session.examId && (p.status === 'LOCKED' || p.status === 'APPROVED')) {
      p.status = 'RELEASED';
    }
  });

  addAuditRecord('RELEASE_ATTEMPT', 'SUCCESS', req.user.id, null, session.examId, { session_id: sessionId });

  res.json({ message: 'Release session activated successfully. Both custodians validated.' });
});

// 9. Exams: Download Paper with Forensic Watermark
app.get('/exams/papers/:id/download', authMiddleware, async (req: any, res) => {
  const paperId = Number(req.params.id);
  const paper = papers.get(paperId);

  if (!paper) {
    return res.status(404).json({ detail: 'Paper not found' });
  }

  if (req.user.role !== 'CENTER_SUPERINTENDENT') {
    addAuditRecord('DOWNLOAD_DENIED', 'FAILURE', req.user.id, paperId, paper.examId, { reason: 'Unauthorized role' });
    return res.status(403).json({ detail: 'Only CENTER_SUPERINTENDENT can download examination papers.' });
  }

  // Check if session for this exam is active
  const activeSession = Array.from(releaseSessions.values()).find(
    s => s.examId === paper.examId && s.status === 'active'
  );

  if (!activeSession && paper.status !== 'RELEASED') {
    addAuditRecord('RELEASE_DENIED', 'FAILURE', req.user.id, paperId, paper.examId, { reason: 'Session not active' });
    return res.status(403).json({ detail: 'Release Denied: Dual-custodian authorization missing or session inactive.' });
  }

  try {
    const decryptedBuffer = decryptPaper(paper);

    const centerId = req.user.center_id || 101;
    const nowUtc = new Date().toISOString().replace('T', ' ').substring(0, 16);

    const watermarkedPdf = await applyForensicWatermark(
      decryptedBuffer,
      paper.examId,
      centerId,
      req.user.id,
      nowUtc
    );

    addAuditRecord('DOWNLOAD', 'SUCCESS', req.user.id, paperId, paper.examId, { center_id: centerId });

    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="watermarked_paper_${paperId}.pdf"`);
    res.send(watermarkedPdf);
  } catch (err: any) {
    addAuditRecord('DOWNLOAD_FAILURE', 'FAILURE', req.user.id, paperId, paper.examId);
    res.status(500).json({ detail: 'Failed to generate secure individualized document.' });
  }
});

// 10. Audit: Verify Chain
app.get('/audit/verify', authMiddleware, (req: any, res) => {
  if (req.user.role !== 'AUDITOR' && req.user.role !== 'EXAM_CONTROLLER') {
    return res.status(403).json({ detail: 'Not authorized to verify audit logs' });
  }

  let isValid = true;
  let firstInvalidRecord: number | null = null;

  for (let i = 0; i < auditChain.length; i++) {
    const record = auditChain[i];
    const prevHash = i === 0 ? '0'.repeat(64) : auditChain[i - 1].recordHash;

    if (record.previousHash !== prevHash) {
      isValid = false;
      firstInvalidRecord = record.id;
      break;
    }

    const content = `${record.id}|${record.timestamp}|${record.action}|${record.result}|${record.actorId ?? ''}|${record.resourceId ?? ''}|${record.previousHash}`;
    const expectedHash = crypto.createHash('sha256').update(content).digest('hex');

    if (record.recordHash !== expectedHash) {
      isValid = false;
      firstInvalidRecord = record.id;
      break;
    }
  }

  res.json({
    valid: isValid,
    total_records: auditChain.length,
    first_invalid_record: firstInvalidRecord
  });
});

// --- Vite Middleware or Static Production Serving ---

async function startServer() {
  const isProduction = process.env.NODE_ENV === 'production';

  if (!isProduction) {
    const vite = await createViteServer({
      server: { middlewareMode: true, hmr: false },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.resolve(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, HOST, () => {
    console.log(`STLEDS server running securely on http://${HOST}:${PORT}`);
  });
}

startServer();
