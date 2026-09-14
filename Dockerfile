FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
WORKDIR /app
COPY deploy/public-runtime.lock ./public-runtime.lock
RUN python -m pip install --no-cache-dir -r public-runtime.lock
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation .
RUN useradd --create-home --uid 10001 weather && mkdir -p /app/data && chown -R weather:weather /app
USER weather
EXPOSE 8000
CMD ["uvicorn", "rozkalns_weather.app:app", "--host", "0.0.0.0", "--port", "8000"]
