#!/bin/bash
set -e

fuser -k 8000/tcp || true
fuser -k 5173/tcp || true
fuser -k 5000/tcp || true

echo "Starting moto_server in background..."
source backend/venv/bin/activate
nohup moto_server -p 5000 > moto.log 2>&1 &
sleep 3
export AWS_ACCESS_KEY_ID=testing
export AWS_SECRET_ACCESS_KEY=testing
export AWS_DEFAULT_REGION=us-east-1
KMS_OUTPUT=$(aws --endpoint-url=http://127.0.0.1:5000 kms create-key --description "stleds-mock-key")
KMS_KEY_ID=$(echo $KMS_OUTPUT | grep -o '"KeyId": "[^"]*' | cut -d'"' -f4)
aws --endpoint-url=http://127.0.0.1:5000 s3 mb s3://stleds-secure-storage || true

cat << ENV_EOF > backend/.env
DATABASE_URL=sqlite:///./stleds.db
R2_ENDPOINT=http://127.0.0.1:5000
R2_ACCESS_KEY_ID=testing
R2_SECRET_ACCESS_KEY=testing
R2_BUCKET_NAME=stleds-secure-storage
AWS_REGION=us-east-1
AWS_KMS_KEY_ID=$KMS_KEY_ID
JWT_SECRET=supersecretjwtkey_for_demo_purposes_only
ENV_EOF

echo "Starting localtunnels..."
nohup npx --yes localtunnel --port 8000 --local-host 127.0.0.1 > backend_url.txt 2>&1 &
nohup npx --yes localtunnel --port 5173 --local-host 127.0.0.1 > frontend_url.txt 2>&1 &

sleep 5

BACKEND_URL=$(cat backend_url.txt | grep -o 'https://[^[:space:]]*')
FRONTEND_URL=$(cat frontend_url.txt | grep -o 'https://[^[:space:]]*')

echo "BACKEND_URL=$BACKEND_URL"
echo "FRONTEND_URL=$FRONTEND_URL"

echo "VITE_API_URL=$BACKEND_URL" > frontend/.env

export PYTHONPATH=$(pwd)
export CORS_ALLOWED_ORIGINS="$FRONTEND_URL"

echo "Starting Backend..."
nohup uvicorn backend.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &

echo "Starting Frontend..."
cd frontend
npm install
nohup npm run dev -- --host 127.0.0.1 --port 5173 > ../frontend.log 2>&1 &

echo "Deployment successful."
