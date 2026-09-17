# STLEDS: Secure Examination Delivery System

## A. PROJECT TITLE
**STLEDS (Secure Examination Question-Paper Management / Secure Examination Delivery System)**

## B. BRIEF PROJECT DESCRIPTION
STLEDS is a highly secure, cryptographic platform designed to manage the lifecycle of high-stakes examination papers. It solves the critical problem of examination paper leaks by ensuring that from the moment a paper is uploaded by a Question Setter to the moment it is downloaded at an examination center, the digital asset remains strictly confidential, tamper-proof, and completely inaccessible to unauthorized parties. The main objective is to provide absolute cryptographic certainty that an exam cannot be leaked prematurely, even if the database or storage servers are fully compromised.

## C. PROBLEM STATEMENT
**The Problem:** Traditional digital examination distribution systems suffer from single points of failure. If a database administrator goes rogue, or if a hacker compromises the backend server, they can simply download and read the stored question papers. 
**The Risk:** Premature leaks of high-stakes exams (like university finals or national entrance exams) destroy institutional credibility and require massive financial costs to reschedule. 
**The Challenge:** We need a system where *no single person*—not even the system administrator—has the technical ability to read the paper before the exam begins.

## D. SOLUTION OVERVIEW
STLEDS solves this by never storing papers in readable text. When a paper is uploaded, it is instantly locked in an unbreakable cryptographic vault (AES-256-GCM). The "key" to this vault is then split into multiple pieces and hidden behind an AWS Key Management Service (KMS). To open the vault, the system requires two completely independent senior officials (the Exam Controller and an External Observer) to insert their cryptographic "signatures" at the exact same time, and only during a strictly enforced time window. Finally, when the paper is downloaded at the exam center, it is permanently watermarked to trace any physical leaks.

## E. KEY FEATURES
- **Authenticated Encryption:** Papers are encrypted using AES-256-GCM. *Why:* Prevents both unauthorized reading and malicious modification of the exam file.
- **Dual-Custodian Authorization:** Release requires two independent actors. *Why:* Eliminates the "rogue insider" threat; no single person can release the exam.
- **Forensic Watermarking:** Injects Center ID and timestamps into the PDF upon delivery. *Why:* If a center prints and leaks the paper physically, the leak can be traced back to the exact center and time.
- **Immutable Audit Chain:** Cryptographically hashes every sensitive action into a blockchain-like log. *Why:* Allows independent auditors to verify that the database timeline was never altered or tampered with.
- **Time-Bounded Locks:** Enforces strict temporal release windows. *Why:* Prevents authorized actors from colluding to release the paper days before the exam.

## F. TECHNOLOGIES / TOOLS USED

| Technology / Tool | Purpose |
|-------------------|---------|
| **FastAPI (Python)** | High-performance, asynchronous REST API backend. |
| **React + Vite (TS)** | Modern, blazing-fast frontend framework for the UI. |
| **SQLite** | Relational database mapping for RBAC, state-machine, and audit logs. |
| **AWS KMS (Moto)** | Hardware Security Module simulation for wrapping/unwrapping key shares. |
| **Cryptography (AES-GCM)** | Implementation of AES-256-GCM for authenticated document encryption. |
| **PyOTP & PyJWT** | Implementation of Time-based One-Time Passwords (MFA) and JSON Web Tokens. |
| **PyPDF2** | Python library for dynamic injection of forensic watermarks into PDFs. |
| **Lucide React** | Professional vector icons for the enterprise UI. |

## G. SYSTEM REQUIREMENTS / PREREQUISITES
To run STLEDS locally, you need the following installed:
- **Operating System:** Linux, macOS, or Windows (WSL recommended)
- **Python:** Version 3.10 or higher
- **Node.js:** Version 18 or higher & **npm**
- **No cloud accounts required:** The AWS KMS and Cloudflare R2 object storage are fully simulated locally for this sandboxed deployment.

## H. INSTALLATION
Follow these steps to set up the project on your local machine.

1. **Clone the repository and enter the directory:**
   Ensure you are in the `stleds` project root folder.
2. **Install backend dependencies:**
   ```bash
   python3 -m venv backend/venv
   source backend/venv/bin/activate
   pip install -r backend/requirements.txt
   ```
   *This creates an isolated Python environment and installs FastAPI, cryptography, and boto3.*
3. **Install frontend dependencies:**
   ```bash
   cd frontend
   npm install
   cd ..
   ```
   *This downloads the React framework and Lucide icons required for the UI.*

*(Note: STLEDS utilizes hardcoded mock configuration in local development, so manual `.env` configuration is bypassed for the demo).*

## I. HOW TO RUN THE PROJECT
The system requires three distinct services running simultaneously. Open three separate terminal windows.

**Terminal 1 (Start Mock AWS KMS):**
```bash
source backend/venv/bin/activate
moto_server -p 5000
```
*This spins up the simulated hardware security module on port 5000.*

**Terminal 2 (Initialize Database & Start Backend):**
```bash
source backend/venv/bin/activate
python setup_moto.py
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
*The `setup_moto.py` script initializes the encryption keys and repairs pre-seeded databases. `uvicorn` boots the API.*

**Terminal 3 (Start Frontend UI):**
```bash
cd frontend
npm run dev
```
*This starts the React development server.*

## J. HOW TO ACCESS THE APPLICATION
With all three terminals running, the application is accessible at:
- **Frontend Dashboard:** `http://localhost:5173`
- **Backend API Server:** `http://localhost:8000`
- **API Documentation (Swagger):** `http://localhost:8000/docs`

## K. PROJECT STRUCTURE

```text
stleds/
├── backend/
│   ├── audit/            # Cryptographic blockchain logging
│   ├── auth/             # JWT, RBAC, and TOTP MFA
│   ├── crypto/           # AES-GCM, Secret Splitting, KMS interaction
│   ├── exams/            # Core CRUD and paper download endpoints
│   ├── release/          # Dual-custodian authorization state machine
│   ├── storage/          # Local R2 bucket simulation for ciphertexts
│   └── main.py           # FastAPI entry point
├── frontend/
│   ├── src/
│   │   ├── App.tsx       # Core React application and routing
│   │   └── App.css       # Enterprise design system
│   └── package.json      # Frontend dependencies
├── tests/                # Exhaustive Pytest suite
└── setup_moto.py         # KMS initialization script
```

| Module/Folder | Purpose |
|---------------|---------|
| `backend/crypto/` | The heart of STLEDS. Handles the mathematical splitting of keys and AES-256-GCM encryption. |
| `backend/release/` | Enforces the strict business logic requiring two humans to authorize an exam. |
| `frontend/src/App.tsx` | The unified dashboard providing distinct, secure UI views for all six user roles. |

## L. USER ROLES

| Role | Responsibility | Allowed Actions | Restricted Actions | Position in Workflow |
|------|----------------|-----------------|--------------------|----------------------|
| **Question Setter** | Authoring exams. | Upload draft papers. | Cannot approve, release, or download finals. | Step 1 (Start) |
| **Reviewer** | Quality assurance. | Read drafts securely in-app; mark as APPROVED. | Cannot download original raw PDFs. | Step 2 |
| **Exam Controller** | Exam administration. | Lock papers; Create release sessions; Authorize Share A; Execute release. | Cannot read paper contents. | Steps 3, 4, & 6 |
| **External Observer** | Independent oversight. | Provide authorization Share B. | Cannot read paper or initiate release. | Step 5 |
| **Superintendent** | Exam center logistics. | Download watermarked paper during the active window. | Cannot download early; Cannot avoid watermarks. | Step 7 |
| **Auditor** | Security compliance. | Verify cryptographic audit chain integrity. | Cannot alter logs or access papers. | Post-Exam / Ongoing |

## M. COMPLETE SYSTEM WORKFLOW

1. **Authentication:** User logs in via email/password. High-privilege users must also provide a 6-digit TOTP MFA code.
2. **Question-Paper Upload:** Question Setter selects a PDF and uploads it to the system.
3. **Encryption & Secure Storage:** The backend instantly generates a 256-bit DEK, encrypts the PDF using AES-GCM, splits the DEK into two shares, wraps the shares using AWS KMS, and saves the ciphertext to storage.
4. **Review & Approval:** The Reviewer views the decrypted paper securely inside the browser memory and clicks "Approve."
5. **Locking & Session Creation:** The Exam Controller locks the paper state (preventing further edits) and generates a cryptographic Release Session tied to the exam schedule.
6. **Controller Authorization:** The Controller cryptographically signs the Release Session, authorizing `Share A` of the key.
7. **External Observer Authorization:** The independent Observer signs the Session, authorizing `Share B`.
8. **Release Execution:** The Controller executes the fully authorized session, transitioning the paper state to `RELEASED`.
9. **Secure Delivery:** During the allowed time window, the Center Superintendent requests the paper.
10. **Watermarking:** The backend dynamically reconstructs the key, decrypts the ciphertext, injects a forensic watermark (Center ID + Timestamp) into the PDF pages, and serves the file.
11. **Audit Logging:** Every single step above is hashed and permanently logged in the audit database.
12. **Audit Verification:** The Auditor recalculates the SHA-256 hashes of the entire database to prove no tampering occurred.

## N. SECURITY MECHANISMS

- **Multi-Factor Authentication (MFA)**
  - *What:* Requires a rotating 6-digit code from an authenticator app.
  - *Why:* Protects high-privilege accounts (Controller/Auditor) from compromised passwords.
  - *How:* Implemented via `PyOTP` validating against a base32 secret in the database.
- **Authenticated Encryption (AES-256-GCM)**
  - *What:* Military-grade symmetric encryption that also validates file integrity.
  - *Why:* Prevents database administrators from reading papers, and detects if the ciphertext was tampered with on disk.
  - *How:* Implemented via Python's `cryptography` library. A 16-byte auth tag is appended and verified on decryption.
- **Dual-Custodian Authorization**
  - *What:* Requires two distinct users to approve an action.
  - *Why:* Ensures a single compromised account cannot leak a paper.
  - *How:* The decryption key is split into `Share A` and `Share B`. The backend only reconstructs the key if the active Release Session possesses cryptographic signatures from both a Controller and an Observer.
- **Forensic Watermarking**
  - *What:* Visibly and invisibly stamping the downloaded PDF with identifying data.
  - *Why:* Deters physical leaks by tracing the source of photographed/printed papers.
  - *How:* `PyPDF2` dynamically draws the Superintendent's ID and current timestamp diagonally across the document memory buffer before HTTP delivery.
- **Tamper-Evident Audit Chain**
  - *What:* A blockchain-style linked list of log entries.
  - *Why:* Detects if a hacker deletes a log entry to cover their tracks.
  - *How:* Each log entry hashes its own data plus the `previous_hash`. The Auditor recalculates the entire chain from genesis; if a hash mismatches, tampering is proven.

## O. SAMPLE INPUT AND OUTPUT

### Sample Input
The Question Setter selects a PDF (e.g., `sample_paper.pdf`) and clicks "Upload". The frontend sends a `multipart/form-data` request with the Bearer JWT token.

### Processing
STLEDS backend intercepts the file:
1. Generates `DEK = os.urandom(32)`
2. Encrypts PDF: `ciphertext, tag = AESGCM(DEK).encrypt(file_bytes)`
3. Splits DEK and requests KMS wrapping.
4. Saves ciphertext to `./backend/storage/local_r2_bucket/`.

### Sample Output
The backend returns a JSON success response:
```json
{
  "message": "Paper uploaded successfully.",
  "paper_id": 21,
  "filename": "sample_paper.pdf"
}
```
The UI updates to display the new Paper ID.

## P. COMPLETE USER / DEMONSTRATION GUIDE

Follow this exact happy-path walkthrough to test the system end-to-end. (Ensure all 3 terminals are running).

1. **Pre-requisite (MFA Generation):** 
   High-privilege accounts require MFA. Open a new terminal and run:
   ```bash
   source backend/venv/bin/activate
   python -c "import pyotp; print(pyotp.TOTP('base32secret3232').now())"
   ```
   *Keep this 6-digit code handy. (Passwords for all users are `pass`).*

2. **Upload (Question Setter):**
   - Log in: `setter@test.com` (Password: `pass`)
   - Click "Choose File", select `sample_paper.pdf` from the project root, and click "Upload". Note the generated Paper ID. Logout.

3. **Review (Reviewer):**
   - Log in: `reviewer@test.com` (Password: `pass`)
   - Enter the Paper ID and click "Approve Paper". Logout.

4. **Lock & Initialize (Exam Controller):**
   - Log in: `c@test.com` (Password: `pass`, MFA: generated code)
   - Enter the Paper ID. Click "Lock Paper".
   - Click "Create Release Session". Note the generated Active Session ID.
   - Click "Authorize Session". Logout.

5. **Co-Authorize (External Observer):**
   - Log in: `o@test.com` (Password: `pass`)
   - The Active Session ID is auto-detected. Click "Co-Authorize Release Session". Logout.

6. **Execute (Exam Controller):**
   - Log in again as `c@test.com` (Generate a new MFA code if the old one expired).
   - Click "Execute Release". The paper is now mathematically unlocked. Logout.

7. **Secure Download (Center Superintendent):**
   - Log in: `center@test.com` (Password: `pass`)
   - Enter the Paper ID and click "Download Watermarked Paper".
   - *Open the downloaded PDF. You will see a forensic watermark across the page!* Logout.

8. **Audit (Auditor):**
   - Log in: `auditor@test.com` (Password: `pass`, MFA: generated code)
   - Click "Verify Audit Chain". The system will return `{"integrity_valid": true}`.

## Q. TESTING
STLEDS includes a robust test suite that verifies cryptographic integrity, dual-custodian bounds, and time-based access control.
- **Framework:** `pytest`
- **Commands:** 
  ```bash
  source backend/venv/bin/activate
  PYTHONPATH=. pytest tests/ -v
  ```
- **What it verifies:** 
  - `test_encryption.py`: Ensures ciphertext modification throws `InvalidTag`.
  - `test_dual_custodian.py`: Ensures Controller alone cannot execute a release.
  - `test_audit_chain.py`: Mutates SQLite directly to ensure the blockchain hash fails.

## R. TROUBLESHOOTING

- **Problem:** Download fails with `{"detail":"Release Denied: Key authorization or secure delivery failed."}` or `500 Internal Server Error`.
  - **Cause:** The mock AWS Moto server was restarted, but the master KMS keys in memory were wiped.
  - **Solution:** Stop the backend, run `python setup_moto.py` to re-seed the keys and repair the database, then restart the backend.
- **Problem:** Controller or Auditor login shows "Login Failed. Check credentials."
  - **Cause:** The TOTP MFA code has expired (they last 30 seconds).
  - **Solution:** Generate a fresh code using `python -c "import pyotp; print(pyotp.TOTP('base32secret3232').now())"` and login immediately.
- **Problem:** Frontend shows `Failed to fetch`.
  - **Cause:** The backend is not running, or is running on the wrong port.
  - **Solution:** Ensure Terminal 2 is running `uvicorn` on exactly port `8000`.

## S. CONFIGURATION
STLEDS is configured for seamless local demonstration.
- **Required:** Python 3.10+, Node 18+.
- **Local/Demo Configuration:** The `setup_moto.py` script automatically configures the local AWS Moto server and injects local environment variables (`AWS_ACCESS_KEY_ID=testing`, etc.) required for the KMS mock.
- **Database:** Defaults to a local `stleds.db` SQLite file.

## T. LIMITATIONS
- **Mock Infrastructure:** Uses `moto_server` instead of a live AWS KMS endpoint, meaning cryptographic keys are lost when the Moto terminal closes.
- **Local Storage:** Cloudflare R2 object storage is simulated via local disk I/O in the `backend/storage/local_r2_bucket/` directory.

## U. FUTURE IMPROVEMENTS
- **Cloud KMS Integration:** Transition from `moto` to live AWS KMS ARNs for persistent key management.
- **Dynamic MFA Enrollment:** Implement QR-code generation for TOTP enrollment so users can use Google Authenticator instead of python CLI scripts.

## V. PROJECT STATUS
**Active / Production-Ready Security Prototype.** The cryptographic core and RBAC boundaries are fully functional and verifiable.
