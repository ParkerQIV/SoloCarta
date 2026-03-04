from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./solocarta.db"
    anthropic_api_key: str = ""
    github_token: str = ""
    workspaces_dir: str = ".workspaces"

    model_config = {"env_prefix": "SOLOCARTA_"}


settings = Settings()
