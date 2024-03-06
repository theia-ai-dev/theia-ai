# Copyright (c) Meta Platforms, Inc. and affiliates.
# This software may be used and distributed according to the terms of the Llama 2 Community License Agreement.

from dataclasses import dataclass
from typing import ClassVar, List
import torch


@dataclass
class lora_config:
    r: int = 8
    lora_alpha: int = 16
    target_modules: ClassVar[List[str]] = ["q_proj", "v_proj"]
    bias = "none"
    task_type: str = "CAUSAL_LM"
    lora_dropout: float = 0.05
    inference_mode: bool = False


@dataclass
class llama_adapter_config:
    adapter_len: int = 10
    adapter_layers: int = 30
    task_type: str = "CAUSAL_LM"


@dataclass
class prefix_config:
    num_virtual_tokens: int = 30
    task_type: str = "CAUSAL_LM"


@dataclass
class bitsandbytes_config:
    load_in_4bit: bool = True
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_compute_dtype: torch.dtype = torch.bfloat16


@dataclass
class qlora_config:
    r: int = 8
    lora_alpha: int = 32
    target_modules: ClassVar[List[str]] = ["q_proj", "v_proj"]
    bias = "none"
    task_type: str = "CAUSAL_LM"
    lora_dropout: float = 0.05
    inference_mode: bool = False
