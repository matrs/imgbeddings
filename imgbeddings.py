import logging
import torch
from dataclasses import dataclass, field

from transformers import CLIPProcessor, CLIPVisionModel
from .utils import square_pad

logger = logging.getLogger("imgbeddings")
logger.setLevel(logging.INFO)


@dataclass
class imgbeddings:
    patch_size: int = 32
    model: CLIPVisionModel = field(init=False)
    processor: CLIPProcessor = field(init=False)

    r_brightness: float = 0.2
    r_contrast: float = 0.2
    r_saturation: float = 0.2
    r_hue: float = 0.01
    r_degrees: int = 15
    r_scale: float = 0.10

    def __post_init__(self):
        patch_values = [14, 16, 32]
        assert self.patch_size in patch_values, f"patch_size must be in {patch_values}."

        self.model = CLIPVisionModel.from_pretrained(
            f"openai/clip-vit-base-patch{self.patch_size}"
        )
        self.processor = CLIPProcessor.from_pretrained(
            f"openai/clip-vit-base-patch{self.patch_size}"
        )
        # for embeddings consistancy, do not center crop
        self.processor.feature_extractor.do_center_crop = False

        self.model.eval()

    def create_embeddings(self, inputs, num_layers=3):
        if not isinstance(inputs, list):
            inputs = [inputs]

        inputs = [square_pad(x) for x in inputs]

        image_inputs = self.processor(images=inputs, return_tensors="pt")

        with torch.no_grad():
            outputs = self.model(
                **image_inputs, output_attentions=True, output_hidden_states=True
            )

        hidden_states = torch.sum(
            torch.stack([outputs.hidden_states[i] for i in range(-num_layers, 0)]), 0
        )

        attentions = torch.stack([outputs.attentions[i] for i in range(-num_layers, 0)])
        # switch dimensions so batch dimension is first
        attentions = torch.transpose(attentions, 1, 0)

        attentions_reduced = torch.mean(attentions, (1, 2, 3))
        attentions_reweighted = attentions_reduced

        # the first value corresponds to the class token which is irrelevant
        attentions_reweighted[:, 0] = 0.0
        attentions_reweighted = attentions_reweighted / torch.sum(
            attentions_reweighted, 1
        )

        embeddings = hidden_states * attentions_reweighted.unsqueeze(2)
        return embeddings.sum(1)
