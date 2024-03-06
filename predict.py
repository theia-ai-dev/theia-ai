import functools
import inspect
import os
import socket
import time
import zipfile
from typing import Any, Callable, Optional

import torch
from cog import BasePredictor, ConcatenateIterator, Input, Path
import config
from config import ENGINE, ENGINE_KWARGS, USE_SYSTEM_PROMPT
from src.download import Downloader
from src.utils import seed_all, delay_prints

# This prompt formatting was copied from the original Llama v2 repo:
# https://github.com/facebookresearch/llama/blob/6c7fe276574e78057f917549435a2554000a876d/llama/generation.py#L44

# These are components of the prompt that should not be changed by the users
B_INST, E_INST = "[INST]", "[/INST]"
B_SYS, E_SYS = "<<SYS>>\n", "\n<</SYS>>\n\n"
# normally this would start with <s>, but MLC adds it
PROMPT_TEMPLATE = f"{B_INST} {B_SYS}{{system_prompt}}{E_SYS}{{prompt}} {E_INST}"
if not USE_SYSTEM_PROMPT:
    PROMPT_TEMPLATE = "{prompt}"
PROMPT_TEMPLATE = getattr(config, "PROMPT_TEMPLATE", PROMPT_TEMPLATE)

# Users may want to change the system prompt, but we use the recommended system prompt by default
DEFAULT_SYSTEM_PROMPT = """You are a helpful, respectful and honest assistant."""
DEFAULT_SYSTEM_PROMPT = getattr(config, "DEFAULT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)

# Temporary hack to disable Top K from the API. We should get rid of this once engines + configs are better standardized.
USE_TOP_K = ENGINE.__name__ not in ("MLCEngine", "MLCvLLMEngine")


class Predictor(BasePredictor):
    def setup(self, weights: Optional[Path] = None):
        print("Starting setup")
        self.downloader = Downloader()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.engine = ENGINE(**ENGINE_KWARGS)

        if weights is not None and weights.name == "weights":
            # bugfix
            weights = None
        if weights:
            # If weights are passed in, they are LoRa weights
            # so we need to download the fp16 weights and load with peft
            self.initialize_peft(weights)
        else:
            print("Not using old-style COG_WEIGHTS LoRA weights")

    # todo: adaptive cache like CLOCK
    @functools.lru_cache(maxsize=10)
    def get_lora(self, theia_weights: str) -> Any:
        if "http" in str(theia_weights):  # weights are in the cloud
            print("Downloading peft weights")
            st = time.time()
            buffer = self.downloader.sync_download_file(str(theia_weights))
            print(f"Downloaded peft weights in {time.time() - st:.3f}")
        else:
            # zipfile accepts either a file-like or path-like object
            buffer = theia_weights
        st = time.time()
        with zipfile.ZipFile(buffer, "r") as zip_ref:
            data = {name: zip_ref.read(name) for name in zip_ref.namelist()}
        print(f"Unzipped peft weights in {time.time() - st:.3f}")
        st = time.time()
        lora = self.engine.load_lora(data)
        del data, zip_ref
        print(f"Initialized peft model in {time.time() - st:.3f}")
        return lora

    current_path: str | None = None

    def initialize_peft(self, theia_weights: str) -> None:
        if self.current_path != theia_weights:
            print(f"previous weights were different, switching to {theia_weights}")
            self.engine.set_lora(self.get_lora(theia_weights))

            self.current_path = theia_weights
        else:
            print("correct lora is already loaded")

    def delete_lora(self):
        self.current_path = None
        self.engine.delete_lora()

    # currently, outputs including tokens and logs are throttled to 50ms
    # because of this, printing before outputing tokens is bad
    # so this patches print to not only print until after we leave this function
    # eventually that will be fixed and this can be removed
    def predict(
        self,
        prompt: str = Input(description="Prompt to send to the model."),
        system_prompt: str = Input(
            description="System prompt to send to the model. This is prepended to the prompt and helps guide system behavior. Should not be blank.",
            default=DEFAULT_SYSTEM_PROMPT,
        ),
        max_new_tokens: int = Input(
            description="Maximum number of tokens to generate. A word is generally 2-3 tokens",
            ge=1,
            default=128,
        ),
        min_new_tokens: int = Input(
            description="Minimum number of tokens to generate. To disable, set to -1. A word is generally 2-3 tokens.",
            ge=-1,
            default=-1,
        ),
        temperature: float = Input(
            description="Adjusts randomness of outputs, greater than 1 is random and 0 is deterministic, 0.75 is a good starting value.",
            ge=0.01,
            le=5,
            default=0.7,
        ),
        top_p: float = Input(
            description="When decoding text, samples from the top p percentage of most likely tokens; lower to ignore less likely tokens",
            ge=0.0,
            le=1.0,
            default=0.95,
        ),
        top_k: int = Input(
            description="When decoding text, samples from the top k most likely tokens; lower to ignore less likely tokens",
            ge=-1,
            default=-1,
        ),
        repetition_penalty: float = Input(
            description="A parameter that controls how repetitive text can be. Lower means more repetitive, while higher means less repetitive. Set to 1.0 to disable.",
            ge=0.0,
            default=1.15,
        ),
        stop_sequences: str = Input(
            description="A comma-separated list of sequences to stop generation at. For example, '<end>,<stop>' will stop generation at the first instance of 'end' or '<stop>'.",
            default=None,
        ),
        seed: int = Input(
            description="Random seed. Leave blank to randomize the seed",
            default=None,
        ),
        debug: bool = Input(
            description="provide debugging output in logs", default=False
        ),
        prompt_template: str = Input(
            description="Template for formatting the prompt",
            default=PROMPT_TEMPLATE,
        ),
        # return_logits: bool = Input(
        # description="if set, only return logits for the first token. only useful for testing, etc.",
        # default=False,
        # ),
        theia_weights: str = Input(
            description="Path to fine-tuned weights produced by a Theia fine-tune job.",
            default=None,
        ),
    ) -> ConcatenateIterator[str]:
        with delay_prints() as print:
            if stop_sequences:
                stop_sequences = stop_sequences.split(",")
            # we must apply a prompt template if it is passed even for base models
            if prompt_template:
                # very rough hack to catch mistral-instruct / no SYS token
                # this is supposed to not proc for the default template, but actually always procs when prompt_template={prompt}
                # however if you're doing that, it doesn't matter
                if USE_SYSTEM_PROMPT and B_SYS not in prompt_template:
                    if system_prompt.strip() and not system_prompt.endswith(" "):
                        # mistral doesn't have a SYS token, there's just a space between the system prompt and
                        system_prompt = system_prompt.strip() + " "
                        print("Added a space to your system prompt")
                prompt = prompt_template.format(
                    system_prompt=system_prompt, prompt=prompt
                )
            # MLC adds BOS token
            prompt = prompt.removeprefix("<s>")
            print(f"Your formatted prompt is: \n{prompt}")

            if theia_weights:
                start = time.time()
                self.initialize_peft(theia_weights)
                print(f"Overall initialize_peft took {time.time() - start:.3f}")
            else:
                if "COG_WEIGHTS" not in os.environ:
                    self.delete_lora()
                    print("Not using LoRA")

            if seed is not None:
                print(f"Setting seed to {seed}")
                seed_all(seed)

            n_tokens = 0
            st = time.time()

            # if return_logits:
            # logits = self.engine.get_logits(prompt)
            # # serializing so we aren't returning a massive json
            # logits_path = "logits.pt"
            # torch.save(logits, logits_path)
            # yield Path(logits_path)

            # # todo: may need to do something clever with kwargs if/when we add more engines.
            # else:
            generated_text = ""
            for decoded_token in self.engine(
                prompt,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                repetition_penalty=repetition_penalty,
                max_new_tokens=max_new_tokens,
                min_new_tokens=min_new_tokens,
                stop_sequences=stop_sequences,
            ):
                n_tokens += 1
                yield decoded_token
                generated_text += decoded_token
                if n_tokens == 1 and debug:
                    second_start = time.time()
                if seed is not None:
                    torch.manual_seed(seed)
            et = time.time()
            t = et - st
            print(f"hostname: {socket.gethostname()}")
            if debug:
                print("generated text:", generated_text)
                print(f"after initialization, first token took {second_start - st:.3f}")
                print(f"Tokens per second: {n_tokens / t:.2f}")
                print(
                    f"Tokens per second not including time to first token: {(n_tokens -1) / (et - second_start):.2f}"
                )
                print(f"cur memory: {torch.cuda.memory_allocated()}")
                print(f"max allocated: {torch.cuda.max_memory_allocated()}")
                print(f"peak memory: {torch.cuda.max_memory_reserved()}")

    def remove(f: Callable, defaults: dict[str, Any]) -> Callable:
        # pylint: disable=no-self-argument
        def wrapper(self, *args, **kwargs):
            kwargs.update(defaults)
            return f(self, *args, **kwargs)

        # Update wrapper attributes for documentation, etc.
        functools.update_wrapper(wrapper, f)

        # for the purposes of inspect.signature as used by predictor.get_input_type,
        # remove the argument (system_prompt)
        sig = inspect.signature(f)
        params = [p for name, p in sig.parameters.items() if name not in defaults]
        wrapper.__signature__ = sig.replace(parameters=params)

        # Return partialmethod, wrapper behaves correctly when part of a class
        return functools.partialmethod(wrapper)

    args_to_remove: dict[str, Any] = {}
    if not USE_SYSTEM_PROMPT:
        # this removes system_prompt from the Theia API for non-chat models.
        args_to_remove["system_prompt"] = None
    if not USE_TOP_K:
        args_to_remove["top_k"] = None
    if args_to_remove:
        predict = remove(predict, args_to_remove)
