# Chatbot PF. Shoes — dùng cho Hugging Face Spaces (Docker) hoặc bất kỳ nền tảng chạy container nào.
# Khi deploy, AI chạy qua Gemini API (LLM_PROVIDER=gemini), không cần Ollama trong container.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    CHATBOT_HOST=0.0.0.0 \
    CHATBOT_PORT=7860 \
    LLM_PROVIDER=gemini

# Hugging Face Spaces chạy container bằng user uid 1000
RUN useradd -m -u 1000 app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app app.py ./
COPY --chown=app:app pf_bot ./pf_bot
COPY --chown=app:app Data_policy ./Data_policy
RUN mkdir -p .cache && chown app:app .cache

USER app
EXPOSE 7860
CMD ["python", "app.py"]
