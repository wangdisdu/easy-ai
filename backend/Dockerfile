FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

# Use Alibaba Cloud Debian mirror (bookworm-slim uses DEB822 sources)
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv from PyPI mirror (avoids astral.sh → GitHub releases)
RUN pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple uv

WORKDIR /srv/easy-ai-backend

# Install deps first (better layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App source + alembic
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

# 上传/日志等运行时数据(数据库改用 postgres,这个目录只存未来的上传/附件等)
RUN mkdir -p /srv/easy-ai-backend/data
VOLUME ["/srv/easy-ai-backend/data"]

ENV PATH="/srv/easy-ai-backend/.venv/bin:${PATH}"
EXPOSE 8000

# 启动时先跑迁移,再起 uvicorn。alembic env.py 从 settings 读 DATABASE_URL。
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
