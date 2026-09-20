FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies (required for some ML libraries)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create necessary directories for local DB/storage
RUN mkdir -p chroma_db processed raw src templates

# Copy application code
COPY . .

# Create a non-root user (Hugging Face Spaces requirement for security)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Change ownership of working directory to non-root user
WORKDIR $HOME/app
COPY --chown=user . $HOME/app

# Expose Hugging Face default port
EXPOSE 7860

# Run the Flask app
CMD ["python", "app.py"]
