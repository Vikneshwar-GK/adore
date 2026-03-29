FROM apache/airflow:2.8.1-python3.11

COPY requirements.txt /requirements.txt

# Install additional dependencies only — Airflow is already in the base image
RUN pip install --no-cache-dir \
    google-cloud-bigquery==3.25.0 \
    google-cloud-storage==2.18.0 \
    requests==2.31.0 \
    protobuf==4.25.3 \
    dbt-bigquery==1.8.0 \
    anthropic==0.40.0 \
    streamlit==1.38.0