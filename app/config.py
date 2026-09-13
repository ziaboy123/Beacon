from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BEACON_", extra="ignore")

    rcon_host: str = "127.0.0.1"
    rcon_port: int = 25575
    rcon_password: str = ""

    mc_server_dir: str = "/opt/minecraft"
    systemd_unit: str = "mc-ultimaterealm.service"

    host: str = "127.0.0.1"
    port: int = 8090


settings = Settings()
