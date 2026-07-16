FROM python:3.12-slim

WORKDIR /app

# Copy and install python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt


# Copy application source code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Expose port
EXPOSE 8000

# Run Uvicorn app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
