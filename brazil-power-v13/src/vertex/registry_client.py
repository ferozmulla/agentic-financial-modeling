"""Vertex AI Model Registry client (us-central1) and Gemini LLM multi-region ('us') helper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.config import Settings, get_settings


@dataclass(frozen=True)
class VertexEndpointConfig:
    """Configuration for Vertex AI Prediction in us-central1 and Gemini LLMs in 'us' multi-region."""

    project_id: str
    service_region: str  # us-central1 for Cloud Run, AlloyDB, Vertex Custom Prediction
    gemini_location: str  # 'us' multi-region for Gemini LLMs
    model_name: str
    endpoint_id: str

    @property
    def custom_prediction_api_endpoint(self) -> str:
        return f"{self.service_region}-aiplatform.googleapis.com"

    @property
    def gemini_api_endpoint(self) -> str:
        # Gemini models serve from the US multi-region endpoint ('us') rather than regional endpoints
        return (
            "aiplatform.googleapis.com"
            if self.gemini_location == "global"
            else f"{self.gemini_location}-aiplatform.googleapis.com"
        )


def get_vertex_endpoint_config(settings: Settings | None = None) -> VertexEndpointConfig:
    """Build VertexEndpointConfig enforcing us-central1 for services and 'us' for Gemini LLMs."""
    cfg = settings or get_settings()
    return VertexEndpointConfig(
        project_id=cfg.gcp_project_id,
        service_region=cfg.gcp_region,
        gemini_location=cfg.gemini_location,
        model_name=cfg.vertex_model_name,
        endpoint_id=cfg.vertex_endpoint_id,
    )


def build_model_registry_metadata(settings: Settings | None = None) -> dict[str, Any]:
    """Generate Vertex AI Model Registry metadata payload with universal labels."""
    cfg = settings or get_settings()
    vcfg = get_vertex_endpoint_config(cfg)
    return {
        "display_name": vcfg.model_name,
        "project": vcfg.project_id,
        "region": vcfg.service_region,
        "gemini_location": vcfg.gemini_location,
        "gemini_api_endpoint": vcfg.gemini_api_endpoint,
        "labels": {
            "app": cfg.app_label,
            "project": "enterprise-commodity-modernization",
            "env": "mvp",
            "managed-by": "terraform",
        },
        "container_spec": {
            "health_route": "/health",
            "predict_route": "/predict",
            "port": 8080,
        },
    }
