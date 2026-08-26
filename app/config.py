from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 10080  # 7 dias
    pluggy_client_id: str = ""
    pluggy_client_secret: str = ""

    class Config:
        env_file = ".env"

settings = Settings()