FROM alpine:3.23 AS whisper
RUN apk add --no-cache git cmake g++ make curl
RUN git clone https://github.com/ggml-org/whisper.cpp.git /src \
    && git -C /src checkout 48f628a84833905ee4a0658ee6d4a5c915ce1997 \
    && cmake -S /src -B /build -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DWHISPER_BUILD_TESTS=OFF \
    && cmake --build /build --target whisper-cli -j 2 \
    && sh /src/models/download-ggml-model.sh base \
    && echo '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe  /src/models/ggml-base.bin' | sha256sum -c -

FROM python:3.12-alpine3.23
RUN apk add --no-cache ffmpeg libstdc++
COPY --from=whisper /build/bin/whisper-cli /usr/local/bin/whisper-cli
COPY --from=whisper /src/models/ggml-base.bin /opt/media-eyes/ggml-base.bin
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src src
RUN pip install --no-cache-dir . \
    && adduser -D -u 10001 media
USER media
ENV MEDIA_EYES_WHISPER_CPP_MODEL=/opt/media-eyes/ggml-base.bin
ENTRYPOINT ["media-eyes"]
