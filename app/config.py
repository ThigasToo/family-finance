from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_user: str
    db_password: str
    db_host: str
    db_port: int = 6543
    db_name: str = "postgres"

    secret_key: str
    access_token_expire_minutes: int = 10080
    pluggy_client_id: str = ""
    pluggy_client_secret: str = ""
    pluggy_webhook_secret: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
