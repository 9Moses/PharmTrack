from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "production"
    log_level: str = "info"
    service_name: str = "PharmTrack Email Service"
    service_version: str = "1.0.0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_ssl: bool = True
    default_from_email: str = ""
    default_from_name: str = "PharmTrack"
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

settings = Settings()
