"""Central configuration loaded from environment / .env file."""

from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AGRI_SENSE_",
        extra="ignore",
    )

    # Root data directory (relative to project root or absolute)
    data_dir: Path = Field(default=Path("data"), alias="AGRI_SENSE_DATA_DIR")

    # NASA POWER
    nasa_power_base_url: str = Field(
        default="https://power.larc.nasa.gov/api/temporal/daily/point",
        alias="NASA_POWER_BASE_URL",
    )

    # SoilGrids 2.0
    soilgrids_base_url: str = Field(
        default="https://rest.isric.org/soilgrids/v2.0",
        alias="SOILGRIDS_BASE_URL",
    )

    # Microsoft Planetary Computer (empty string = anonymous)
    pc_sdk_subscription_key: str = Field(default="", alias="PC_SDK_SUBSCRIPTION_KEY")

    # GSO yield data (optional for MVP)
    gso_api_key: str = Field(default="", alias="GSO_API_KEY")

    # Temperature scaling for classifier probabilities (T>1 softens distribution)
    classifier_temperature: float = Field(default=2.0, alias="AGRI_SENSE_CLASSIFIER_TEMPERATURE")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def interim_dir(self) -> Path:
        return self.data_dir / "interim"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"


# Module-level singleton — import this everywhere
config = Config()
