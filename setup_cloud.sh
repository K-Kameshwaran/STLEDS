#!/bin/bash
set -e

echo "Starting moto_server in background..."
source backend/venv/bin/activate
pip install 'moto[server]' awscli
moto_server -p 5000 > moto.log 2>&1 &
MOTO_PID=$!
sleep 3

export AWS_ACCESS_KEY_ID=testing
export AWS_SECRET_ACCESS_KEY=testing
export AWS_DEFAULT_REGION=us-east-1

echo "Creating mock KMS key..."
KMS_OUTPUT=$(aws --endpoint-url=http://127.0.0.1:5000 kms create-key --description "stleds-mock-key")
KMS_KEY_ID=$(echo $KMS_OUTPUT | grep -o '"KeyId": "[^"]*' | cut -d'"' -f4)

echo "Creating mock S3 bucket..."
aws --endpoint-url=http://127.0.0.1:5000 s3 mb s3://stleds-secure-storage

echo "Creating backend/.env..."
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

echo "Cloud mock setup complete."
cat backend/.env
