FROM python:3.11-slim@sha256:673719e071ecf27434fd2635bbd8d00f49f4fdd81f243143438a42ced8bedf60
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DBT_SEND_ANONYMOUS_USAGE_STATS=false
ENTRYPOINT ["python", "-m", "src.run_pipeline"]
