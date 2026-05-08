# common base
FROM python:3.12-alpine3.21 AS base

LABEL maintainer="Alan Hsieh"

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# development stage: --target development
FROM base AS development

# use docker build --build-arg USER_NAME=user_name --build-arg USER_UID=uid --target development -t tag .
ARG USER_NAME=root
ARG USER_UID=0

# create the user for the alpine based OS
RUN addgroup -g ${USER_UID} -S ${USER_NAME} \
    && adduser -u ${USER_UID} -s /bin/sh -S -D -G ${USER_NAME} ${USER_NAME}

# follow https://deepsource.com/directory/docker/issues/DOK-DL3019
RUN apk --no-cache add git sqlite-dev nodejs npm

# RUN pip install --upgrade pip

# install codex
RUN npm i -g @openai/codex

WORKDIR /app

# install required python packages
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
#COPY requirements.txt .
#RUN pip install --no-cache-dir --user -r requirements.txt

USER ${USER_NAME}

# production stage: --target production
FROM base AS production

# use docker build --build-arg USER_NAME=user_name --build-arg USER_UID=uid --target production -t tag .
ARG USER_NAME=root
ARG USER_UID=0

# create the user for the alpine based OS
RUN addgroup -g ${USER_UID} -S ${USER_NAME} \
    && adduser -u ${USER_UID} -s /bin/sh -S -D -G ${USER_NAME} ${USER_NAME}

WORKDIR /app

# Allow statements and log messages to immediately appear in the logs
ENV PYTHONUNBUFFERED=1

# install required python packages
COPY pyproject.toml uv.lock src/ /app/
RUN uv sync --frozen --no-install-project --no-dev

USER ${USER_NAME}

# run the server
CMD ["uv", "run", "python", "-m", "yfinance_watchlist.mcp_server", "--host", "127.0.0.1", "--port", "8000", "--path", "/mcp/"]