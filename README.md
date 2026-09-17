# STLEDS: Secure Examination Delivery System

**STLEDS (Secure Examination Question-Paper Management / Secure Examination Delivery System)** is a comprehensive, enterprise-grade platform designed to cryptographically secure the entire lifecycle of high-stakes examination papers. 

From the moment a Question Setter uploads a draft to the final secure delivery at an Examination Center, STLEDS ensures that digital examination assets remain strictly confidential, tamper-evident, and accessible only under authorized, time-bound conditions. 

STLEDS mitigates insider threats and external breaches by enforcing a strict **Dual-Custodian Release Workflow**, Role-Based Access Control (RBAC), and Authenticated Encryption (AES-256-GCM) with centralized Key Management (KMS).

---

## 🎯 Key Features

- **Strict Role-Based Access Control (RBAC):** Distinct cryptographic boundaries and UI experiences for Setters, Reviewers, Controllers, Observers, Superintendents, and Auditors.
- **Authenticated Encryption (AES-256-GCM):** Papers are immediately encrypted client-side/server-side using 256-bit symmetric keys. Ciphertexts are protected against both decryption and tampering.
- **KMS-Protected Key Shards:** Data Encryption Keys (DEKs) are split into dual shares. Each share is independently wrapped by an AWS KMS Master Key, ensuring that database compromise alone yields no plaintext.
- **Dual-Custodian Release Protocol:** Examination release requires cryptographic authorization from two independent parties (Exam Controller and External Observer). A single rogue actor cannot release a paper.
- **Time-Bounded Release Windows:** Papers are mathematically locked until the precise examination time window opens.
- **Forensic Watermarking:** Upon authorized download, a unique forensic watermark (Center ID, timestamp, transaction ID) is irreversibly embedded into the PDF to trace offline leaks.
- **Immutable Audit Chain:** Every sensitive action (upload, approval, authorization, download) is cryptographically chained using SHA-256 hashing. The Auditor role can instantly verify the integrity of the entire event timeline.
- **Zero-Trust Storage:** All uploaded documents are stored in private Cloudflare R2 (mocked via local storage for sandboxing) strictly as AES-GCM ciphertexts.

---

## 🛠️ Technologies Used

| Technology | Purpose |
|------------|---------|
| **FastAPI (Python)** | High-performance, asynchronous REST API backend. |
| **React + Vite (TypeScript)** | Modern, blazing-fast frontend framework for a responsive SPA. |
| **SQLite** | Relational database mapping for RBAC, state-machine tracking, and audit logs. |
| **AWS KMS (boto3 / moto)** | Hardware Security Module simulation for wrapping/unwrapping key shares. |
| **Cryptography Library** | Implementation of AES-256-GCM for authenticated document encryption. |
| **PyOTP & PyJWT** | Implementation of Time-based One-Time Passwords (MFA) and JSON Web Tokens. |
| **PyPDF2** | Python library for dynamic injection of forensic watermarks into PDFs. |
| **Lucide React** | Professional vector icons for the enterprise UI. |

---

## 📦 Installation & Setup

STLEDS is designed to run locally using simulated cloud environments (`moto_server`). **No external AWS or Cloudflare credentials are required.**

### Prerequisites
- **Python 3.10+**
- **Node.js 18+ & npm**

### 1. Backend Setup
Open a terminal in the project root:
```bash
# Enter the backend directory (or root) and activate the virtual environment
source backend/venv/bin/activate

# Install requirements (if not already installed)
pip install -r backend/requirements.txt
```

### 2. Frontend Setup
Open a separate terminal in the `frontend/` directory:
```bash
cd frontend
npm install
```

---

## 🚀 How to Run the Project

You must start three services in **three separate terminal windows** to run the complete system.

### Terminal 1: Start Mock AWS KMS Server
This spins up the localized AWS mocking server for KMS encryption operations.
```bash
source backend/venv/bin/activate
moto_server -p 5000
```

### Terminal 2: Initialize Keys & Start Backend
This script initializes the Master KMS keys in the Moto server, synchronizes the database, and boots FastAPI.
```bash
source backend/venv/bin/activate
# Synchronize mock KMS keys and repair pre-seeded data
python setup_moto.py

# Start the FastAPI backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Terminal 3: Start the Frontend UI
```bash
cd frontend
npm run dev
```

The STLEDS dashboard will be instantly available at **http://localhost:5173**.

---

## 📁 Project Structure

```text
project_root/
├── backend/
│   ├── audit/            # Cryptographic audit chain logging and verification logic
│   ├── auth/             # JWT issuance, RBAC, and TOTP MFA verification
│   ├── crypto/           # AES-256-GCM, Secret Splitting, KMS interaction, Watermarking
│   ├── exams/            # Core CRUD operations and atomic paper download/release endpoints
│   ├── release/          # Time-based state machine and dual-custodian authorization logic
│   ├── storage/          # Local R2 bucket simulation for ciphertext storage
│   ├── database.py       # SQLite connection and session management
│   └── main.py           # FastAPI application entry point, CORS config, rate limiting
├── frontend/
│   ├── src/
│   │   ├── App.tsx       # Core React application, routing, and UI components
│   │   ├── App.css       # Premium enterprise design system & styling
│   │   └── main.tsx      # React DOM attachment
│   └── package.json      # Frontend dependencies and Vite configuration
├── tests/                # Exhaustive pytest suite covering E2E, Auth, Crypto, and Workflows
├── setup_moto.py         # Automates KMS master key generation and database sync
└── sample_paper.pdf      # Default test asset for upload and watermarking
```

---

## 🔒 Security Architecture

### Authentication & MFA
STLEDS strictly enforces Role-Based Access Control using signed JWTs. High-privilege roles (Exam Controller and Auditor) are enforced by multi-factor authentication (MFA) via Time-Based One Time Passwords (TOTP). 

### Storage Encryption (AES-256-GCM)
Documents are NEVER stored in plaintext. They are encrypted using a randomly generated 256-bit Data Encryption Key (DEK). AES-GCM appends a 16-byte authentication tag to the ciphertext. Any unauthorized modification to the file on disk instantly raises an `InvalidTag` exception upon decryption, preventing tampering.

### Dual-Custodian Authorization
The DEK is split into two cryptographic shares. `Share A` requires the Exam Controller's authorization token; `Share B` requires the External Observer's token. Both shares are wrapped by the AWS KMS Master Key. The ciphertext can only be reconstructed when both distinct human actors cryptographically authorize the active release session.

### Immutable Audit Trail
Every system action is written to the `audit_logs` table. Each record's `hash_signature` incorporates the `previous_hash`, forming a continuous blockchain-like chain. The Auditor interface actively re-computes this chain from Genesis to HEAD, detecting any database tampering.

---

## 🧪 Testing

STLEDS features a rigorous, automated Pytest suite that validates cryptographic boundaries, time-window locks, and role access.

To run the complete test suite:
```bash
source backend/venv/bin/activate
pytest tests/ -v
```

**Key Tests Included:**
- `test_encryption.py`: Validates AES-GCM ciphertext integrity and KMS key splitting.
- `test_dual_custodian.py`: Ensures a single Controller cannot force a release without the Observer.
- `test_time_based_release.py`: Simulates temporal attacks to ensure locked papers cannot be fetched early.
- `test_audit_chain.py`: Mutates database records to ensure the blockchain hash verifier catches tampering.

---

## 👥 User Roles & Workflow

### 1. Question Setter (`setter@test.com`)
**Capabilities:** Can upload new draft question papers securely into the system.
**Limitations:** Cannot approve, authorize, or download final papers.

### 2. Reviewer (`reviewer@test.com`)
**Capabilities:** Has temporary access to read the draft paper in a secure in-app viewer and formally mark it as `APPROVED`.
**Limitations:** Expressly prevented from downloading the raw, un-watermarked PDF.

### 3. Exam Controller (`c@test.com` - Requires MFA)
**Capabilities:** Creates the mathematical Release Session, locks the paper state, and executes the final release payload. Provides the first cryptographic authorization signature (`Share A`).

### 4. External Observer (`o@test.com`)
**Capabilities:** Acts as the independent verifying party. Provides the second cryptographic authorization signature (`Share B`) to complete the dual-custody requirement.

### 5. Center Superintendent (`center@test.com`)
**Capabilities:** Once the release window is open and fully authorized, the Superintendent can securely download the decrypted paper. The system injects a unique, forensic watermark into the PDF prior to delivery.

### 6. Auditor (`auditor@test.com` - Requires MFA)
**Capabilities:** Independent oversight. Can instantly verify the integrity of the cryptographic audit chain to ensure no malicious database manipulation has occurred.

---

## 🎮 How to Demonstrate (The Happy Path)

To experience the complete lifecycle of a secure paper:

1. **Pre-Requisite (MFA):** Run `python -c "import pyotp; print(pyotp.TOTP('base32secret3232').now())"` to generate a 6-digit TOTP code when logging in as the Controller or Auditor. All user passwords are `pass`.
2. **Review & Approve:** Log in as **Reviewer** (`reviewer@test.com`). View the pre-seeded Paper `20` and click **Approve Paper**. Logout.
3. **Initiate Release:** Log in as **Controller** (`c@test.com`). Lock Paper `20`. Create a Release Session. Click **Authorize Session**. Logout.
4. **Co-Authorize:** Log in as **Observer** (`o@test.com`). Click **Co-Authorize Release Session**. Logout.
5. **Execute Release:** Log in as **Controller** (`c@test.com`). Click **Execute Release**. Logout.
6. **Secure Delivery:** Log in as **Center Superintendent** (`center@test.com`). Click **Download Watermarked Paper**. A dynamically watermarked PDF will be downloaded to your machine.
7. **Verify Integrity:** Log in as **Auditor** (`auditor@test.com`). Click **Verify Audit Chain**. The system will mathematically prove that the entire chain of custody is untampered.

---

## 🚧 Limitations & Future Improvements

**Current Limitations:**
- Mock KMS: The system uses a local `moto_server` to simulate AWS KMS.
- Local Storage: R2 object storage is simulated via local disk I/O in the `storage/` directory.

**Future Improvements:**
- Full Cloud Deployment: Seamlessly swap the mock endpoints for actual AWS KMS ARNs and Cloudflare R2 bucket credentials.
- Dynamic MFA Enrollment: Allow users to scan QR codes for TOTP enrollment rather than relying on a seeded secret.

---
**Project Status:** Active / Production-Ready Security Prototype
