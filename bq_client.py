import os

from google.cloud import bigquery

from config import settings

_client: bigquery.Client | None = None


def _get_client() -> bigquery.Client:
    """Ленивая инициализация клиента BigQuery.

    Локально — через сервис-ключ из GOOGLE_APPLICATION_CREDENTIALS.
    На GCP (если ключа нет) — через Application Default Credentials.
    """
    global _client
    if _client is None:
        key = settings.GOOGLE_APPLICATION_CREDENTIALS
        if key and os.path.exists(key):
            _client = bigquery.Client.from_service_account_json(
                key, project=settings.BQ_PROJECT
            )
        else:
            _client = bigquery.Client(project=settings.BQ_PROJECT)
    return _client


def get_customer_id_by_email(email: str) -> str | None:
    """Ищет customer_account_id по email. None — не найден либо ошибка запроса."""
    if not email:
        return None
    try:
        query = f"""
            SELECT customer_account_id
            FROM `{settings.BQ_PROJECT}.{settings.BQ_TABLE}`
            WHERE LOWER(customer_email) = LOWER(@email)
              AND customer_account_id IS NOT NULL
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )
        results = _get_client().query(query, job_config=job_config).result()
        for row in results:
            return row.customer_account_id
        return None
    except Exception as e:
        print(f"❌ BigQuery error for '{email}': {e}")
        return None
