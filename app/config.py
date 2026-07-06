from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""

    feishu_bitable_app_token: str = ""
    feishu_table_raw_inputs: str = ""
    feishu_table_task_rules: str = ""
    feishu_table_chore_records: str = ""
    feishu_table_reminder_records: str = ""

    member_map_json: str = ""

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"


settings = Settings()
