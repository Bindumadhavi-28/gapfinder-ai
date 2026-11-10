FROM python:3.11-slim

# Install system dependencies including Node.js for pdfjs-dist
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node dependencies
COPY package.json ./
RUN npm install --omit=dev

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose Streamlit port
EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
