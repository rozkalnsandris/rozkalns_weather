FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[weathernext]'
RUN useradd --create-home --uid 10001 weather && mkdir -p /app/data && chown -R weather:weather /app
USER weather
EXPOSE 8000
CMD ["uvicorn", "rozkalns_weather.app:app", "--host", "0.0.0.0", "--port", "8000"]
