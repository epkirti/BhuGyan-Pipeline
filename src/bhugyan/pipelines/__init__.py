"""The five extraction pipelines. Each subclasses Pipeline and reports its
steps through a PipelineRun so progress is visible live."""
from .base import Pipeline
from .p1_places import PlacesPipeline
from .p2_content import ContentPipeline
from .p3_questions import QuestionsPipeline
from .p4_current_affairs import CurrentAffairsPipeline
from .p5_media import MediaPipeline

REGISTRY: dict[str, type[Pipeline]] = {
    "p1": PlacesPipeline,
    "p2": ContentPipeline,
    "p3": QuestionsPipeline,
    "p4": CurrentAffairsPipeline,
    "p5": MediaPipeline,
}

__all__ = ["Pipeline", "REGISTRY"]
