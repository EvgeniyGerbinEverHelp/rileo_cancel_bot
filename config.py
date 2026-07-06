from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Zendesk ---
    ZD_SUBDOMAIN: str
    ZD_EMAIL: str
    ZD_TOKEN: str

    # --- Zendesk: ID кастомных полей ---
    FIELD_REQUEST_TYPE: int
    FIELD_PRODUCT: int

    # --- Zendesk: значения опций и маршрутизация ---
    REQUEST_TYPE_VALUE: str = ""
    PRODUCT_VALUE: str = ""
    GROUP_ID: str = ""

    # ID агента-бота в Zendesk. Если задан — бот ассайнит тикет на этого агента
    # и публикует комментарии от его имени (author_id). Пусто (0) -> старое
    # поведение: ассайн через ZD_EMAIL, автор комментария = владелец токена.
    BOT_AGENT_ID: int = 0

    # ID бренда Zendesk (нативное поле ticket.brand_id). Если задан — бот
    # проставляет бренд тикету при завершении/эскалации. На ruutsupport заменяет
    # отсутствующее поле Product. Пусто (0) -> бренд не трогаем.
    BRAND_ID: int = 0

    # --- Solidgate ---
    SOLIDGATE_PUBLIC_KEY: str = ""
    SOLIDGATE_SECRET_KEY: str = ""
    # Код причины отмены (опционально, см. docs.solidgate.com subscription-cancel-codes)
    CANCEL_CODE: str = "8.06"

    # --- BigQuery ---
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    BQ_PROJECT: str
    BQ_TABLE: str

    # --- Данные: ключевые слова и макросы ---
    KEYWORDS_FILE: str = "rileo_data_enrichment.xlsx"
    KEYWORDS_SHEET_NAME: str = "Keywords"
    MACROS_SHEET_NAME: str = "Macros"

    # --- Режим ---
    # True  = co-pilot (Этап 1): только internal note, без ответа клиенту и без отмены.
    # False = полный режим (Этап 2).
    CO_PILOT_MODE: bool = True

    # --- Сервер ---
    PORT: int = 8080

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
