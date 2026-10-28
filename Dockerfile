FROM python:3.12-slim-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential autoconf automake libtool pkg-config intltool libglib2.0-dev libpng-dev && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch 0.31.10 https://github.com/autotrace/autotrace.git /src/autotrace && cd /src/autotrace && ./autogen.sh && ./configure --prefix=/usr/local --without-magick --without-pstoedit && make -j2 && make install
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libpng16-16 && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/autotrace /usr/local/bin/autotrace
COPY --from=build /usr/local/lib/ /usr/local/lib/
RUN ldconfig
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=10000
CMD ["sh","-c","gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 120 app:app"]
