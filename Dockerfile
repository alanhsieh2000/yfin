FROM python:3.12-alpine3.21

LABEL maintainer="Alan Hsieh"

# use docker build --build-arg USER_NAME=user_name --build-arg USER_UID=uid -t tag .
ARG USER_NAME=root
ARG USER_UID=0

# follow https://deepsource.com/directory/docker/issues/DOK-DL3019
RUN apk --no-cache add git sqlite-dev nodejs npm

RUN pip install --upgrade pip

# install codex
RUN npm i -g @openai/codex

# create the user for the alpine based OS
RUN addgroup -g ${USER_UID} -S ${USER_NAME} \
    && adduser -u ${USER_UID} -s /bin/sh -S -D -G ${USER_NAME} ${USER_NAME}
USER ${USER_NAME}

# install required python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt