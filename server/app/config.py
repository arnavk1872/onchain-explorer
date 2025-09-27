from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # Database Configuration (Neon PostgreSQL)
    db_connection_string: str = "postgresql://username:password@ep-xxx-xxx-xxx.region.aws.neon.tech/database_name?sslmode=require"
    
    # OpenAI Configuration
    openai_api_key: str = ""
    
    # Cohere Configuration
    cohere_api_key: str = ""
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # LangGraph Configuration
    langgraph_debug: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
